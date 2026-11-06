import sqlite3
from pathlib import Path

DB_PATH = "filmlog.db"
SEED_SQL_PATH = Path("../data/seed.sql")

def init_database():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor() 

    # Mengaktifkan foreign key support
    cursor.execute("PRAGMA foreign_keys = ON;")

    # 1. Menjalankan seed.sql untuk membuat tabel dan mengisi 20 film awal
    with open(SEED_SQL_PATH, "r", encoding="utf-8") as f:
        seed_sql = f.read()
        cursor.executescript(seed_sql)

    # 2. Tabel users (menyimpan akun register dan login)
        # Membuat tabel users dengan kolom id, username, password, dan email    
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE
            );
        """)
    # 3. Tabel watchlists (menyimpan daftar film yang ingin ditonton oleh pengguna)
        # Membuat tabel watchlists dengan kolom id, user_id, dan film_id
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS watchlists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                movie_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (movie_id) REFERENCES films(id) ON DELETE CASCADE
                UNIQUE (user_id, movie_id)
            );
        """)

    # 4. tabel watched (menyimpan ulasan film rating 1-5 yang diberikan oleh pengguna dan review)
        # Membuat tabel watched dengan kolom id, user_id, film_id, rating, review, dan created_at
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS watched (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                movie_id INTEGER NOT NULL,
                rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
                review TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (movie_id) REFERENCES movies(id) ON DELETE CASCADE,
                UNIQUE (user_id, movie_id)
            );
        """)    

    conn.commit()
    conn.close()
    print("Database initialized successfully.")

if __name__ == "__main__":
    init_database()