import uuid
from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import (
    jwt_required, create_access_token, get_jwt_identity, 
    set_access_cookies, unset_jwt_cookies
)
from models import db, User

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/api/register", methods=["POST"])
def register():
    data = request.json or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    
    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400
        
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters long"}), 400

    try:
        # Check if user already exists
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            return jsonify({"error": "Username already exists"}), 400
            
        # Create user
        hashed_password = generate_password_hash(password)
        new_user = User(username=username, password_hash=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        
        return jsonify({"status": "ok", "message": "User registered successfully"}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Registration failed: {str(e)}"}), 500


@auth_bp.route("/api/login", methods=["POST"])
def login():
    data = request.json or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    
    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    try:
        user = User.query.filter_by(username=username).first()
        if not user or not check_password_hash(user.password_hash, password):
            return jsonify({"error": "Invalid username or password"}), 401
            
        # Create JWT access token
        access_token = create_access_token(identity=str(user.id))
        
        # Build response and set JWT cookie
        response = jsonify({
            "status": "ok",
            "message": "Logged in successfully",
            "access_token": access_token,
            "username": user.username
        })
        set_access_cookies(response, access_token)
        return response
    except Exception as e:
        return jsonify({"error": f"Login failed: {str(e)}"}), 500


@auth_bp.route("/api/logout", methods=["POST"])
def logout():
    response = jsonify({"status": "ok", "message": "Logged out successfully"})
    unset_jwt_cookies(response)
    return response


@auth_bp.route("/api/me", methods=["GET"])
@jwt_required(optional=True)
def get_current_user():
    current_user_id = get_jwt_identity()
    if not current_user_id:
        return jsonify({"logged_in": False}), 200
        
    try:
        user = User.query.get(uuid.UUID(current_user_id))
        if not user:
            return jsonify({"logged_in": False}), 200
        return jsonify({
            "logged_in": True,
            "username": user.username,
            "id": str(user.id)
        })
    except Exception:
        return jsonify({"logged_in": False}), 200
