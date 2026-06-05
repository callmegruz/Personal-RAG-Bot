import os
import uuid
import shutil
from flask import Blueprint, render_template, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import db, User, Conversation
import config
from services.rag import collection, list_documents, count_user_chunks

admin_bp = Blueprint("admin", __name__)

@admin_bp.route("/admin", methods=["GET"])
@jwt_required(optional=True)
def admin_dashboard_page():
    current_user_id = get_jwt_identity()
    if not current_user_id:
        return "Unauthorized. Please log in first.", 401
    
    try:
        user = User.query.get(uuid.UUID(current_user_id))
        if not user or user.role != "admin":
            return "Access Forbidden. Admins only.", 403
    except Exception:
        return "Invalid session.", 400
        
    theme = request.cookies.get("theme", "fire")
    return render_template("admin.html", theme=theme)


@admin_bp.route("/api/admin/users", methods=["GET"])
@jwt_required()
def list_users():
    current_admin_id = get_jwt_identity()
    try:
        admin = User.query.get(uuid.UUID(current_admin_id))
        if not admin or admin.role != "admin":
            return jsonify({"error": "Admin privilege required"}), 403
            
        users = User.query.order_by(User.created_at.desc()).all()
        
        # Optimize 1: Fetch conversation counts grouped by user_id in one database query (fixes SQL N+1)
        from sqlalchemy import func
        conv_counts = dict(
            db.session.query(Conversation.user_id, func.count(Conversation.id))
            .group_by(Conversation.user_id)
            .all()
        )
        
        # Optimize 2: Fetch all user documents and chunk counts from ChromaDB in a single query (fixes Chroma N+1)
        user_docs = {}
        user_chunks = {}
        try:
            if collection.count() > 0:
                all_chunks = collection.get(include=["metadatas"])
                if all_chunks and all_chunks.get("metadatas"):
                    for m in all_chunks["metadatas"]:
                        if m:
                            u_id = m.get("user_id")
                            source = m.get("source")
                            if u_id:
                                if u_id not in user_docs:
                                    user_docs[u_id] = set()
                                if source:
                                    user_docs[u_id].add(source)
                                user_chunks[u_id] = user_chunks.get(u_id, 0) + 1
        except Exception as ce:
            print(f"[ERROR] Failed to batch fetch ChromaDB stats: {ce}")
            
        user_list = []
        for u in users:
            str_id = str(u.id)
            docs = sorted(list(user_docs.get(str_id, [])))
            chunks_count = user_chunks.get(str_id, 0)
            c_count = conv_counts.get(u.id, 0)
            
            user_list.append({
                "id": str_id,
                "username": u.username,
                "first_name": u.first_name or "",
                "last_name": u.last_name or "",
                "email": u.email or "",
                "role": u.role,
                "created_at": u.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "conv_count": c_count,
                "doc_count": len(docs),
                "chunk_count": chunks_count
            })
            
        return jsonify({"users": user_list})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/api/admin/users/<uuid:user_id>/role", methods=["POST"])
@jwt_required()
def change_user_role(user_id):
    current_admin_id = uuid.UUID(get_jwt_identity())
    try:
        admin = User.query.get(current_admin_id)
        if not admin or admin.role != "admin":
            return jsonify({"error": "Admin privilege required"}), 403
            
        if current_admin_id == user_id:
            return jsonify({"error": "You cannot modify your own role"}), 400
            
        data = request.json or {}
        new_role = data.get("role", "").strip()
        if new_role not in {"user", "admin"}:
            return jsonify({"error": "Invalid role specified"}), 400
            
        target_user = User.query.get(user_id)
        if not target_user:
            return jsonify({"error": "User not found"}), 404
            
        target_user.role = new_role
        db.session.commit()
        return jsonify({"status": "ok", "message": f"User role updated to {new_role}"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/api/admin/users/<uuid:user_id>", methods=["DELETE"])
@jwt_required()
def delete_user(user_id):
    current_admin_id = uuid.UUID(get_jwt_identity())
    try:
        admin = User.query.get(current_admin_id)
        if not admin or admin.role != "admin":
            return jsonify({"error": "Admin privilege required"}), 403
            
        if current_admin_id == user_id:
            return jsonify({"error": "You cannot delete your own admin account"}), 400
            
        target_user = User.query.get(user_id)
        if not target_user:
            return jsonify({"error": "User not found"}), 404
            
        # 1. Purge from ChromaDB
        str_user_id = str(user_id)
        try:
            if collection.count() > 0:
                results = collection.get(where={"user_id": str_user_id}, include=[])
                if results and results.get("ids"):
                    collection.delete(ids=results["ids"])
        except Exception as ce:
            print(f"Error purging ChromaDB for user {user_id}: {ce}")
            
        # 2. Delete uploads folder
        user_dir = os.path.join(config.UPLOAD_FOLDER, str_user_id)
        if os.path.exists(user_dir):
            shutil.rmtree(user_dir)
            
        # 3. Delete from PostgreSQL (SQLAlchemy cascade deletes memories/conversations)
        db.session.delete(target_user)
        db.session.commit()
        return jsonify({"status": "ok", "message": "User and all associated data completely deleted"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to delete user: {str(e)}"}), 500
