"""The only place that picks adapters, like container.ts in the app."""

from dataclasses import dataclass, field

import httpx
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.auth import TokenVerifier, jwks_resolver
from app.config import Settings
from app.integrations.supabase import SupabaseAvatarStorage, SupabaseIdentityAdmin
from app.rate_limit import RateLimiter
from app.services.ports import AvatarStorage, IdentityAdmin


@dataclass
class Container:
    settings: Settings
    engine: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]
    verifier: TokenVerifier
    storage: AvatarStorage
    identity: IdentityAdmin
    rate_limiter: RateLimiter
    http: httpx.AsyncClient | None = field(default=None)

    async def close(self) -> None:
        if self.http:
            await self.http.aclose()
        await self.engine.dispose()


def create_engine(settings: Settings) -> AsyncEngine:
    connect_args = {"statement_cache_size": 0} if settings.db_transaction_pooler else {}
    return create_async_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_pool_size,
        pool_pre_ping=True,
        connect_args=connect_args,
    )


def build_container(settings: Settings) -> Container:
    engine = create_engine(settings)
    http = httpx.AsyncClient(timeout=10)
    service_key = settings.supabase_service_role_key.get_secret_value()
    return Container(
        settings=settings,
        engine=engine,
        sessions=async_sessionmaker(engine, expire_on_commit=False),
        verifier=TokenVerifier(
            jwks_resolver(settings.jwks_url), issuer=settings.jwt_issuer, audience=settings.jwt_audience
        ),
        storage=SupabaseAvatarStorage(http, settings.supabase_url, service_key, settings.avatars_bucket),
        identity=SupabaseIdentityAdmin(http, settings.supabase_url, service_key),
        rate_limiter=RateLimiter(settings.rate_limit_per_minute),
        http=http,
    )
