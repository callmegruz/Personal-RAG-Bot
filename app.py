from flask import Flask, render_template, request, jsonify, Response, stream_with_context
import requests
import json
import os
import uuid
import re
import hashlib
from concurrent.futures import ThreadPoolExecutor

# ── PDF extraction ─────────────────────────────────────────────────────────────
try:
    import pypdf
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False

# ── ChromaDB ───────────────────────────────────────────────────────────────────
import chromadb
from chromadb.config import Settings

app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10MB maximum upload limit

@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({"error": "File size exceeds the 10MB maximum limit."}), 413

def secure_filename_hash(filename: str) -> str:
    """
    Generate a safe, deterministic cryptographic hash of the filename
    to obfuscate it on the server filesystem. This prevents path/directory traversal
    and avoids exposing the original filename structure on disk.
    """
    base_name = os.path.basename(filename)
    parts = base_name.rsplit(".", 1)
    ext = parts[-1].lower() if len(parts) > 1 else ""
    
    sha256 = hashlib.sha256(base_name.encode("utf-8")).hexdigest()
    return f"{sha256}.{ext}" if ext else sha256

# ══════════════════════════════════════════════════════════════════════════════
# Ollama configuration
# Add as many locally pulled models as you like to AVAILABLE_MODELS.
# The first one in the list becomes the default.
# To add a model: ollama pull <model-name>
# ══════════════════════════════════════════════════════════════════════════════

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
# Default is the first model in the list that is actually installed locally.
# Falls back to the first entry if none are found.
DEFAULT_MODEL = AVAILABLE_MODELS[0]

# ── RAG / context settings ─────────────────────────────────────────────────────
DEFAULT_CHUNK_SIZE    = 800
DEFAULT_CHUNK_OVERLAP = 150
TOP_K                 = 6
CHROMA_DIR            = "chroma_db"
RECENT_TURNS          = 6
MEMORY_FILE           = "memory.json"

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

# In-memory session store
sessions: dict = {}

# ══════════════════════════════════════════════════════════════════════════════
# Ollama helpers
# ══════════════════════════════════════════════════════════════════════════════

def get_installed_models() -> list:
    """
    Returns the intersection of AVAILABLE_MODELS and what Ollama has installed,
    preserving the order defined in AVAILABLE_MODELS.
    Filters out embedding models like nomic-embed-text that are not designed for chat.
    """
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        if r.status_code != 200:
            return AVAILABLE_MODELS  # fallback: show configured list
        
        installed = set()
        for m in r.json().get("models", []):
            name = m["name"]
            # Exclude dedicated embedding models or any tag containing 'embed'
            if name == EMBED_MODEL or "embed" in name.lower() or name.startswith("nomic"):
                continue
            installed.add(name)

        # Keep configured order, include only installed ones
        ordered = [m for m in AVAILABLE_MODELS if m in installed]
        # Append any locally installed models not in AVAILABLE_MODELS
        extras = [m for m in installed if m not in AVAILABLE_MODELS]
        return ordered + sorted(extras)
    except requests.exceptions.ConnectionError:
        return []


def ollama_chat_stream(messages: list, model: str):
    r = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={"model": model, "messages": messages, "stream": True},
        stream=True,
        timeout=120,
    )
    r.raise_for_status()
    return r


def ollama_complete(prompt: str, model: str) -> str:
    """Non-streaming completion — used for summarisation and memory extraction."""
    r = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={"model": model, "messages": [{"role": "user", "content": prompt}], "stream": False},
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["message"]["content"].strip()


# ══════════════════════════════════════════════════════════════════════════════
# ChromaDB + embeddings (always uses EMBED_MODEL via Ollama)
# ══════════════════════════════════════════════════════════════════════════════

chroma_client = chromadb.PersistentClient(
    path=CHROMA_DIR,
    settings=Settings(anonymized_telemetry=False),
)
collection = chroma_client.get_or_create_collection(
    name="documents",
    metadata={"hnsw:space": "cosine"},
)


def embed_one(text: str) -> list:
    r = requests.post(
        f"{OLLAMA_URL}/api/embeddings",
        json={"model": EMBED_MODEL, "prompt": text},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["embedding"]


def embed(texts: list) -> list:
    with ThreadPoolExecutor(max_workers=10) as executor:
        embeddings = list(executor.map(embed_one, texts))
    return embeddings


def get_adaptive_params(text_len: int) -> tuple:
    """
    Dynamically adjust chunk size and overlap based on document length.
    - Small docs (< 4,000 chars): smaller chunks for high resolution retrieval.
    - Medium docs (< 15,000 chars): moderate size.
    - Large docs: standard larger size to prevent excessive API calls.
    """
    if text_len < 4000:
        return 350, 80
    elif text_len < 15000:
        return 550, 110
    else:
        return 800, 150


def chunk_text(text: str, source: str) -> list:
    if not text or not text.strip():
        return []
    
    # Determine adaptive parameters based on document length
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
            # Fallback split
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
            
            # Handle parts that are individually larger than the chunk size limit
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
                
                # Overlap logic: grab trailing portion of the current segment
                overlap_start = max(0, len(current_segment) - chunk_overlap)
                overlap_text = current_segment[overlap_start:]
                current_segment = overlap_text + part_with_sep
                
        if current_segment:
            chunks.append(current_segment.rstrip(sep) if sep else current_segment)
            
        # Final pass to ensure all chunks are bounded correctly
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
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext == "pdf":
        if not HAS_PYPDF:
            raise RuntimeError("pypdf not installed. Run: pip install pypdf")
        reader = pypdf.PdfReader(filepath)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def ingest_document(filepath: str, filename: str) -> int:
    text   = extract_text(filepath, filename)
    chunks = chunk_text(text, filename)
    if not chunks:
        return 0
    texts      = [c["text"]   for c in chunks]
    metadatas  = [{"source": c["source"]} for c in chunks]
    ids        = [str(uuid.uuid4()) for _ in chunks]
    collection.add(documents=texts, embeddings=embed(texts), metadatas=metadatas, ids=ids)
    return len(chunks)


def list_documents() -> list:
    if collection.count() == 0:
        return []
    results = collection.get(include=["metadatas"])
    return sorted({m["source"] for m in results["metadatas"]})


def delete_document(filename: str):
    results       = collection.get(include=["metadatas"])
    ids_to_delete = [rid for rid, meta in zip(results["ids"], results["metadatas"])
                     if meta.get("source") == filename]
    if ids_to_delete:
        collection.delete(ids=ids_to_delete)


def retrieve(query: str, top_k: int = TOP_K) -> list:
    if collection.count() == 0:
        return []
    results = collection.query(
        query_embeddings=embed([query]),
        n_results=min(top_k, collection.count()),
        include=["documents", "metadatas", "distances"],
    )
    return [{"text": doc, "source": meta["source"], "score": 1 - dist}
            for doc, meta, dist in zip(results["documents"][0],
                                       results["metadatas"][0],
                                       results["distances"][0])]


def format_rag_context(chunks: list) -> str:
    return "\n\n".join(f"[{i}] (from: {c['source']})\n{c['text']}"
                       for i, c in enumerate(chunks, 1))


# ══════════════════════════════════════════════════════════════════════════════
# Persistent memory
# ══════════════════════════════════════════════════════════════════════════════

def load_memory() -> dict:
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_memory(mem: dict):
    with open(MEMORY_FILE, "w") as f:
        json.dump(mem, f, indent=2)


def memory_as_text(mem: dict) -> str:
    if not mem:
        return "No facts remembered yet."
    return "\n".join(f"- {k}: {v}" for k, v in mem.items())


# ══════════════════════════════════════════════════════════════════════════════
# Summarisation
# ══════════════════════════════════════════════════════════════════════════════

def summarise(messages: list, model: str) -> str:
    transcript = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in messages)
    return ollama_complete(
        f"Summarise this conversation in 3-5 sentences, keeping all key facts:\n\n{transcript}\n\nSUMMARY:",
        model,
    )


def maybe_summarise(session: dict, model: str):
    history = session["history"]
    if len(history) <= RECENT_TURNS:
        return
    old, keep = history[:-RECENT_TURNS], history[-RECENT_TURNS:]
    new_sum = summarise(old, model)
    if session["summary"]:
        session["summary"] = ollama_complete(
            f"Merge into one paragraph:\n\nOLDER:\n{session['summary']}\n\nNEWER:\n{new_sum}\n\nMERGED:",
            model,
        )
    else:
        session["summary"] = new_sum
    session["history"] = keep


# ══════════════════════════════════════════════════════════════════════════════
# Memory extraction
# ══════════════════════════════════════════════════════════════════════════════

def extract_and_save_memory(user_msg: str, assistant_msg: str, model: str):
    prompt = (
        "Extract personal facts about the user worth remembering long-term "
        "(name, occupation, preferences, projects, etc.).\n\n"
        f"USER: {user_msg}\nASSISTANT: {assistant_msg}\n\n"
        "Respond ONLY with a JSON object {\"key\": \"value\"} or {} if none. No markdown."
    )
    try:
        raw   = ollama_complete(prompt, model).strip().strip("```json").strip("```").strip()
        facts = json.loads(raw)
        if facts and isinstance(facts, dict):
            mem = load_memory()
            mem.update(facts)
            save_memory(mem)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
# Message builder
# ══════════════════════════════════════════════════════════════════════════════

def build_messages(session: dict, memory: dict, rag_chunks: list) -> list:
    sections = [SYSTEM_PROMPT]
    sections.append(f"=== REMEMBERED FACTS ===\n{memory_as_text(memory)}")
    if session["summary"]:
        sections.append(f"=== EARLIER CONVERSATION SUMMARY ===\n{session['summary']}")
    if rag_chunks:
        sections.append(f"=== RELEVANT DOCUMENT EXCERPTS ===\n{format_rag_context(rag_chunks)}")
    return [{"role": "system", "content": "\n\n".join(sections)}] + session["history"]


# ══════════════════════════════════════════════════════════════════════════════
# Routes
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    models = get_installed_models()
    default = models[0] if models else DEFAULT_MODEL
    return render_template("index.html", models=models, default_model=default)


@app.route("/api/models")
def list_models():
    return jsonify({"models": get_installed_models()})


@app.route("/api/memory", methods=["GET"])
def get_memory():
    return jsonify(load_memory())

@app.route("/api/memory", methods=["DELETE"])
def delete_memory():
    save_memory({})
    return jsonify({"status": "cleared"})


@app.route("/api/documents", methods=["GET"])
def get_documents():
    return jsonify({"documents": list_documents(), "total_chunks": collection.count()})


@app.route("/api/documents/upload", methods=["POST"])
def upload_document():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "Empty filename"}), 400
    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext not in {"pdf", "txt", "md"}:
        return jsonify({"error": f"Unsupported type .{ext}"}), 400
    
    hashed_name = secure_filename_hash(file.filename)
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], hashed_name)
    file.save(filepath)
    try:
        n = ingest_document(filepath, file.filename)
        return jsonify({"status": "ok", "filename": file.filename, "chunks": n})
    except Exception as e:
        # Clean up the file if ingestion fails
        if os.path.exists(filepath):
            os.remove(filepath)
        return jsonify({"error": str(e)}), 500


@app.route("/api/documents/delete", methods=["POST"])
def remove_document():
    filename = request.json.get("filename", "")
    if not filename:
        return jsonify({"error": "No filename"}), 400
    delete_document(filename)
    
    hashed_name = secure_filename_hash(filename)
    fp = os.path.join(app.config["UPLOAD_FOLDER"], hashed_name)
    if os.path.exists(fp):
        os.remove(fp)
    return jsonify({"status": "deleted"})


def should_use_rag(query: str, model: str) -> bool:
    """
    Determine if the query is relevant to the indexed documents.
    1. If the database is empty, return False.
    2. Check for explicit general queries using keyword heuristics (instant).
    3. Use a fast, single-token LLM classification call as a fallback.
    """
    if collection.count() == 0:
        return False
        
    query_lower = query.lower()
    
    # Heuristic check for greetings, chit-chat, and coding instructions
    general_patterns = [
        r"^(hi|hello|hey|greetings|good morning|good afternoon|good evening|howdy)(\s+.*)?$",
        r"^how are you(\s+.*)?$",
        r"^who are you(\s+.*)?$",
        r"^what is your name(\s+.*)?$",
        r"^write a (python|javascript|c\+\+|html|css|code|script|function|program|query|sql)(\s+.*)?$",
        r"^help(\s+.*)?$",
    ]
    
    if any(re.match(pattern, query_lower) for pattern in general_patterns):
        return False
        
    # Heuristics for direct document keywords
    doc_keywords = ["document", "file", "pdf", "txt", "text", "upload", "summarise", "summarize", "read", "report", "context", "cite", "citation"]
    if any(word in query_lower for word in doc_keywords):
        return True
        
    # Fast LLM classifier fallback
    prompt = (
        "You are an intent router for a document chat assistant.\n"
        f"User query: \"{query}\"\n"
        "Determine if this query asks about files, uploaded documents, or specific source context. "
        "Respond with ONLY 'YES' if it relates to uploaded documents/context, or 'NO' if it is a general question (coding, greetings, general knowledge). Do not write anything else."
    )
    try:
        response = ollama_complete(prompt, model).strip().upper()
        return "YES" in response
    except Exception:
        # Fallback to True to be safe if model fails
        return True


@app.route("/api/chat", methods=["POST"])
def chat():
    data       = request.json
    session_id = data.get("session_id", "default")
    user_msg   = data.get("message", "").strip()
    model      = data.get("model", DEFAULT_MODEL)

    if not user_msg:
        return jsonify({"error": "Empty message"}), 400

    if session_id not in sessions:
        sessions[session_id] = {"history": [], "summary": "", "model": model}

    session = sessions[session_id]

    prev_model     = session.get("model", model)
    model_switched = prev_model != model
    if model_switched and session["history"]:
        maybe_summarise(session, prev_model)
        session["model"] = model

    session["history"].append({"role": "user", "content": user_msg})
    maybe_summarise(session, model)

    use_rag = should_use_rag(user_msg, model)
    rag_chunks = retrieve(user_msg) if use_rag else []
    messages   = build_messages(session, load_memory(), rag_chunks)

    def generate():
        sources = list({c["source"] for c in rag_chunks})
        yield f"data: {json.dumps({'sources': sources, 'model_switched': model_switched, 'prev_model': prev_model, 'current_model': model, 'done': False})}\n\n"

        full_response = ""
        try:
            resp = ollama_chat_stream(messages, model)
            for line in resp.iter_lines():
                if not line:
                    continue
                chunk = json.loads(line)
                token = chunk.get("message", {}).get("content", "")
                done  = chunk.get("done", False)
                if token:
                    full_response += token
                    yield f"data: {json.dumps({'token': token, 'done': False})}\n\n"
                if done:
                    session["history"].append({"role": "assistant", "content": full_response})
                    try:
                        extract_and_save_memory(user_msg, full_response, model)
                    except Exception:
                        pass
                    yield f"data: {json.dumps({'token': '', 'done': True})}\n\n"
                    return

        except requests.exceptions.ConnectionError:
            yield f"data: {json.dumps({'error': 'Cannot connect to Ollama. Is it running?', 'done': True})}\n\n"
        except requests.exceptions.HTTPError as e:
            yield f"data: {json.dumps({'error': f'Ollama error {e.response.status_code}', 'done': True})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e), 'done': True})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/switch-model", methods=["POST"])
def switch_model():
    data       = request.json
    session_id = data.get("session_id", "default")
    new_model  = data.get("model", DEFAULT_MODEL)
    if session_id in sessions:
        sessions[session_id]["model"] = new_model
    return jsonify({"status": "ok", "model": new_model})


@app.route("/api/clear", methods=["POST"])
def clear_history():
    session_id = request.json.get("session_id", "default")
    sessions.pop(session_id, None)
    return jsonify({"status": "cleared"})


# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("🤖 Flask Chatbot starting...")
    print(f"🔗 Ollama: {OLLAMA_URL}  |  embed: {EMBED_MODEL}")
    models = get_installed_models()
    if models:
        print(f"✅ Available models: {', '.join(models)}")
    else:
        print("⚠️  No models found. Pull models with: ollama pull llama3.2")
    print(f"\n💡 To add more models, edit AVAILABLE_MODELS in app.py, then: ollama pull <model>")
    print(f"📚 ChromaDB: {collection.count()} chunks in {CHROMA_DIR}/")
    mem = load_memory()
    if mem:
        print(f"🧠 Loaded {len(mem)} remembered fact(s)")
    app.run(debug=True, host="0.0.0.0", port=5000)