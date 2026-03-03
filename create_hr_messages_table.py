import sqlite3

conn = sqlite3.connect("database.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS hr_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    worker_id INTEGER,
    subject TEXT,
    message TEXT,
    attachment TEXT,
    status TEXT DEFAULT 'Pending',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")

conn.commit()
conn.close()

print("✅ hr_messages table created successfully")
