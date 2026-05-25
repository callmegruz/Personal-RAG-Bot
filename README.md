# 🤖 Personal RAG Bot & Local LLM Assistant

### 🔒 Absolute Data Privacy. Zero Cloud Dependencies. Production-Grade Local Architecture.

A premium, fully local **Retrieval-Augmented Generation (RAG)** chatbot and AI assistant. This application allows you to upload documents (PDF, TXT, MD) and chat with them securely on your local network. Your data, vector embeddings, document indexes, and conversation history never leave your physical machine.

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

### 3. 🛡️ Defense-in-Depth File Security
* **Deterministic SHA-256 Filename Obfuscation:** Stored files are renamed on the server filesystem using a deterministic cryptographic hash (e.g., `uploads/2e34fa...a32b.txt`). This completely prevents **Directory / Path Traversal** exploits (like `../../../etc/passwd` injection) and remote code execution while keeping the database logical key human-readable.
* **Strict Upload Protection:** Implements an immediate **10MB upload limit** checked on both the frontend (browser toast notification) and backend (Flask request size constraints with graceful `413` JSON handler).

### 4. 🎨 Premium Glassmorphic UI/UX
* Harmonious dark theme using CSS custom tokens and glassmorphism with two dynamic presets (Emerald and Magma themes).
* Drag-and-drop file indexing overlay.
* Dynamic context status pills showing active systems (System prompt, Memory state, RAG status, Active model).
* Sleek modal dialogues for critical action confirmations.
* **Claude AI-Style Chatbox:** Features a refined, cohesive chatbox layout with a borderless user-input textarea on top and an unified actions toolbar on the bottom (bottom-left `+` file uploader, bottom-right model dropdown pill, voice toggle, and send button).

### 5. 🎙️ Premium Offline Voice Integration (STT & TTS)
* **Local Speech-to-Text (STT):** Records voice inputs directly in-browser using a custom `ScriptProcessorNode` resampler, compiles them into a standard 16-bit Mono PCM WAV file at `16000` Hz, and transcribes them fully offline via a local **OpenAI Whisper** tiny model (supporting GPU CUDA acceleration).
* **Real-Time Speech Synthesis (TTS):** Parses streamed response chunks dynamically on sentence boundaries (`.`, `?`, `!`) and feeds them into a voice synthesis queue (`SpeechSynthesisUtterance`). Readback starts *during active token generation* so you don't have to wait for the complete answer.
* **Intelligent Lifecycles:** Features clean SpeechSynthesis garbage collection handling in Google Chrome, custom Whisper silence-hallucination filters, visual pulsing/recording animations, a quick-mute header toggle, and secure microphone shutdown safeguards on error.

### 6. 🏗️ Modern Modular Backend Architecture
* **Separation of Concerns:** Deconstructs the monolithic Flask layout into robust, clean logic modules for vectors indexation (`services/rag.py`), offline speech transcribing (`services/audio.py`), and Ollama inference memory extraction (`services/cognitive.py`).
* **Decoupled Configuration & Models:** Centralizes system configuration, LLM parameters, and system prompts in `config.py`, separating databases ORM models completely into `models.py`.
* **Dynamic Blueprints Routing:** Utilizes Flask Blueprints routing to bind modular routes dynamically (`routes/auth.py`, `routes/documents.py`, `routes/chat.py`), leaving `app.py` as an ultra-lightweight startup orchestrator (under 70 lines of code).

---

## 🛠️ Technology Stack

* **Backend:** Python, Flask, Gunicorn/Waitress (WSGI server)
* **AI & Embeddings:** Ollama, ChromaDB, PyPDF
* **Frontend:** Vanilla HTML5, CSS3 Grid/Flexbox, ES6+ Javascript (Zero external UI libraries)

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

### 4. Run the Application

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
* Toggling the **VOICE ON** button triggers a quick audio test speech to register browser-enforced **user gestures** so that streaming synthesis works smoothly.

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
│   ├── documents.py     # /api/documents, /api/documents/upload, /api/documents/delete
│   └── chat.py          # /api/chat stream, /api/clear, /api/transcribe, /api/models, /api/memory
│
├── templates/
│   └── index.html       # Single-page premium glassmorphic UI with Claude-style chat input panel
│
├── uploads/             # Obfuscated cryptographic document storage (Safe disk)
└── chroma_db/           # Persistent ChromaDB vector database index
```
