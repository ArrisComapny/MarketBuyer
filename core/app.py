from database.db import Database, Base

db: Database | None = None

class DBConnectionError(Exception):
    pass

async def init_application():
    global db
    db = Database(echo=False)

    ok = await db.test_connection()
    if not ok:
        raise DBConnectionError("Не удалось подключиться к базе данных.")

    await db.init_models(Base)
