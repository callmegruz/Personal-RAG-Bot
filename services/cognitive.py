import json
import uuid
import re
import requests
import time
from models import db, Conversation, ChatMessage, UserMemory
import config
from services.rag import collection

# ── Ollama Helper Methods ─────────────────────────────────────────────────────────

_installed_models_cache = None
_installed_models_cache_time = 0

def get_installed_models() -> list:
    """
    Returns the list of locally pulled Ollama models.
    Filters out embedding models like nomic-embed-text.
    Caches the results for 30 seconds to prevent slow page reloads.
    """
    global _installed_models_cache, _installed_models_cache_time
    now = time.time()
    if _installed_models_cache is not None and (now - _installed_models_cache_time) < 30:
        return _installed_models_cache

    try:
        r = requests.get(f"{config.OLLAMA_URL}/api/tags", timeout=2)
        if r.status_code != 200:
            return config.AVAILABLE_MODELS
        
        installed = set()
        for m in r.json().get("models", []):
            name = m["name"]
            if name == config.EMBED_MODEL or "embed" in name.lower() or name.startswith("nomic"):
                continue
            installed.add(name)

        ordered = [m for m in config.AVAILABLE_MODELS if m in installed]
        extras = [m for m in installed if m not in config.AVAILABLE_MODELS]
        _installed_models_cache = ordered + sorted(extras)
        _installed_models_cache_time = now
        return _installed_models_cache
    except Exception:
        # Fallback to cache if available, otherwise return default config models
        if _installed_models_cache is not None:
            return _installed_models_cache
        return config.AVAILABLE_MODELS


def ollama_chat_stream(messages: list, model: str):
    """Initiates a streaming chat interface with Ollama."""
    r = requests.post(
        f"{config.OLLAMA_URL}/api/chat",
        json={"model": model, "messages": messages, "stream": True},
        stream=True,
        timeout=120,
    )
    r.raise_for_status()
    return r


def ollama_complete(prompt: str, model: str) -> str:
    """Non-streaming complete pass - used for summaries and facts extraction."""
    r = requests.post(
        f"{config.OLLAMA_URL}/api/chat",
        json={"model": model, "messages": [{"role": "user", "content": prompt}], "stream": False},
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["message"]["content"].strip()


# ── RAG Intent Routing Heuristic ───────────────────────────────────────────────

def should_use_rag(query: str, model: str, user_id: str) -> bool:
    """
    Determine if the query is relevant to the indexed documents.
    """
    from services.rag import list_documents
    user_docs = list_documents(user_id)
    if not user_docs:
        return False
        
    query_lower = query.lower()
    
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
        
    # Default to True to guarantee vector search runs reliably for any other query
    return True


# ── PostgreSQL Memory Helpers ──────────────────────────────────────────────────

def load_memory_db(user_id: str) -> dict:
    """Loads all saved facts for a specific user from the PostgreSQL database."""
    try:
        memories = UserMemory.query.filter_by(user_id=uuid.UUID(user_id)).all()
        return {m.fact_key: m.fact_value for m in memories}
    except Exception as e:
        print(f"Error loading memory in services/cognitive.py: {e}")
        return {}


def delete_memory_db(user_id: str):
    """Deletes all saved user facts from the PostgreSQL database."""
    try:
        UserMemory.query.filter_by(user_id=uuid.UUID(user_id)).delete()
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting memory in services/cognitive.py: {e}")


def memory_as_text(mem: dict) -> str:
    """Helper compiler mapping memories dictionary into structured strings."""
    if not mem:
        return "No facts remembered yet."
    return "\n".join(f"- {k}: {v}" for k, v in mem.items())


# ── Rolling Summarization Service ──────────────────────────────────────────────

def summarise(messages: list, model: str) -> str:
    """Summarizes a block of conversational logs."""
    transcript = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in messages)
    return ollama_complete(
        f"Summarise this conversation in 3-5 sentences, keeping all key facts:\n\n{transcript}\n\nSUMMARY:",
        model,
    )


def maybe_summarise(session_id: str, session: dict, model: str):
    """
    Checks rolling log turns count. If it exceeds boundaries, runs summarise pass,
    updates PostgreSQL summary field, and truncates volatile history.
    """
    history = session["history"]
    if len(history) <= config.RECENT_TURNS:
        return
    old, keep = history[:-config.RECENT_TURNS], history[-config.RECENT_TURNS:]
    new_sum = summarise(old, model)
    try:
        conv = Conversation.query.get(uuid.UUID(session_id))
        if conv:
            if conv.summary:
                merged = ollama_complete(
                    f"Merge into one paragraph:\n\nOLDER:\n{conv.summary}\n\nNEWER:\n{new_sum}\n\nMERGED:",
                    model,
                )
                conv.summary = merged
                session["summary"] = merged
            else:
                conv.summary = new_sum
                session["summary"] = new_sum
            
            # Sync database messages by removing the truncated ones
            ChatMessage.query.filter_by(conversation_id=conv.id).delete()
            for msg in keep:
                m_record = ChatMessage(
                    conversation_id=conv.id,
                    role=msg["role"],
                    content=msg["content"]
                )
                db.session.add(m_record)
            db.session.commit()
            session["history"] = keep
    except Exception as e:
        db.session.rollback()
        print(f"Error in maybe_summarise inside services/cognitive.py: {e}")


# ── Cognitive Facts Memory Extractor ──────────────────────────────────────────

def extract_and_save_memory(user_msg: str, assistant_msg: str, model: str, user_id: str):
    """
    Autonomous assistant pass that parses new dialogue elements, structures personal facts
    as JSON, and upserts them securely into SQL db records.
    """
    prompt = (
        "Extract personal facts about the user worth remembering long-term "
        "(name, occupation, preferences, projects, etc.).\n\n"
        f"USER: {user_msg}\nASSISTANT: {assistant_msg}\n\n"
        "Respond ONLY with a JSON object {\"key\": \"value\"} or {} if none. No markdown."
    )
    try:
        raw = ollama_complete(prompt, model)
        
        # 1. Clean raw text from <think>...</think> processes (very common in reasoning models like deepseek-r1)
        raw_clean = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL)
        
        # 2. Extract first JSON block matching { ... } to handle markdown wraps or leading/trailing text
        start = raw_clean.find('{')
        end = raw_clean.rfind('}')
        if start != -1 and end != -1 and end > start:
            json_str = raw_clean[start:end+1]
        else:
            json_str = raw_clean.strip().strip("```json").strip("```").strip()
            
        facts = json.loads(json_str)
        if facts and isinstance(facts, dict):
            for key, val in facts.items():
                if not key or not val:
                    continue
                # Ensure keys and values are treated as clean strings
                key_str = str(key).strip()
                val_str = str(val).strip()
                
                existing = UserMemory.query.filter_by(
                    user_id=uuid.UUID(user_id),
                    fact_key=key_str
                ).first()
                if existing:
                    existing.fact_value = val_str
                else:
                    new_mem = UserMemory(
                        user_id=uuid.UUID(user_id),
                        fact_key=key_str,
                        fact_value=val_str
                    )
                    db.session.add(new_mem)
            db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Error extracting memory inside services/cognitive.py: {e}")


# ── Prompt Context Compiler ─────────────────────────────────────────────────────

def build_messages(session: dict, memory: dict, rag_chunks: list) -> list:
    """Formats default context templates adding facts history, rolling summary summaries, and RAG context."""
    sections = [config.SYSTEM_PROMPT]
    sections.append(f"=== REMEMBERED FACTS ===\n{memory_as_text(memory)}")
    if session["summary"]:
        sections.append(f"=== EARLIER CONVERSATION SUMMARY ===\n{session['summary']}")
    if rag_chunks:
        from services.rag import format_rag_context
        sections.append(f"=== RELEVANT DOCUMENT EXCERPTS ===\n{format_rag_context(rag_chunks)}")
    return [{"role": "system", "content": "\n\n".join(sections)}] + session["history"]
