# 🤖 Personal RAG Bot & Local LLM Assistant

### 🔒 Absolute Data Privacy. Zero Cloud Dependencies. Production-Grade Local Architecture.

A premium, fully local **Retrieval-Augmented Generation (RAG)** chatbot and AI assistant. This application allows you to register accounts securely, upload documents (PDF, TXT, MD), and chat with them on your local network. Your data, vector embeddings, document indexes, and conversation history never leave your physical machine.

---

## 🚀 Key Architectural Features

### 1. 📚 Local Semantic Search (RAG)
* **Embedding Model:** Uses local `nomic-embed-text` vectors via Ollama.
* **Vector Store:** Integrates **ChromaDB** as a high-performance persistent vector database.
* **Adaptive Chunking:** Implements an intelligent, multi-separator recursive text splitter that dynamically adjusts chunk size and overlap based on document length to preserve context while maintaining high resolution.

### 2. 🧠 Cognitive Context & Long-Term Memory
* **Persistent Memory:** Automatically extracts personal facts shared during the chat (using structured JSON extraction) and stores them in a persistent layer across sessions.
* **Rolling Summarization:** Prevents context window saturation. When conversation turns exceed limits, older messages are summarized and compressed into a dense context block while keeping recent turns verbatim.
* **Model History Tracking:** Visualizes which LLM models (e.g. DeepSeek-R1, Llama 3.2, Mistral) were used during the current session.

### 3. 🛡️ Production-Grade Security & Authentication
* **Role-Based Access Control (RBAC):** Users register with their First Name, Last Name, Email, Password, and selectable User or Admin role. Secure cryptographic password hashing (using Werkzeug security primitives) secures credentials.
* **30-Day JWT Session Lifespans:** Configured via `Flask-JWT-Extended` with robust cookies handling. Extended token lifespan prevents unexpected 401 expirations during prolonged chat sessions.
* **Deterministic SHA-256 Filename Obfuscation:** Stored files are renamed on the server filesystem using a deterministic cryptographic hash (e.g., `uploads/<user_id>/2e34fa...a32b.txt`). This completely prevents **Directory / Path Traversal** exploits (like `../../../etc/passwd` injection) and remote code execution while keeping the database logical key human-readable.
* **Strict Upload Protection:** Implements an immediate **10MB upload limit** checked on both the frontend (browser toast notification) and backend (Flask request size constraints with graceful `413` JSON handler).
* **Robust Cryptographic Fallback:** Secret keys default to RFC 7518 compliant HMAC-SHA256 32-byte strings to eliminate console `InsecureKeyLengthWarning` messages on startup.

### 4. 🎛️ Secure Administrative Control Panel (`/admin`)
* **Interactive Admin Dashboard:** Admins can securely navigate to `/admin` to manage application state. Features live stats tracking including total conversations, uploaded document count, and specific ChromaDB chunk counts per user.
* **Role Promotion & Demotion:** Admins can dynamically promote standard users to admin level, or demote other administrators (with safe-guards preventing admins from demoting themselves).
* **Transactional Cascade Purging:** When deleting a user, the system executes a meticulous, multi-layer purge sequence:
  1. Wipes all database relations (User record, chats, messages, memory facts) via SQL cascades.
  2. Recursively deletes the user's uploaded files directory from the server disk.
  3. Queries ChromaDB and purges all document vectors matching the target `user_id` metadata. This completely eliminates database leaks and orphaned file/vector anomalies.

### 5. 🔄 Seamless Persistent Conversations (Dashboard & Page Switching)
* **Active Chat Persistence:** Navigating from the chatbot to the admin dashboard and back will no longer lose your chat history. Active chat sessions are bound using persistent, user-isolated identifiers.
* **LocalStorage Session Mapping:** Volatile random parameters are replaced with `localStorage` based session keys. This guarantees that reloading or returning to the page perfectly restores active conversations.
* **GET `/api/chat/history` Secure API:** A dedicated endpoint safely retrieves chronologically ordered message histories and active conversation summaries from PostgreSQL, restricted to the authenticated JWT user.
* **Dynamic Session Wiping:** Standard logout procedures automatically clear the persistent session key from the browser. This ensures that new user log-ins start with a fresh, secure, and completely isolated chat window.

### 6. ⚡ Time-Based Caching & Zero-Flicker UI
* **High-Performance Model Caching:** Synchronous, blocking queries to `/api/tags` on Ollama are optimized with a thread-safe **30-second memory cache** and a shortened 2-second timeout fallback. This eliminates sluggish page reloads and laggy logout transitions, boosting reload performance to instant, lightweight industry standards.
* **Zero-Flicker History Loader:** The initial HTML welcome placeholder card is pre-hidden server-side for authenticated sessions (`display: none`). Once the chat history API completes its async call:
  - If messages are found, they are seamlessly pre-rendered with zero layout shifts or visual flashes.
  - If the conversation is empty, the welcome greeting card is animated cleanly into view.
* **Active Loading Spinner Indicators:** Submit buttons (Sign In / Register) are embedded with smooth CSS SVG spinning elements (`@keyframes spin`) and a click lockout state during auth processing.
* **Recent Credentials Suggestion Bar:** Implements a dynamic autocompletion panel in the Sign-In card, allowing users to select from a list of recently logged-in accounts on that device.
* **Claude AI-Style Chatbox:** Features a refined, cohesive chatbox layout with a borderless user-input textarea on top and an unified actions toolbar on the bottom (bottom-left `+` file uploader, bottom-right model dropdown pill, voice toggle, and send button).

### 7. 🎙️ Premium Offline Voice Integration (STT & TTS)
* **Local Speech-to-Text (STT):** Records voice inputs directly in-browser using a custom `ScriptProcessorNode` resampler, compiles them into a standard 16-bit Mono PCM WAV file at `16000` Hz, and transcribes them fully offline via a local **OpenAI Whisper** tiny model (supporting GPU CUDA acceleration).
* **Real-Time Speech Synthesis (TTS):** Parses streamed response chunks dynamically on sentence boundaries (`.`, `?`, `!`) and feeds them into a voice synthesis queue (`SpeechSynthesisUtterance`). Readback starts *during active token generation* so you don't have to wait for the complete answer.
* **Intelligent Lifecycles:** Features clean SpeechSynthesis garbage collection handling in Google Chrome, custom Whisper silence-hallucination filters, visual pulsing/recording animations, a single unified status toggle that dynamically displays ON/OFF transitions in one dynamic indicator, and secure microphone shutdown safeguards on error.

### 8. 🏗️ Modern Modular Backend Architecture
* **Separation of Concerns:** Monolithic structures are modularized into robust, clean logic modules for vectors indexation (`services/rag.py`), offline speech transcribing (`services/audio.py`), and Ollama inference memory extraction (`services/cognitive.py`).
* **Robust Session Hygiene:** Outfitted with `db.session.rollback()` transaction safety guards inside stream generators to prevent database connection lockups in the event of local model timeout or Ollama disconnects.
* **Non-Blocking Asynchronous Extraction:** Memory facts are extracted asynchronously in a background daemon thread (`threading.Thread`) using Flask application context maps. This prevents the primary streaming interface from hanging after the text response finishes generating.
* **Resilient XML & JSON Sanitizers:** Upgraded facts extraction splits thinking blocks (`<think>...</think>`) and strips markdown code wraps to isolate structural JSON braces, resolving terminal crash logs from reasoning models like DeepSeek-R1.
* **Dynamic Blueprints Routing:** Utilizes Flask Blueprints routing to bind modular routes dynamically (`routes/auth.py`, `routes/admin.py`, `routes/documents.py`, `routes/chat.py`), leaving `app.py` as an ultra-lightweight startup orchestrator.

---

## 🛠️ Technology Stack

* **Backend:** Python, Flask, Gunicorn/Waitress (WSGI server)
* **Database:** PostgreSQL (with Docker Compose)
* **AI & Embeddings:** Ollama (`nomic-embed-text`), ChromaDB, PyPDF, Whisper Local
* **Frontend:** Vanilla HTML5, CSS3 Grid/Flexbox, ES6+ Javascript (Zero external UI libraries, pure CSS variables styling)

---

## 💿 Installation & Setup

### Prerequisites
* [Python 3.9+](https://www.python.org/downloads/) installed.
* [Ollama](https://ollama.com) installed and running locally.
* [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running.

### 1. Set Up Ollama Models
Pull the dedicated embedding model and your preferred LLMs:
```bash
# Pull the dedicated embedding model
ollama pull nomic-embed-text

# Pull LLMs for chatting (e.g. DeepSeek or Llama)
ollama pull llama3.2
ollama pull deepseek-r1:latest
```

### 2. Setup Virtual Environment & Dependencies
Set up your virtual environment and install all python dependencies:
```powershell
# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate       # On Windows (PowerShell)
source .venv/bin/activate    # On Linux/macOS

# Install dependencies
pip install -r requirements.txt
```

### 3. Spin Up the Database
Start the persistent local PostgreSQL database inside a Docker container:
```powershell
docker compose up -d
```
*(This maps host port `5433` to container port `5432` to ensure no conflict with any native Windows PostgreSQL services running on port `5432`.)*

### 4. Database Schema Migration
If upgrading from a legacy schema without user roles or email fields, ensure your local PostgreSQL database tables are fully migrated.
The app automatically performs `db.create_all()` at startup, but if you have existing tables, run a SQL update or clear the containers:
```sql
ALTER TABLE users ADD COLUMN IF NOT EXISTS first_name VARCHAR(80);
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_name VARCHAR(80);
ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR(120) UNIQUE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) NOT NULL DEFAULT 'user';
```

### 5. Run the Application

#### 🚀 Option A: Production Mode (WSGI Server) - *Recommended*
Run the production-ready high-concurrency **Waitress** WSGI server (fully optimized for Windows):
* **On Windows (PowerShell):**
  ```powershell
  $env:PYTHONUTF8=1; waitress-serve --port=5000 wsgi:app
  ```
* **On Windows (CMD):**
  ```cmd
  set PYTHONUTF8=1 && waitress-serve --port=5000 wsgi:app
  ```

#### 🛠️ Option B: Development Mode (Flask Dev Server)
Run the Flask server with debug mode enabled (recommended for code development/testing only):
* **On Windows (PowerShell):**
  ```powershell
  $env:PYTHONUTF8=1; python app.py
  ```
* **On Windows (CMD):**
  ```cmd
  set PYTHONUTF8=1 && python app.py
  ```

Open **`http://localhost:5000`** in your browser to start chatting!

---

## 🎙️ Microphone & Secure Context Notice

Due to browser security guidelines, **microphone access (`getUserMedia`) is strictly restricted to Secure Contexts** (i.e., `localhost`, `127.0.0.1`, or `https://`).
* If you access the server locally at **`http://localhost:5000`**, the voice features will work flawlessly.
* If you access the app over a local network IP (e.g., `http://192.168.1.225:5000`) on a remote device, the browser will automatically disable the microphone. Access the app via `localhost` or configure an SSL proxy (HTTPS) to enable remote mic capture.
* Toggling the **VOICE ON/OFF** button triggers a quick audio test speech to register browser-enforced **user gestures** so that streaming synthesis works smoothly.

---

## 📂 Project Structure

```text
├── app.py               # Lightweight bootstrapper & Blueprint registry
├── config.py            # Central configurations, model definitions, and system prompts
├── models.py            # SQLAlchemy database schemas (User, Conversation, ChatMessage, UserMemory)
├── requirements.txt     # Python dependencies
│
├── services/            # Decoupled business and AI logic engines
│   ├── rag.py           # ChromaDB client connection, document ingestion, and cosine queries
│   ├── audio.py         # Floating mono PCM WAV builder and Whisper offline STT transcribers
│   └── cognitive.py     # Ollama generation stream, persistent facts memory, and rolling summary
│
├── routes/              # Flask Blueprint HTTP routes
│   ├── auth.py          # /api/register, /api/login, /api/logout, /api/me (JWT token auth)
│   ├── admin.py         # /admin dashboard pages, users list API, role editor, and user cascade purger
│   ├── documents.py     # /api/documents, /api/documents/upload, /api/documents/delete
│   └── chat.py          # /api/chat stream, /api/clear, /api/transcribe, /api/models, /api/memory, /api/chat/history
│
├── templates/
│   ├── index.html       # Single-page premium glassmorphic UI with Claude-style chat input panel
│   └── admin.html       # Premium glassmorphic administrative control panel and user data purger
│
├── uploads/             # Obfuscated cryptographic document storage per user
└── chroma_db/           # Persistent ChromaDB vector database index
```
