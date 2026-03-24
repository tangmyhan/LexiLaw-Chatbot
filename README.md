# 🏛️ LexiLaw - AI Assistant & Knowledge Graph for Vietnam Labor Law

**LexiLaw** is an advanced RAG (Retrieval-Augmented Generation) system specifically designed to consult and resolve legal issues related to the Vietnam Labor Law.

The system leverages a modern architecture with a high-speed React/Vite Frontend, smooth asynchronous FastAPI Backend, and the power of leading LLM models, delivering highly accurate, transparent answers fully based on current legal documents.

---

## ✨ Key Features

- 🎯 **Accurate Legal Consultation:** Provides information and answers questions based on actual labor law provisions.
- 🎨 **Premium & Modern UI:** Optimized user experience with a **Side-by-Side layout**, allowing parallel interaction between the Chatbot frame and the Legal Graph map intuitively.
- 🕸️ **Knowledge Graph Visualization:** Utilizes **Sigma.js** combined with **Neo4j** to vividly display and smoothly interact with the network of laws, labor codes, and related regulations.
- 🔍 **Hybrid Search RAG:** Combines Dense Vector (semantic) and Sparse Vector (BM25 keyword) search using **Qdrant** to retrieve the most accurate context.
- 🇻🇳 **Multilingual Re-ranking:** Uses **Cohere Rerank 3.5** to optimize search result rankings for Vietnamese/Japanese text.
- ⚡ **Real-time Streaming:** Integrates Server-Sent Events (SSE) technology for zero-latency instant responses (typing effect).
- 🔄 **Multi-Session Context Management:** Securely stores chat history using **Redis** to maintain context for continuous chat flows.

---

## 🛠 Technology Stack

### 🎨 Frontend (UI & Graph Visualization)
- **Core:** React 19, Vite
- **Graph Visualization:** Sigma.js v3, Graphology, ForceAtlas2, @react-sigma
- **Styling:** Tailwind CSS, Lucide React
- **State Management:** Zustand, Immer, Use-immer
- **Markdown Rendering:** React Markdown

### 🧠 Backend (API, AI & Data)
- **Core:** FastAPI (Python 3.10+)
- **LLM Engine:** OpenAI API (`gpt-4o-mini` or other models)
- **Embeddings:** BAAI/bge-m3 (via `SentenceTransformers`)
- **Vector Database:** Qdrant (Cloud/Local)
- **Graph Database:** Neo4j (Aura Cloud/Local)
- **Caching & Memory:** Redis (Async)

---

## 📦 System Architecture (Dockerized)

The project is configured with Docker and Docker Compose for easy deployment through 3 main services:
1. **Frontend:** Nginx serving React/Vite static files.
2. **Backend:** FastAPI hosted via Uvicorn.
3. **Redis:** Caching and chat history storage.
*(Note: Qdrant and Neo4j are configured to use Cloud instances but can be set up to run local mapping via `docker-compose`)*.

---

## 🚦 Running the Project with Docker

The simplest way to run the entire project is using Docker. Please install [Docker](https://www.docker.com/) and [Docker Compose](https://docs.docker.com/compose/) before proceeding.

### 1. Environment Variables Configuration
Create a `.env` file inside the `backend/` directory with the following settings:

```env
# App Config
APP_NAME="LexiLaw RAG Chatbot"
DEBUG=False
ALLOW_ORIGINS="*"

# Qdrant Cloud / Local
QDRANT_URL="<Your_Qdrant_URL>"
QDRANT_API_KEY="<Your_Qdrant_API_Key>"
COLLECTION_NAME="legal_laws"
VECTOR_SEARCH_TOP_K=10

# OpenAi LLM
OPENAI_API_KEY="<Your_OpenAI_API_Key>"
OPENAI_MODEL="gpt-4o-mini"

# Cohere Rerank
COHERE_API_KEY="<Your_Cohere_API_Key>"

# Redis
REDIS_URL="redis://redis:6379/0"

# Neo4j (GraphRAG)
NEO4J_URI="<Neo4j_URI>"
NEO4J_USERNAME="<Neo4j_User>"
NEO4J_PASSWORD="<Neo4j_Password>"
NEO4J_DATABASE="neo4j"
```

### 2. Deploy with Docker Compose

At the project's root directory (where the `docker-compose.yml` file is located), run the command:

```bash
docker-compose up --build -d
```

The services will automatically install dependencies and start:
- **Frontend** runs at: `http://localhost:3000`
- **Backend API Docs** run at: `http://localhost:8000/docs`

---

## 💻 Running the Project Manually (Development Mode)

If you want to debug directly without using Docker, follow these steps.

### 1. Start Redis (Required)
You need a running Redis instance on port `6379`.
If using pre-installed Docker: 
```bash
docker run -d -p 6379:6379 redis:7-alpine
```

### 2. Run Backend
Open Terminal, navigate to the `backend/` directory and execute:

```bash
# Create and activate virtual environment (Recommended)
python -m venv myenv
source myenv/bin/activate  # On Windows: .\myenv\Scripts\activate

# Install libraries
pip install -r requirements.txt

# Make sure you change the REDIS_URL line in the .env file to LOCAL:
# REDIS_URL="redis://localhost:6379/0"

# Start Uvicorn
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. Run Frontend
Open a new Terminal, navigate to the `frontend/` directory and execute:

```bash
# Install Nodejs libraries
npm install

# Run Vite development server
npm run dev
```
Open your browser and navigate to the URL announced by Vite (usually `http://localhost:5173`).

---

## 📂 Main Source Code Structure

```text
LawRAG/
│
├── frontend/                 # User Interface
│   ├── src/components/       # React components: ChatUI, GraphViewer, Sidebar...
│   ├── src/api/              # API call configurations to Backend
│   ├── Dockerfile            # Frontend container configuration (Node + Nginx)
│   └── package.json
│
├── backend/                  # API and Processing Logic
│   ├── app/
│   │   ├── agents/           # Bot Logic: Researcher, Router, Prompts
│   │   ├── core/             # General config (.env loader, neo4j, qdrant, redis, llm)
│   │   ├── services/         # Layer calling LLM model, embedding, retrieval
│   │   ├── api.py            # Routes / Endpoints declaration
│   │   └── main.py           # Init FastAPI app
│   ├── worker/               # Source code for offline data ingestion
│   ├── Dockerfile            # Backend container configuration (Python)
│   └── requirements.txt
│
└── docker-compose.yml        # System-wide service integration
```

---

## ⚖️ License & Disclaimer

Although the LexiLaw system uses advanced search technology based on Labor Law documents, AI-generated consultations are strictly **for reference purposes only**. You should cross-check and verify legality with Competent Authorities or Professional Lawyers for important decisions.

This project serves academic and research purposes to apply **GraphRAG (Knowledge Graph + RAG)** technology with an interactive interface and powerful visualization technology.
