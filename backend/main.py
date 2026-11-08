import os
import sqlite3
import random
import jwt
import bcrypt
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI(
    title="FilmLog Backend API",
    description="Movie Watchlist REST API with Gemini Integration for GDGoC UGM",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

DB_PATH = "filmlog.db"
SECRET_KEY = os.getenv("JWT_SECRET", "gdgoc-ugm-secret-key-2026")
ALGORITHM = "HS256"

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

def create_jwt_token(user_id: int, username: str, email: str):
    payload = {
        "user_id": user_id,
        "username": username,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(hours=24)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

# 1. Menampilkan semua film
@app.get("/api/movies")
def getmovies(shuffle: bool = False):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM movies")
    rows = cursor.fetchall()
    conn.close()

    movies = [dict(row) for row in rows]
    if shuffle:
        random.shuffle(movies)
    return movies

# 2. Menampilkan detail 1 film berdasarkan ID
@app.get("/api/movies/{movie_id}")
def get_movie(movie_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM movies WHERE id = ?", (movie_id,))
    row = cursor.fetchone()
    conn.close()

    if row is None:
        return JSONResponse(status_code=404, content={"message": "Movie not found"})

    return dict(row)

# 3. Registrasi pengguna baru
@app.post("/api/auth/register")
def register_user(data: RegisterRequest):
    if not data.username.strip() or not data.email.strip() or len(data.password) < 6:
        return JSONResponse(
            status_code=400,
            content={"message": "Username dan email wajib diisi, serta password minimal 6 karakter"}
        )

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM users WHERE email = ? OR username = ?",
        (data.email, data.username)
    )
    if cursor.fetchone() is not None:
        conn.close()
        return JSONResponse(
            status_code=409,
            content={"message": "Email atau username sudah terdaftar"}
        )

    hashed_pw = bcrypt.hashpw(data.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    cursor.execute(
        "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
        (data.username, data.email, hashed_pw)
    )
    conn.commit()
    new_user_id = cursor.lastrowid
    conn.close()

    token = create_jwt_token(new_user_id, data.username, data.email)
    return JSONResponse(
        status_code=201,
        content={
            "message": "Registrasi berhasil",
            "token": token,
            "user": {
                "id": new_user_id,
                "username": data.username,
                "email": data.email
            }
        }
    )

# 4. Login pengguna
@app.post("/api/auth/login")
def login_user(data: LoginRequest):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (data.email,))
    user = cursor.fetchone()
    conn.close()

    if user is None:
        return JSONResponse(
            status_code=401,
            content={"message": "Email atau password salah"}
        )

    is_valid = bcrypt.checkpw(
        data.password.encode("utf-8"),
        user["password_hash"].encode("utf-8")
    )

    if not is_valid:
        return JSONResponse(
            status_code=401,
            content={"message": "Email atau password salah"}
        )

    token = create_jwt_token(user["id"], user["username"], user["email"])
    return {
        "message": "Login berhasil",
        "token": token,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "email": user["email"]
        }
    }

    class WatchlistRequest(BaseModel):
        movie_id: int

# Fungsi pembantu untuk memeriksa keaslian token JWT dari Header Authorization
class WatchlistRequest(BaseModel):
    movie_id: int | None = None
    movieId: int | None = None
    id: int | None = None

def get_current_user_id(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("user_id")
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None

# 5. Menampilkan daftar film di Watchlist milik pengguna yang sedang login
@app.get("/api/watchlist")
def get_watchlist(authorization: str | None = Header(default=None)):
    user_id = get_current_user_id(authorization)
    if user_id is None:
        return JSONResponse(status_code=401, content={"message": "Silakan login terlebih dahulu"})

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT m.*
        FROM watchlists w
        JOIN movies m ON w.movie_id = m.id
        WHERE w.user_id = ?
        ORDER BY w.id DESC
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]

# 6. Menambahkan film ke dalam Watchlist
@app.post("/api/watchlist")
def add_to_watchlist(data: WatchlistRequest, authorization: str | None = Header(default=None)):
    user_id = get_current_user_id(authorization)
    if user_id is None:
        return JSONResponse(status_code=401, content={"message": "Silakan login terlebih dahulu"})

    target_movie_id = data.movie_id or data.movieId or data.id
    if target_movie_id is None:
        return JSONResponse(status_code=400, content={"message": "ID film tidak valid"})

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM movies WHERE id = ?", (target_movie_id,))
    if cursor.fetchone() is None:
        conn.close()
        return JSONResponse(status_code=404, content={"message": "Film tidak ditemukan"})

    cursor.execute(
        "SELECT id FROM watchlists WHERE user_id = ? AND movie_id = ?",
        (user_id, target_movie_id)
    )
    if cursor.fetchone() is not None:
        conn.close()
        return JSONResponse(status_code=409, content={"message": "Film sudah ada di watchlist kamu"})

    cursor.execute(
        "INSERT INTO watchlists (user_id, movie_id) VALUES (?, ?)",
        (user_id, target_movie_id)
    )
    conn.commit()
    conn.close()

    return JSONResponse(status_code=201, content={"message": "Film berhasil ditambahkan ke watchlist"})

# 7. Menghapus film dari Watchlist
@app.delete("/api/watchlist/{movie_id}")
def remove_from_watchlist(movie_id: int, authorization: str | None = Header(default=None)):
    user_id = get_current_user_id(authorization)
    if user_id is None:
        return JSONResponse(status_code=401, content={"message": "Silakan login terlebih dahulu"})

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM watchlists WHERE user_id = ? AND movie_id = ?",
        (user_id, movie_id)
    )
    conn.commit()
    deleted_rows = cursor.rowcount
    conn.close()

    if deleted_rows == 0:
        return JSONResponse(status_code=404, content={"message": "Film tidak ditemukan di watchlist"})

    return {"message": "Film berhasil dihapus dari watchlist"}