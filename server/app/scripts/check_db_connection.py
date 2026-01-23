import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from config_manager import config


async def main() -> None:
    url = config.get_database_url()
    engine = create_async_engine(url, echo=False)
    try:
        async with engine.connect() as conn:
            result = await conn.execute("SELECT 1")
            _ = result.scalar()
            print("DB connection: OK")
    except Exception as exc:
        print(f"DB connection: FAILED - {exc}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())


