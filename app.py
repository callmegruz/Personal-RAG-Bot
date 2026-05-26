import os
import uuid
from datetime import timedelta
from flask import Flask, render_template, request, Response
from flask_jwt_extended import JWTManager, jwt_required, get_jwt_identity
from models import db
import config

# Import modular blueprints
from routes.auth import auth_bp
from routes.documents import doc_bp
from routes.chat import chat_bp
from routes.admin import admin_bp
from services.cognitive import get_installed_models

app = Flask(__name__)
os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = config.UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = config.MAX_CONTENT_LENGTH

# ── Database & JWT configuration ──────────────────────────────────────────────
app.config["SQLALCHEMY_DATABASE_URI"] = config.DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

app.config["JWT_SECRET_KEY"] = config.JWT_SECRET_KEY
app.config["JWT_TOKEN_LOCATION"] = ["headers", "cookies"]
app.config["JWT_COOKIE_CSRF_PROTECT"] = False
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(days=30)
jwt = JWTManager(app)

# Register routing blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(doc_bp)
app.register_blueprint(chat_bp)
app.register_blueprint(admin_bp)

# Automatically create all tables at startup if they do not exist
with app.app_context():
    try:
        db.create_all()
        print("[SUCCESS] PostgreSQL database tables verified/created successfully.")
    except Exception as e:
        print(f"[WARNING] Could not connect to PostgreSQL or create tables: {e}")
        print("[INFO] Make sure your PostgreSQL database is running and configured correctly in your .env file.")


@app.route("/")
@jwt_required(optional=True)
def index():
    theme = request.args.get("theme")
    models = get_installed_models()
    default = models[0] if models else config.AVAILABLE_MODELS[0]
    
    current_user_id = get_jwt_identity()
    is_logged_in = current_user_id is not None
    greeting = "PERSONAL RAG BOT"
    
    if is_logged_in:
        try:
            from models import User
            user = User.query.get(uuid.UUID(current_user_id))
            if user:
                display_name = user.first_name if user.first_name else user.username
                display_name = display_name[0].upper() + display_name[1:] if display_name else ""
                
                from datetime import datetime
                hour = datetime.now().hour
                if hour < 12:
                    greet_prefix = "Good Morning"
                elif hour < 17:
                    greet_prefix = "Good Afternoon"
                else:
                    greet_prefix = "Good Evening"
                greeting = f"{greet_prefix}, {display_name}!"
        except Exception:
            pass
            
    if theme in ("classic", "fire"):
        response = Response(render_template("index.html", models=models, default_model=default, theme=theme, is_logged_in=is_logged_in, greeting=greeting))
        response.set_cookie("theme", theme, max_age=30*24*60*60)
        return response

    cookie_theme = request.cookies.get("theme", "fire")
    response = Response(render_template("index.html", models=models, default_model=default, theme=cookie_theme, is_logged_in=is_logged_in, greeting=greeting))
    response.set_cookie("theme", cookie_theme, max_age=30*24*60*60)
    return response


# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("🤖 Flask Chatbot starting...")
    print(f"🔗 Ollama: {config.OLLAMA_URL}  |  embed: {config.EMBED_MODEL}")
    models = get_installed_models()
    if models:
        print(f"✅ Available models: {', '.join(models)}")
    else:
        print("⚠️  No models found. Pull models with: ollama pull llama3.2")
    print(f"\n💡 To add more models, edit AVAILABLE_MODELS in config.py, then: ollama pull <model>")
    app.run(debug=True, host="0.0.0.0", port=5000, threaded=True)