"""
train.py
--------
Run this ONCE (and again any time you edit data.json) to turn the Q&A
dataset into numeric "embeddings" that the chatbot can compare against
in app.py.

WHAT IS AN EMBEDDING?
An embedding is just a list of numbers that represents the MEANING of a
sentence. Two sentences that mean the same thing (even in different
words, or in Pidgin English) end up with embeddings that are close to
each other. This is how the bot understands "when to plant maize" and
"How I go plant maize" as the same question, instead of relying on
exact word matches like old-school TF-IDF search does.

WHAT THIS SCRIPT DOES:
1. Loads data.json (our list of {questions, answer, category} entries)
2. Flattens it into one big list of individual questions, each pointing
   back to its answer/category
3. Uses the sentence-transformers model "all-MiniLM-L6-v2" to convert
   every question into an embedding (a vector of 384 numbers)
4. Saves everything into embeddings.pkl so app.py can load it instantly
   at startup, without needing to re-run the model every time.

HOW TO RUN:
    python train.py

This downloads the "all-MiniLM-L6-v2" model the first time (needs
internet + about 90MB), then caches it locally for offline use after
that.
"""

import json
import pickle
import sys

DATA_FILE = "data.json"
OUTPUT_FILE = "embeddings.pkl"
MODEL_NAME = "all-MiniLM-L6-v2"


def main():
    # Step 1: load the raw Q&A dataset
    print(f"Loading dataset from {DATA_FILE} ...")
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        dataset = json.load(f)
    print(f"Loaded {len(dataset)} answer groups.")

    # Step 2: flatten into (question_text, answer_index) pairs.
    # We keep every phrasing/variation as its own row so the model can
    # match ANY of them, but they all point back to the same answer.
    flat_questions = []      # list[str]  -> every individual question
    question_to_answer = []  # list[int]  -> index into `dataset` for each question

    for answer_index, entry in enumerate(dataset):
        for question_text in entry["questions"]:
            flat_questions.append(question_text)
            question_to_answer.append(answer_index)

    print(f"Flattened into {len(flat_questions)} individual question variations.")

    # Step 3: load the sentence-transformers model and encode everything
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print(
            "\nERROR: sentence-transformers is not installed.\n"
            "Run:  pip install -r requirements.txt\n"
        )
        sys.exit(1)

    print(f"Loading model '{MODEL_NAME}' (first run downloads it, later runs use the local cache)...")
    model = SentenceTransformer(MODEL_NAME)

    print("Encoding all questions into embeddings... (this takes a few seconds)")
    embeddings = model.encode(
        flat_questions,
        convert_to_numpy=True,
        show_progress_bar=True,
        normalize_embeddings=True,  # pre-normalize so cosine similarity = dot product
    )

    # Step 4: save everything the chatbot needs at runtime
    payload = {
        "model_name": MODEL_NAME,
        "flat_questions": flat_questions,
        "question_to_answer": question_to_answer,
        "embeddings": embeddings,       # numpy array, shape (num_questions, 384)
        "dataset": dataset,             # original answer/category data
    }

    with open(OUTPUT_FILE, "wb") as f:
        pickle.dump(payload, f)

    print(f"\nDone! Saved {len(flat_questions)} embeddings to '{OUTPUT_FILE}'.")
    print("You can now start the chatbot with:  uvicorn app:app --reload")


if __name__ == "__main__":
    main()
