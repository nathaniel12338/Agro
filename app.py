"""
app.py
------
The backend for the Agricultural Chatbot.

WHAT THIS FILE DOES:
1. Loads the embeddings created by train.py so it can answer farming
   questions using SEMANTIC search (meaning-based, not just keywords).
2. If no local answer is confident enough (similarity < 0.5), it tries
   the free Gemini API as a fallback (only if you've set GEMINI_API_KEY).
3. If Gemini isn't available either, it replies with an honest
   "I don't know" message instead of making something up.
4. Provides /sell and /buy endpoints backed by a small SQLite database,
   so farmers can list produce for sale and buyers can search for it.

HOW TO RUN:
    1. python train.py              (only needed once, or after editing data.json)
    2. uvicorn app:app --reload     (starts the server on http://127.0.0.1:8000)

See README.md for full setup instructions and how to embed the widget
into a PHP website.
"""

import os
import sqlite3
import pickle
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# --------------------------------------------------------------------------
# CONFIG
# --------------------------------------------------------------------------

EMBEDDINGS_FILE = "embeddings.pkl"
DB_FILE = "agrichatbot.db"

# How confident the semantic match needs to be (0 to 1) before we trust
# the local dataset answer. Below this, we try Gemini instead.
SIMILARITY_THRESHOLD = 0.5

# Set this as an environment variable, e.g.:
#   export GEMINI_API_KEY="your-key-here"        (Mac/Linux)
#   setx GEMINI_API_KEY "your-key-here"           (Windows)
# Get a free key at https://aistudio.google.com/apikey
# The app works fine WITHOUT this key -- it just won't have a fallback
# for questions outside the local dataset.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = "gemini-3.6-flash"
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)

# --------------------------------------------------------------------------
# APP SETUP
# --------------------------------------------------------------------------

app = FastAPI(title="Agricultural Chatbot API")

# Allow the widget to be embedded on ANY website (PHP, WordPress, etc.)
# and still be able to call this API from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------
# DATABASE HELPERS (SQLite)
# --------------------------------------------------------------------------

def init_db():
    """Create the sellers and chats tables if they don't already exist."""
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sellers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_name TEXT NOT NULL,
                quantity TEXT NOT NULL,
                location TEXT NOT NULL,
                price TEXT NOT NULL,
                phone TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message TEXT NOT NULL,
                reply TEXT NOT NULL,
                source TEXT NOT NULL,
                similarity REAL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


@contextmanager
def get_db():
    """Small helper so every DB call opens/closes its connection safely."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


# --------------------------------------------------------------------------
# LOAD THE SEMANTIC SEARCH MODEL + EMBEDDINGS
# --------------------------------------------------------------------------

# These get filled in by load_embeddings() when the server starts.
_model = None
_flat_questions = []
_question_to_answer = []
_embeddings = None  # numpy array
_dataset = []


def load_embeddings():
    """
    Load the embeddings.pkl file created by train.py, and load the
    sentence-transformers model so we can embed NEW incoming questions
    at chat time (the questions in data.json were already embedded by
    train.py; here we just need the same model to embed what the user
    types, so we can compare the two).
    """
    global _model, _flat_questions, _question_to_answer, _embeddings, _dataset

    if not os.path.exists(EMBEDDINGS_FILE):
        raise FileNotFoundError(
            f"'{EMBEDDINGS_FILE}' not found. Run 'python train.py' first "
            "to generate it from data.json."
        )

    with open(EMBEDDINGS_FILE, "rb") as f:
        payload = pickle.load(f)

    _flat_questions = payload["flat_questions"]
    _question_to_answer = payload["question_to_answer"]
    _embeddings = payload["embeddings"]
    _dataset = payload["dataset"]

    from sentence_transformers import SentenceTransformer

    _model = SentenceTransformer(payload["model_name"])
    print(f"Loaded {len(_flat_questions)} question embeddings and model '{payload['model_name']}'.")


def find_best_answer(user_message: str):
    """
    Compare the user's question against every question in our dataset
    using cosine similarity, and return the best match.

    Since embeddings were saved normalized (unit length) in train.py,
    the cosine similarity between two embeddings is just their dot
    product -- fast and simple.

    Returns: (answer_text, category, similarity_score)
    """
    query_embedding = _model.encode(
        [user_message], convert_to_numpy=True, normalize_embeddings=True
    )[0]

    # Dot product of the query against every stored question embedding.
    similarities = _embeddings @ query_embedding  # shape: (num_questions,)

    best_index = int(np.argmax(similarities))
    best_score = float(similarities[best_index])
    answer_index = _question_to_answer[best_index]
    matched_entry = _dataset[answer_index]

    return matched_entry["answer"], matched_entry["category"], best_score


# --------------------------------------------------------------------------
# GEMINI FALLBACK
# --------------------------------------------------------------------------

def ask_gemini(user_message: str) -> Optional[str]:
    """
    Ask Google's free Gemini API for an answer when our local dataset
    isn't confident about the question. Returns None if no API key is
    set, or if the request fails for any reason (keeping the bot
    "offline-first": it should never crash just because Gemini is
    unreachable).
    """
    if not GEMINI_API_KEY:
        return None

    import requests  # imported here so the app still runs without 'requests'
                      # installed if you never use the Gemini fallback path

    prompt = (
        "You are a helpful agricultural extension assistant for farmers "
        "in Nigeria. Answer the following farming question clearly and "
        "practically, in 3-5 sentences.\n\n"
        f"Question: {user_message}"
    )

    try:
        response = requests.post(
            GEMINI_URL,
            params={"key": GEMINI_API_KEY},
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as error:  # noqa: BLE001 - deliberately broad: never crash the bot
        print(f"Gemini fallback failed: {error}")
        return None


# --------------------------------------------------------------------------
# REQUEST / RESPONSE MODELS
# --------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)


class ChatResponse(BaseModel):
    reply: str
    source: str          # "dataset" | "gemini" | "fallback"
    similarity: float
    category: Optional[str] = None


class SellRequest(BaseModel):
    product_name: str = Field(..., min_length=1)
    quantity: str = Field(..., min_length=1)
    location: str = Field(..., min_length=1)
    price: str = Field(..., min_length=1)
    phone: str = Field(..., min_length=1)


class Seller(BaseModel):
    id: int
    product_name: str
    quantity: str
    location: str
    price: str
    phone: str
    created_at: str


# --------------------------------------------------------------------------
# STARTUP
# --------------------------------------------------------------------------

@app.on_event("startup")
def on_startup():
    init_db()
    load_embeddings()


# --------------------------------------------------------------------------
# ENDPOINTS
# --------------------------------------------------------------------------

@app.get("/")
def root():
    return {"status": "ok", "message": "Agricultural Chatbot API is running."}


@app.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest):
    """
    Answer a farming question.
    1. Try the local dataset first (semantic search).
    2. If similarity is below the threshold, try Gemini.
    3. If neither works, return an honest fallback message.
    """
    user_message = payload.message.strip()

    answer, category, similarity = find_best_answer(user_message)
    source = "dataset"

    if similarity < SIMILARITY_THRESHOLD:
        gemini_answer = ask_gemini(user_message)
        if gemini_answer:
            answer = gemini_answer
            source = "gemini"
        else:
            answer = (
                "I'm not confident I have a good answer for that yet. "
                "I can currently help best with questions about maize, "
                "rice, cassava, and tomato -- planting time, spacing, "
                "fertilizer, pests, diseases, and harvesting. Could you "
                "try rephrasing your question, or ask about one of those crops?"
            )
            source = "fallback"
            category = None

    # Log every conversation turn so you can review common questions later.
    with get_db() as conn:
        conn.execute(
            "INSERT INTO chats (message, reply, source, similarity, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_message, answer, source, similarity, datetime.utcnow().isoformat()),
        )
        conn.commit()

    return ChatResponse(reply=answer, source=source, similarity=similarity, category=category)


@app.post("/sell", response_model=Seller)
def sell(payload: SellRequest):
    """Save a new produce listing from a farmer who wants to sell."""
    created_at = datetime.utcnow().isoformat()

    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO sellers (product_name, quantity, location, price, phone, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                payload.product_name.strip(),
                payload.quantity.strip(),
                payload.location.strip(),
                payload.price.strip(),
                payload.phone.strip(),
                created_at,
            ),
        )
        conn.commit()
        new_id = cursor.lastrowid

    return Seller(
        id=new_id,
        product_name=payload.product_name,
        quantity=payload.quantity,
        location=payload.location,
        price=payload.price,
        phone=payload.phone,
        created_at=created_at,
    )


@app.get("/buy", response_model=list[Seller])
def buy(product: str):
    """Search for sellers of a given product, most recent first."""
    if not product.strip():
        raise HTTPException(status_code=400, detail="Please provide a product to search for.")

    search_term = f"%{product.strip()}%"

    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM sellers WHERE product_name LIKE ? COLLATE NOCASE "
            "ORDER BY created_at DESC",
            (search_term,),
        ).fetchall()

    return [Seller(**dict(row)) for row in rows]