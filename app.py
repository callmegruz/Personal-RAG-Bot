import os
import uuid
from flask import Flask, render_template, request, Response
from flask_jwt_extended import JWTManager
from models import db
import config

# Import modular blueprints
from routes.auth import auth_bp
from routes.documents import doc_bp
from routes.chat import chat_bp
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
jwt = JWTManager(app)

# Register routing blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(doc_bp)
app.register_blueprint(chat_bp)

# Automatically create all tables at startup if they do not exist
with app.app_context():
    try:
        db.create_all()
        print("[SUCCESS] PostgreSQL database tables verified/created successfully.")
    except Exception as e:
        print(f"[WARNING] Could not connect to PostgreSQL or create tables: {e}")
        print("[INFO] Make sure your PostgreSQL database is running and configured correctly in your .env file.")


@app.route("/")
def index():
    theme = request.args.get("theme")
    models = get_installed_models()
    default = models[0] if models else config.AVAILABLE_MODELS[0]
    
    if theme in ("classic", "fire"):
        response = Response(render_template("index.html", models=models, default_model=default, theme=theme))
        response.set_cookie("theme", theme, max_age=30*24*60*60)
        return response

    cookie_theme = request.cookies.get("theme", "fire")
    response = Response(render_template("index.html", models=models, default_model=default, theme=cookie_theme))
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