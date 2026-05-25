import uuid
import json
import hashlib
import os
import requests
from flask import Blueprint, request, jsonify, Response, stream_with_context
from flask_jwt_extended import jwt_required, get_jwt_identity
import config
from models import db, Conversation, ChatMessage
from services.rag import retrieve
from services.audio import transcribe_audio_file
from services.cognitive import (
    get_installed_models, should_use_rag, load_memory_db, delete_memory_db,
    maybe_summarise, build_messages, ollama_chat_stream, extract_and_save_memory
)

chat_bp = Blueprint("chat", __name__)


def get_deterministic_uuid(user_id: str, name: str) -> uuid.UUID:
    """Generate a stable, deterministic UUID based on user_id and session name/key."""
    hash_input = f"{user_id}:{name}".encode("utf-8")
    sha256 = hashlib.sha256(hash_input).hexdigest()
    return uuid.UUID(sha256[:32])


@chat_bp.route("/api/models")
def list_models():
    return jsonify({"models": get_installed_models()})


@chat_bp.route("/api/memory", methods=["GET"])
@jwt_required()
def get_memory():
    current_user_id = get_jwt_identity()
    return jsonify(load_memory_db(current_user_id))


@chat_bp.route("/api/memory", methods=["DELETE"])
@jwt_required()
def delete_memory():
    current_user_id = get_jwt_identity()
    delete_memory_db(current_user_id)
    return jsonify({"status": "cleared"})


@chat_bp.route("/api/switch-model", methods=["POST"])
@jwt_required()
def switch_model():
    return jsonify({"status": "ok"})


@chat_bp.route("/api/clear", methods=["POST"])
@jwt_required()
def clear_history():
    current_user_id = get_jwt_identity()
    data = request.json or {}
    session_id = data.get("session_id", "default")
    
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError:
        session_uuid = get_deterministic_uuid(current_user_id, session_id)
        
    try:
        ChatMessage.query.filter_by(conversation_id=session_uuid).delete()
        Conversation.query.filter_by(id=session_uuid, user_id=uuid.UUID(current_user_id)).delete()
        db.session.commit()
        return jsonify({"status": "cleared"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@chat_bp.route("/api/transcribe", methods=["POST"])
def transcribe_audio():
    if "file" not in request.files:
        return jsonify({"error": "No audio file provided"}), 400
        
    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "Empty audio filename"}), 400
        
    temp_name = f"temp_{uuid.uuid4().hex}.wav"
    filepath = os.path.join(config.UPLOAD_FOLDER, temp_name)
    file.save(filepath)
    
    try:
        result = transcribe_audio_file(filepath)
        if os.path.exists(filepath):
            os.remove(filepath)
        return jsonify({"text": result})
    except Exception as e:
        if os.path.exists(filepath):
            os.remove(filepath)
        return jsonify({"error": f"Transcription failed: {str(e)}"}), 500


@chat_bp.route("/api/chat", methods=["POST"])
@jwt_required()
def chat():
    current_user_id = get_jwt_identity()
    user_uuid = uuid.UUID(current_user_id)
    
    data       = request.json or {}
    session_id = data.get("session_id", "default")
    user_msg   = data.get("message", "").strip()
    model      = data.get("model", config.AVAILABLE_MODELS[0])

    if not user_msg:
        return jsonify({"error": "Empty message"}), 400

    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError:
        session_uuid = get_deterministic_uuid(current_user_id, session_id)

    # 1. Fetch or create Conversation record in database
    conv = Conversation.query.filter_by(id=session_uuid, user_id=user_uuid).first()
    if not conv:
        conv = Conversation(id=session_uuid, user_id=user_uuid, summary="")
        db.session.add(conv)
        db.session.commit()

    # 2. Fetch history from database
    messages_db = ChatMessage.query.filter_by(conversation_id=conv.id).order_by(ChatMessage.timestamp.asc()).all()
    history = [{"role": m.role, "content": m.content} for m in messages_db]

    # Reconstruct volatile session dict in-memory for our existing helper architecture
    session = {
        "history": history,
        "summary": conv.summary,
        "model": model
    }

    model_switched = False
    
    # 3. Insert user message to database
    user_msg_db = ChatMessage(conversation_id=conv.id, role="user", content=user_msg)
    db.session.add(user_msg_db)
    db.session.commit()
    
    session["history"].append({"role": "user", "content": user_msg})
    
    # Trigger rolling summarization check
    maybe_summarise(str(conv.id), session, model)

    use_rag = should_use_rag(user_msg, model, current_user_id)
    rag_chunks = retrieve(user_msg, current_user_id) if use_rag else []
    messages   = build_messages(session, load_memory_db(current_user_id), rag_chunks)

    def generate():
        sources = list({c["source"] for c in rag_chunks})
        yield f"data: {json.dumps({'sources': sources, 'model_switched': model_switched, 'prev_model': model, 'current_model': model, 'done': False})}\n\n"

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
                    # Save Assistant message to database
                    assistant_msg_db = ChatMessage(
                        conversation_id=conv.id,
                        role="assistant",
                        content=full_response
                    )
                    db.session.add(assistant_msg_db)
                    db.session.commit()
                    
                    try:
                        extract_and_save_memory(user_msg, full_response, model, current_user_id)
                    except Exception as e:
                        print(f"Error saving facts in routes/chat.py: {e}")
                        
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
