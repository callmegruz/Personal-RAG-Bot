import os
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
import config
from services.rag import (
    list_documents, ingest_document, delete_document, secure_filename_hash,
    count_user_chunks, get_user_documents_and_chunks
)

doc_bp = Blueprint("documents", __name__)

@doc_bp.route("/api/documents", methods=["GET"])
@jwt_required()
def get_documents():
    current_user_id = get_jwt_identity()
    docs, total_chunks = get_user_documents_and_chunks(current_user_id)
    return jsonify({
        "documents": docs, 
        "total_chunks": total_chunks
    })


@doc_bp.route("/api/documents/upload", methods=["POST"])
@jwt_required()
def upload_document():
    current_user_id = get_jwt_identity()
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "Empty filename"}), 400
    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext not in {"pdf", "txt", "md"}:
        return jsonify({"error": f"Unsupported type .{ext}"}), 400
    
    hashed_name = secure_filename_hash(file.filename)
    user_dir = os.path.join(config.UPLOAD_FOLDER, current_user_id)
    os.makedirs(user_dir, exist_ok=True)
    filepath = os.path.join(user_dir, hashed_name)
    file.save(filepath)
    try:
        n = ingest_document(filepath, file.filename, current_user_id)
        return jsonify({"status": "ok", "filename": file.filename, "chunks": n})
    except Exception as e:
        if os.path.exists(filepath):
            os.remove(filepath)
        return jsonify({"error": str(e)}), 500


@doc_bp.route("/api/documents/delete", methods=["POST"])
@jwt_required()
def remove_document():
    current_user_id = get_jwt_identity()
    filename = request.json.get("filename", "")
    if not filename:
        return jsonify({"error": "No filename"}), 400
    delete_document(filename, current_user_id)
    
    hashed_name = secure_filename_hash(filename)
    fp = os.path.join(config.UPLOAD_FOLDER, current_user_id, hashed_name)
    if os.path.exists(fp):
        os.remove(fp)
    return jsonify({"status": "deleted"})
