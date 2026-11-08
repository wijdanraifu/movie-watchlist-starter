import os
import json
import sqlite3
import random
import jwt
import bcrypt
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from google import genai
from google.genai import types
from fastapi import FastAPI, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

load_dotenv()

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
    allow_headers=["*"],
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

class WatchlistRequest(BaseModel):
    movie_id: int | None = None
    movieId: int | None = None
    id: int | None = None

class WatchedRequest(BaseModel):
    movie_id: int | None = None
    movieId: int | None = None
    id: int | None = None
    rating: int
    review: str | None = ""

def create_jwt_token(user_id: int, username: str, email: str):
    payload = {
        "user_id": user_id,
        "username": username,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(hours=24)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user_id(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("user_id")
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None

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

# 5. Menampilkan daftar film di Watchlist
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

# 8. Menampilkan daftar film yang sudah ditonton
@app.get("/api/watched")
def get_watched(authorization: str | None = Header(default=None)):
    user_id = get_current_user_id(authorization)
    if user_id is None:
        return JSONResponse(status_code=401, content={"message": "Silakan login terlebih dahulu"})

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT m.*, w.id AS watched_id, w.movie_id, w.rating, w.rating AS user_rating, w.review
        FROM watched w
        JOIN movies m ON w.movie_id = m.id
        WHERE w.user_id = ?
        ORDER BY w.id DESC
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]

# 9. Mencatat film yang sudah ditonton beserta rating & ulasan
@app.post("/api/watched")
def add_to_watched(data: WatchedRequest, authorization: str | None = Header(default=None)):
    user_id = get_current_user_id(authorization)
    if user_id is None:
        return JSONResponse(status_code=401, content={"message": "Silakan login terlebih dahulu"})

    target_movie_id = data.movie_id or data.movieId or data.id
    if target_movie_id is None:
        return JSONResponse(status_code=400, content={"message": "ID film tidak valid"})

    if data.rating < 1 or data.rating > 5:
        return JSONResponse(status_code=400, content={"message": "Rating harus bernilai antara 1 sampai 5"})

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM movies WHERE id = ?", (target_movie_id,))
    if cursor.fetchone() is None:
        conn.close()
        return JSONResponse(status_code=404, content={"message": "Film tidak ditemukan"})

    cursor.execute(
        "SELECT id FROM watched WHERE user_id = ? AND movie_id = ?",
        (user_id, target_movie_id)
    )
    existing = cursor.fetchone()

    if existing is not None:
        cursor.execute(
            "UPDATE watched SET rating = ?, review = ? WHERE id = ?",
            (data.rating, data.review or "", existing["id"])
        )
    else:
        cursor.execute(
            "INSERT INTO watched (user_id, movie_id, rating, review) VALUES (?, ?, ?, ?)",
            (user_id, target_movie_id, data.rating, data.review or "")
        )

    cursor.execute(
        "DELETE FROM watchlists WHERE user_id = ? AND movie_id = ?",
        (user_id, target_movie_id)
    )

    conn.commit()
    conn.close()

    return JSONResponse(status_code=201, content={"message": "Ulasan film berhasil disimpan"})

class RecommendRequest(BaseModel):
    prompt: str | None = None
    query: str | None = None
    description: str | None = None

# 10. Rekomendasi film dengan Google Gemini AI
@app.post("/api/movies/recommend")
def recommend_movie(data: RecommendRequest):
    user_input = data.prompt or data.query or data.description
    if not user_input or not user_input.strip():
        return JSONResponse(
            status_code=400,
            content={"message": "Deskripsi mood atau preferensi film wajib diisi"}
        )

    print(f"\n[AI] 1. Menerima prompt: {user_input}")

    load_dotenv(override=True)
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return JSONResponse(
            status_code=500,
            content={"message": "GEMINI_API_KEY belum dipasang di file backend/.env"}
        )

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM movies")
    rows = cursor.fetchall()
    conn.close()

    movies = [dict(row) for row in rows]
    if not movies:
        return JSONResponse(
            status_code=404,
            content={"message": "Data film di database kosong"}
        )

    catalog_context = json.dumps(
        [
            {
                "id": m["id"],
                "title": m.get("title"),
                "genres": m.get("genres") or m.get("genre"),
                "synopsis": (m.get("synopsis") or m.get("description") or "")[:120]
            }
            for m in movies
        ],
        ensure_ascii=False
    )

    system_instruction = f"""
    Pilih SATU film yang paling cocok dengan permintaan pengguna HANYA dari daftar berikut:
    {catalog_context}

    Balas HANYA dalam JSON murni:
    {{"movie_id": <angka id film>, "reasoning": "<alasan singkat 2 kalimat bahasa Indonesia>"}}
    """

    try:
        print("[AI] 2. Menghubungi Gemini API (gemini-3.8-flash)...")
        client = genai.Client(api_key=api_key.strip())
        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=user_input,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                temperature=0.3,
            ),
        )

        raw_text = response.text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        print(f"[AI] 3. Jawaban Gemini: {raw_text}")
        result = json.loads(raw_text)

        selected_id = int(result.get("movie_id", movies[0]["id"]))
        reasoning = result.get("reasoning", "Film ini sangat cocok dengan suasana hatimu saat ini.")

        return {
            "movie_id": selected_id,
            "reasoning": reasoning
        }
    except Exception as e:
        print("[AI] DETAIL ERROR:", repr(e))
        return JSONResponse(
            status_code=500,
            content={"message": f"Gagal memproses rekomendasi AI: {str(e)}"}
        )