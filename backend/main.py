import sqlite3
import random
from fastapi import FastAPI 
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse


app = FastAPI(
    title="FilmLog Backend API",
    description="Movie Watchlist REST API with Gemini Integration for GDGoC UGM",
    version="1.0.0",
)

#Allow acces localhost:8000
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

DB_PATH = "filmlog.db"

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

#1, menambahkan endpoint untuk menampilkan semua film
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

#2, Menambahkan detail 1 film berdasarkan id
@app.get("/api/movies/{movie_id}")
def get_movie(movie_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM movies WHERE id = ?", (movie_id,))
    row = cursor.fetchone()
    conn.close()

    if row is None:
        return JSONResponse(status_code=404, content={"message": "Movie not found"})

    movie = dict(row)
    return movie    

