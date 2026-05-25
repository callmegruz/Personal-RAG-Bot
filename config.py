import os
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

# ── Flask & SQL Settings ──────────────────────────────────────────────────────────
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql://postgres:postgres_password@localhost:5432/rag_db"
)
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "super-secret-key-change-me")
UPLOAD_FOLDER = "uploads"
MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10MB maximum upload limit

# ── Ollama Config ───────────────────────────────────────────────────────────────
OLLAMA_URL = "http://localhost:11434"
EMBED_MODEL = "nomic-embed-text"   # ollama pull nomic-embed-text

AVAILABLE_MODELS = [
    "llama3.2",
    "mistral",
    "phi3",
    "gemma2",
    "deepseek-r1",
    "codellama",
    "llava",
    "deepseek-r1:latest"
]

# ── RAG Settings ────────────────────────────────────────────────────────────────
DEFAULT_CHUNK_SIZE    = 800
DEFAULT_CHUNK_OVERLAP = 150
TOP_K                 = 6
CHROMA_DIR            = "chroma_db"
RECENT_TURNS          = 6

# ── Default System Prompts ───────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a helpful, knowledgeable assistant.

You have access to:
1. Relevant excerpts retrieved from the user's uploaded documents (RAG context).
2. A persistent memory of facts the user has shared across sessions.
3. A rolling summary of earlier conversation turns.
4. The most recent messages verbatim.

Guidelines:
- When document excerpts are provided, ground your answer in them and cite the source document.
- If the excerpts don't cover the question, answer from your own knowledge and say so.
- Use remembered user facts naturally when relevant.
- Be concise but thorough."""
