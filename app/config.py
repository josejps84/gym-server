from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Read from environment variables (or a local .env file); see .env.example."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://gym:gym@localhost:5433/gym"
    db_pool_size: int = 5
    # Set when DATABASE_URL points at Supabase's transaction pooler (port 6543), which can't
    # keep prepared statements between queries.
    db_transaction_pooler: bool = False

    supabase_url: str = "http://localhost:54321"
    supabase_service_role_key: SecretStr = SecretStr("")
    jwt_audience: str = "authenticated"
    avatars_bucket: str = "avatars"

    # Capacitor apps (Android https://localhost, iOS capacitor://localhost), the Vite dev server and the
    # HTTPS tunnel used to try the web app from a phone.
    cors_origins: list[str] = [
        "https://localhost",
        "capacitor://localhost",
        "http://localhost:5173",
        "https://gym.josepineros.dev",
    ]
    # Requests per user and minute; 0 turns the limit off.
    rate_limit_per_minute: int = 120
    max_body_bytes: int = 1_000_000

    @property
    def jwks_url(self) -> str:
        return f"{self.supabase_url}/auth/v1/.well-known/jwks.json"

    @property
    def jwt_issuer(self) -> str:
        return f"{self.supabase_url}/auth/v1"
