import aiosqlite

DB_NAME = "company.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS workers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                role_key TEXT NOT NULL UNIQUE,
                token TEXT NOT NULL,
                emoji TEXT DEFAULT '🤖',
                system_prompt TEXT NOT NULL,
                is_active INTEGER DEFAULT 1
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS task_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                task_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()

async def add_or_update_worker(name: str, role_key: str, token: str, emoji: str, system_prompt: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            INSERT INTO workers (name, role_key, token, emoji, system_prompt, is_active)
            VALUES (?, ?, ?, ?, ?, 1)
            ON CONFLICT(role_key) DO UPDATE SET
                name=excluded.name,
                token=excluded.token,
                emoji=excluded.emoji,
                system_prompt=excluded.system_prompt,
                is_active=1
        """, (name, role_key, token, emoji, system_prompt))
        await db.commit()

async def get_all_workers():
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM workers ORDER BY id ASC") as cursor:
            return await cursor.fetchall()

async def get_active_workers():
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM workers WHERE is_active = 1 ORDER BY id ASC") as cursor:
            return await cursor.fetchall()

async def toggle_worker_status(worker_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            UPDATE workers 
            SET is_active = CASE WHEN is_active = 1 THEN 0 ELSE 1 END 
            WHERE id = ?
        """, (worker_id,))
        await db.commit()

async def delete_worker(worker_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM workers WHERE id = ?", (worker_id,))
        await db.commit()
