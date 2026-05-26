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
    first_name = data.get("first_name", "").strip()
    last_name = data.get("last_name", "").strip()
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()
    role = data.get("role", "user").strip().lower()
    
    if not first_name or not last_name or not email or not password:
        return jsonify({"error": "All fields are required"}), 400
        
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters long"}), 400
        
    if role not in {"user", "admin"}:
        return jsonify({"error": "Invalid role specified"}), 400

    try:
        # Check if user already exists with this email or username
        existing_user = User.query.filter((User.username == email) | (User.email == email)).first()
        if existing_user:
            return jsonify({"error": "Email is already registered"}), 400
            
        # Create user
        hashed_password = generate_password_hash(password)
        new_user = User(
            username=email,
            first_name=first_name,
            last_name=last_name,
            email=email,
            role=role,
            password_hash=hashed_password
        )
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
        return jsonify({"error": "Username/Email and password are required"}), 400

    try:
        user = User.query.filter((User.username == username) | (User.email == username)).first()
        if not user or not check_password_hash(user.password_hash, password):
            return jsonify({"error": "Invalid username/email or password"}), 401
            
        # Create JWT access token
        access_token = create_access_token(identity=str(user.id))
        
        # Build response and set JWT cookie
        display_name = user.first_name if user.first_name else user.username
        response = jsonify({
            "status": "ok",
            "message": "Logged in successfully",
            "access_token": access_token,
            "username": display_name,
            "role": user.role
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
        display_name = user.first_name if user.first_name else user.username
        return jsonify({
            "logged_in": True,
            "username": display_name,
            "role": user.role,
            "id": str(user.id)
        })
    except Exception:
        return jsonify({"logged_in": False}), 200
