from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Connection, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.repositories.tables import Base


async def test_migrations_match_the_models(engine: AsyncEngine) -> None:
    def diff(connection: Connection) -> list[object]:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        return [d for d in compare_metadata(context, Base.metadata) if d[0] != "remove_table"]

    async with engine.connect() as connection:
        assert await connection.run_sync(diff) == []


async def test_row_level_security_is_on_for_every_table(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        rows = await connection.execute(
            text(
                "SELECT relname FROM pg_class WHERE relkind = 'r' AND relnamespace = 'public'::regnamespace "
                "AND NOT relrowsecurity AND relname <> 'alembic_version'"
            )
        )
        assert rows.scalars().all() == []
