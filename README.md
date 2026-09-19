# MediRAG AI

A production-ready **Retrieval-Augmented Generation (RAG)** assistant for querying trusted medical reference documents. Answers are generated **only** from documents you upload — never from the LLM's own untethered knowledge — and every answer is returned with cited source snippets.

> ⚠️ **Not a medical device.** MediRAG AI is a document-retrieval and summarization tool. It does not diagnose, prescribe, or replace professional medical judgment. See the `SYSTEM_PROMPT` in `backend/app/rag/rag_engine.py` and the disclaimer returned with every answer.

## Architecture

```
Frontend (React+Vite+TS+Tailwind)
        │  JWT-authenticated REST calls
        ▼
FastAPI backend  ──────────────►  PostgreSQL (users, documents, chat history)
        │
        ▼
RAGEngine (LangChain)
  ├── PyPDFLoader + RecursiveCharacterTextSplitter   (ingest)
  ├── HuggingFace sentence-transformers embeddings   (local, no external calls)
  ├── FAISS vector store (persisted to disk)         (retrieval)
  └── Groq API → Llama 3 (cloud inference)          (generation)
```

Embeddings run **locally**, while generation uses the **Groq API** for lightning-fast inference.

## Prerequisites

- Docker + Docker Compose (recommended), **or** locally: Python 3.11+, Node 20+, PostgreSQL 16
- Groq API Key
- ~2GB RAM free for the embedding model

## Quick Start (Docker Compose)

```bash
cd MediRAG-AI
cp backend/.env.example backend/.env   # edit JWT_SECRET_KEY and add GROQ_API_KEY before real deployment
docker compose up -d --build
```

- Frontend: http://localhost:5173
- Backend API docs (Swagger): http://localhost:8000/docs

## Local Development (without Docker)

**Backend**
```bash
cd backend
python -m venv venv
# Windows: venv\Scripts\activate, Linux/Mac: source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # ensure DATABASE_URL points at your local Postgres
uvicorn app.main:app --reload
```

**Frontend**
```bash
cd frontend
npm install
npm run dev
```

## Using the App

1. **Register** an account, then **sign in**.
2. In the left sidebar, **upload a PDF** (a clinical guideline, drug monograph, textbook chapter, etc.). It's chunked, embedded, and added to the FAISS index — watch the status go `processing → indexed`.
3. **Ask questions** in the chat panel. Answers are grounded strictly in your uploaded documents, with the exact source snippet and page shown under each answer.
4. Upload more documents any time — the knowledge base grows incrementally; no re-indexing of prior documents is needed.
