import os
import re
import uuid
import hashlib
import requests
from concurrent.futures import ThreadPoolExecutor
import chromadb
from chromadb.config import Settings
import config

try:
    import pypdf
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False

# Initialize ChromaDB Persist Client
chroma_client = chromadb.PersistentClient(
    path=config.CHROMA_DIR,
    settings=Settings(anonymized_telemetry=False),
)
collection = chroma_client.get_or_create_collection(
    name="documents",
    metadata={"hnsw:space": "cosine"},
)


def secure_filename_hash(filename: str) -> str:
    """
    Generate a safe, deterministic cryptographic hash of the filename
    to obfuscate it on the server filesystem.
    """
    base_name = os.path.basename(filename)
    parts = base_name.rsplit(".", 1)
    ext = parts[-1].lower() if len(parts) > 1 else ""
    
    sha256 = hashlib.sha256(base_name.encode("utf-8")).hexdigest()
    return f"{sha256}.{ext}" if ext else sha256


def embed_one(text: str) -> list:
    """Embed a single chunk using Ollama local embed model."""
    r = requests.post(
        f"{config.OLLAMA_URL}/api/embeddings",
        json={"model": config.EMBED_MODEL, "prompt": text},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["embedding"]


def embed(texts: list) -> list:
    """Multi-threaded embeddings generation."""
    with ThreadPoolExecutor(max_workers=10) as executor:
        embeddings = list(executor.map(embed_one, texts))
    return embeddings


def get_adaptive_params(text_len: int) -> tuple:
    """
    Dynamically adjust chunk size and overlap based on document length.
    """
    if text_len < 4000:
        return 350, 80
    elif text_len < 15000:
        return 550, 110
    else:
        return config.DEFAULT_CHUNK_SIZE, config.DEFAULT_CHUNK_OVERLAP


def chunk_text(text: str, source: str) -> list:
    """Splits a document's raw text into adaptive chunks."""
    if not text or not text.strip():
        return []
    
    chunk_size, chunk_overlap = get_adaptive_params(len(text))
    
    # Standardize line endings and multiple newlines
    normalized_text = text.replace("\r\n", "\n")
    normalized_text = re.sub(r'\n{3,}', '\n\n', normalized_text)
    
    separators = ["\n\n", "\n", " ", ""]
    
    def split_helper(txt: str, seps: list) -> list:
        txt = txt.strip()
        if not txt:
            return []
        if len(txt) <= chunk_size:
            return [txt]
        
        if not seps:
            return [txt[i:i+chunk_size] for i in range(0, len(txt), chunk_size)]
        
        sep = seps[0]
        next_seps = seps[1:]
        
        if sep == "":
            splits = list(txt)
        else:
            splits = txt.split(sep)
            
        if len(splits) == 1 and splits[0] == txt:
            return split_helper(txt, next_seps)
        
        chunks = []
        current_segment = ""
        
        for part in splits:
            if sep != "" and not part and not current_segment:
                continue
            
            part_with_sep = part if sep == "" else (part + sep)
            
            if len(part_with_sep) > chunk_size:
                if current_segment:
                    chunks.append(current_segment.rstrip(sep) if sep else current_segment)
                    current_segment = ""
                
                large_splits = split_helper(part, next_seps)
                for ls in large_splits:
                    chunks.append(ls)
                continue
            
            if len(current_segment) + len(part_with_sep) <= chunk_size:
                current_segment += part_with_sep
            else:
                if current_segment:
                    chunks.append(current_segment.rstrip(sep) if sep else current_segment)
                
                overlap_start = max(0, len(current_segment) - chunk_overlap)
                overlap_text = current_segment[overlap_start:]
                current_segment = overlap_text + part_with_sep
                
        if current_segment:
            chunks.append(current_segment.rstrip(sep) if sep else current_segment)
            
        final_chunks = []
        for chunk in chunks:
            chunk = chunk.strip()
            if not chunk:
                continue
            if len(chunk) > chunk_size:
                final_chunks.extend(split_helper(chunk, next_seps))
            else:
                final_chunks.append(chunk)
        return final_chunks
    
    chunks = split_helper(normalized_text, separators)
    return [{"text": chunk, "source": source} for chunk in chunks if chunk.strip()]


def extract_text(filepath: str, filename: str) -> str:
    """Parses raw text out of PDF, TXT, or MD documents."""
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext == "pdf":
        if not HAS_PYPDF:
            raise RuntimeError("pypdf not installed. Run: pip install pypdf")
        reader = pypdf.PdfReader(filepath)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def ingest_document(filepath: str, filename: str, user_id: str) -> int:
    """Loads document, chunks text, generates embeddings, and adds them to ChromaDB."""
    text   = extract_text(filepath, filename)
    chunks = chunk_text(text, filename)
    if not chunks:
        return 0
    texts      = [c["text"]   for c in chunks]
    metadatas  = [{"source": c["source"], "user_id": user_id} for c in chunks]
    ids        = [str(uuid.uuid4()) for _ in chunks]
    collection.add(documents=texts, embeddings=embed(texts), metadatas=metadatas, ids=ids)
    return len(chunks)


def list_documents(user_id: str) -> list:
    """Lists source names of all indexed documents for a specific user."""
    if collection.count() == 0:
        return []
    results = collection.get(where={"user_id": user_id}, include=["metadatas"])
    if not results or not results.get("metadatas"):
        return []
    return sorted({m["source"] for m in results["metadatas"]})


def count_user_chunks(user_id: str) -> int:
    """Counts the total number of chunks indexed for a specific user."""
    if collection.count() == 0:
        return 0
    results = collection.get(where={"user_id": user_id}, include=[])
    if results and "ids" in results:
        return len(results["ids"])
    return 0


def get_user_documents_and_chunks(user_id: str) -> tuple:
    """Gets all indexed document sources and total chunks for a user in a single query."""
    if collection.count() == 0:
        return [], 0
    results = collection.get(where={"user_id": user_id}, include=["metadatas"])
    if not results or not results.get("metadatas"):
        return [], 0
    sources = sorted({m["source"] for m in results["metadatas"] if m and "source" in m})
    return sources, len(results["metadatas"])


def delete_document(filename: str, user_id: str):
    """Deletes all chunks/embeddings related to a specific file and user."""
    results = collection.get(where={"$and": [{"source": filename}, {"user_id": user_id}]})
    if results and results.get("ids"):
        collection.delete(ids=results["ids"])


def retrieve(query: str, user_id: str, top_k: int = config.TOP_K) -> list:
    """Queries ChromaDB and returns top similar document excerpts."""
    if collection.count() == 0:
        return []
    results = collection.query(
        query_embeddings=embed([query]),
        n_results=min(top_k, collection.count()),
        where={"user_id": user_id},
        include=["documents", "metadatas", "distances"],
    )
    if not results or not results.get("documents") or len(results["documents"]) == 0:
        return []
    return [{"text": doc, "source": meta["source"], "score": 1 - dist}
            for doc, meta, dist in zip(results["documents"][0],
                                       results["metadatas"][0],
                                       results["distances"][0])]


def format_rag_context(chunks: list) -> str:
    """Formats RAG context excerpts into compile-friendly prompt context."""
    return "\n\n".join(f"[{i}] (from: {c['source']})\n{c['text']}"
                       for i, c in enumerate(chunks, 1))
