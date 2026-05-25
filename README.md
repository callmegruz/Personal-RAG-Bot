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

### 5. 🎙️ Premium Offline Voice Integration (STT & TTS)
* **Local Speech-to-Text (STT):** Records voice inputs directly in-browser using a custom `ScriptProcessorNode` resampler, compiles them into a standard 16-bit Mono PCM WAV file at `16000` Hz, and transcribes them fully offline via a local **OpenAI Whisper** tiny model (supporting GPU CUDA acceleration).
* **Real-Time Speech Synthesis (TTS):** Parses streamed response chunks dynamically on sentence boundaries (`.`, `?`, `!`) and feeds them into a voice synthesis queue (`SpeechSynthesisUtterance`). Readback starts *during active token generation* so you don't have to wait for the complete answer.
* **Intelligent Lifecycles:** Features clean SpeechSynthesis garbage collection handling in Google Chrome, custom Whisper silence-hallucination filters, visual pulsing/recording animations, a quick-mute header toggle, and secure microphone shutdown safeguards on error.

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

### 1. Set Up Ollama Models
Pull your favorite local LLMs and the embedding model:
```bash
# Pull the dedicated embedding model
ollama pull nomic-embed-text

# Pull LLMs for chatting (e.g. DeepSeek or Llama)
ollama pull llama3.2
ollama pull deepseek-r1:latest
```

### 2. Clone & Install Dependencies
Clone the repository, set up a virtual environment, and install dependencies:
```bash
# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate       # On Windows
source .venv/bin/activate    # On Linux/macOS

# Install dependencies
pip install -r requirements.txt
```

### 3. Run the App
Start the Flask local development server:
```bash
python app.py
```
Open **`http://localhost:5000`** (or your local IP address `http://192.168.x.x:5000` to share with other devices on your home/office network!).

---

## 🎙️ Microphone & Secure Context Notice

Due to browser security guidelines, **microphone access (`getUserMedia`) is strictly restricted to Secure Contexts** (i.e., `localhost`, `127.0.0.1`, or `https://`).
* If you access the server locally at **`http://localhost:5000`**, the voice features will work flawlessly.
* If you access the app over a local network IP (e.g., `http://192.168.1.225:5000`) on a remote device, the browser will automatically disable the microphone. Access the app via `localhost` or configure an SSL proxy (HTTPS) to enable remote mic capture.
* Toggling the **VOICE ON** button triggers a quick audio test speech to register browser-enforced **user gestures** so that streaming synthesis works smoothly.

---

## 📂 Project Structure
```
├── app.py               # Flask application with security and context managers
├── requirements.txt     # Python dependencies
├── templates/
│   └── index.html       # Single-page glassmorphic UI & frontend validators
├── uploads/             # Obfuscated cryptographic document storage (Safe disk)
└── chroma_db/           # Persistent ChromaDB vector database index
```
