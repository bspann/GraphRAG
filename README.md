# Flask RAG Application with Semantic Kernel

A Python Flask web application providing a chat UI for Retrieval-Augmented Generation (RAG), designed for deployment to Azure Government App Service.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           AZURE GOVERNMENT                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐       │
│  │  Azure App      │     │  Azure OpenAI   │     │  Azure AI       │       │
│  │  Service        │────►│  (GPT-4.1)      │     │  Search         │       │
│  │                 │     │                 │     │                 │       │
│  │  ┌───────────┐  │     └─────────────────┘     └─────────────────┘       │
│  │  │  Flask    │  │              ▲                       ▲                │
│  │  │  App      │  │              │                       │                │
│  │  │           │──┼──────────────┴───────────────────────┘                │
│  │  │  Semantic │  │                                                       │
│  │  │  Kernel   │  │     ┌─────────────────┐                               │
│  │  └───────────┘  │     │  Azure Cosmos   │                               │
│  │                 │────►│  DB             │                               │
│  └─────────────────┘     │  (Chat History) │                               │
│                          └─────────────────┘                               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Features

- 💬 **Chat Interface** — Clean, responsive chat UI for RAG interactions
- 🔍 **RAG with Azure AI Search** — Retrieves grounding data for contextual responses
- 🤖 **Semantic Kernel** — Orchestration layer for AI operations (future-ready for agents & MCP)
- 💾 **Chat History** — Persists conversations in Cosmos DB
- 🔐 **Azure Government Ready** — Configured for `.usgovcloudapi.net` endpoints
- 📱 **Responsive Design** — Works on desktop and mobile

## Technology Stack

| Component | Technology |
|-----------|------------|
| Frontend | Flask + Jinja2 + Tailwind CSS |
| Backend | Python 3.11+ with async/await |
| AI Orchestration | Semantic Kernel |
| LLM | Azure OpenAI GPT-4.1 |
| Search | Azure AI Search |
| Database | Azure Cosmos DB |
| Hosting | Azure App Service |

## Prerequisites

- Python 3.11+
- Azure Government subscription with:
  - Azure OpenAI resource with GPT-4.1 deployment
  - Azure AI Search service
  - Azure Cosmos DB account
- Azure CLI configured for Azure Government

## Quick Start

### 1. Clone and Setup

```bash
cd flask-rag-app
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and update with your Azure Government resources:

```bash
cp .env.example .env
# Edit .env with your values
```

### 3. Run Locally

```bash
python run.py
```

Visit http://localhost:5000

## Project Structure

```
flask-rag-app/
├── app/
│   ├── __init__.py           # Flask app factory
│   ├── routes.py             # API routes
│   ├── services/
│   │   ├── __init__.py
│   │   ├── kernel_service.py # Semantic Kernel setup
│   │   ├── search_service.py # Azure AI Search client
│   │   └── cosmos_service.py # Cosmos DB chat history
│   ├── templates/
│   │   ├── base.html
│   │   └── chat.html
│   └── static/
│       ├── css/
│       │   └── styles.css
│       └── js/
│           └── chat.js
├── config.py                  # Configuration
├── requirements.txt
├── Dockerfile
├── .env.example
└── run.py
```

## Deployment to Azure Government

### Using Azure CLI

```bash
# Login to Azure Government
az cloud set --name AzureUSGovernment
az login

# Create App Service
az webapp up --name your-app-name \
  --resource-group your-rg \
  --runtime "PYTHON:3.11" \
  --sku B1

# Configure app settings from .env
az webapp config appsettings set \
  --name your-app-name \
  --resource-group your-rg \
  --settings @appsettings.json
```

### Using Docker

```bash
docker build -t flask-rag-app .
docker run -p 5000:5000 --env-file .env flask-rag-app
```

## Future Enhancements

This application is designed to evolve with Semantic Kernel:

- **Agent SDK Integration** — Multi-agent orchestration for complex workflows
- **MCP Server Support** — Connect to external tools and data sources via Model Context Protocol
- **Streaming Responses** — Real-time token streaming for better UX
- **Multi-turn Memory** — Enhanced conversation context management

## Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint | `https://xxx.openai.azure.us/` |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI API key | `your-key` |
| `AZURE_OPENAI_DEPLOYMENT` | GPT-4.1 deployment name | `gpt-41` |
| `AZURE_SEARCH_ENDPOINT` | Azure AI Search endpoint | `https://xxx.search.windows.us` |
| `AZURE_SEARCH_KEY` | Azure AI Search admin key | `your-key` |
| `AZURE_SEARCH_INDEX` | Search index name | `documents` |
| `COSMOS_ENDPOINT` | Cosmos DB endpoint | `https://xxx.documents.azure.us:443/` |
| `COSMOS_KEY` | Cosmos DB key | `your-key` |
| `COSMOS_DATABASE` | Database name | `ragapp` |
| `COSMOS_CONTAINER` | Container name | `chathistory` |

## License

MIT
