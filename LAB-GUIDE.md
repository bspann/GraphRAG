---
stepsCompleted: [1, 2, 3, 4, 5]
lastStep: 'complete'
completed_date: 2026-02-03
status: 'ready-for-review'
date: 2026-02-03
user_name: Brian
lab_title: 'Deploy a Flask RAG Application with Semantic Kernel to Azure Government'
duration: 120
skill_level: 'intermediate'
azure_services: ['app-service', 'cosmos-db', 'openai', 'ai-search']
---

# Hands-On Lab: Deploy a Flask RAG Application with Semantic Kernel to Azure Government

**Duration:** 2 hours  
**Skill Level:** Intermediate  
**Last Updated:** 2026-02-03  
**Status:** ✅ Ready for Review

---

## Overview

In this hands-on lab, you'll deploy a production-ready Retrieval-Augmented Generation (RAG) chat application to Azure Government. The application uses Flask as the web framework, Microsoft Semantic Kernel for AI orchestration, Azure OpenAI for chat completion, Azure AI Search for document retrieval, and Cosmos DB for chat history persistence.

This lab demonstrates modern cloud-native patterns for building intelligent applications that are ready for future enhancements like multi-agent orchestration and MCP (Model Context Protocol) integrations.

### Learning Objectives

By the end of this lab, you will be able to:

1. **Configure and deploy a Flask application** to Azure Government App Service with proper environment configuration
2. **Integrate Microsoft Semantic Kernel** with Azure OpenAI for AI-powered chat functionality
3. **Implement a RAG pattern** using Azure AI Search for context retrieval and grounding
4. **Persist chat history** using Azure Cosmos DB with proper session management
5. **Apply production best practices** including logging, error handling, and secure configuration

### Target Audience

Developers and DevOps engineers who need to deploy AI-powered web applications to Azure Government. Participants should have basic experience with:

- Python and Flask web development
- Azure portal and CLI basics
- REST APIs and async programming concepts

### Skill Level

**Intermediate** — This lab assumes familiarity with:

- Python 3.11+ and virtual environments
- Basic Flask application structure
- Azure App Service concepts
- Environment variable configuration

### Duration

**2 hours** — Self-paced or instructor-led

### Success Criteria

Participants successfully deploy the Flask RAG application to Azure Government App Service and can:
- Send chat messages through the web UI
- Receive AI-generated responses grounded in search results
- View chat history persisted across sessions

---

## Prerequisites

Before starting this lab, ensure you have the following:

### Azure Subscription

| Requirement | Description | Validation |
|-------------|-------------|------------|
| Azure Government Subscription | Active subscription with contributor access | `az account show` |
| Azure OpenAI Access | Approved access with GPT-4.1 deployment | Check Azure Portal |
| Azure AI Search | Search service with an index | Check Azure Portal |

### Required Tooling

| Tool | Version | Description | Validation |
|------|---------|-------------|------------|
| Python | 3.11+ | Python runtime | `python --version` |
| Azure CLI | 2.50+ | Azure management CLI | `az version` |
| Git | 2.x+ | Version control | `git --version` |
| VS Code | Latest | Development IDE | `code --version` |

### Azure Resources (Pre-provisioned or Create During Lab)

| Resource | Purpose | Notes |
|----------|---------|-------|
| Azure OpenAI | GPT-4.1 chat completion | Deployment name: `gpt-41` |
| Azure AI Search | Document retrieval | With populated index |
| Azure Cosmos DB | Chat history storage | Will be created |
| Azure App Service | Application hosting | Will be created |

### Environment Validation Script

Run this script to validate your environment:

```powershell
# Lab Environment Validation
Write-Host "🔍 Validating Flask RAG Lab Prerequisites..." -ForegroundColor Cyan

# Check Python
$pythonVersion = python --version 2>&1
if ($pythonVersion -match "3\.(1[1-9]|[2-9][0-9])") {
    Write-Host "✅ Python: $pythonVersion" -ForegroundColor Green
} else {
    Write-Host "❌ Python 3.11+ required. Found: $pythonVersion" -ForegroundColor Red
}

# Check Azure CLI
$azVersion = az version --query '"azure-cli"' -o tsv 2>$null
if ($azVersion) {
    Write-Host "✅ Azure CLI: $azVersion" -ForegroundColor Green
} else {
    Write-Host "❌ Azure CLI not found" -ForegroundColor Red
}

# Check Azure Government
$cloud = az cloud show --query name -o tsv 2>$null
if ($cloud -eq "AzureUSGovernment") {
    Write-Host "✅ Azure Cloud: $cloud" -ForegroundColor Green
} else {
    Write-Host "⚠️  Azure Cloud: $cloud (should be AzureUSGovernment)" -ForegroundColor Yellow
}

# Check Git
$gitVersion = git --version 2>$null
if ($gitVersion) {
    Write-Host "✅ Git: $gitVersion" -ForegroundColor Green
} else {
    Write-Host "❌ Git not found" -ForegroundColor Red
}

Write-Host "`n✨ Validation complete!" -ForegroundColor Cyan
```

---

## Architecture

This lab deploys a Flask web application that implements the RAG (Retrieval-Augmented Generation) pattern using Azure services.

### Components

| Component | Azure Service | Purpose |
|-----------|---------------|---------|
| Web Application | Azure App Service | Hosts Flask application |
| AI Orchestration | Semantic Kernel + Azure OpenAI | Chat completion with GPT-4.1 |
| Document Retrieval | Azure AI Search | Semantic search for context |
| Chat History | Azure Cosmos DB | Session-based conversation storage |

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           AZURE GOVERNMENT                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│    ┌─────────────────────────────────────────────────────────────────┐     │
│    │                     AZURE APP SERVICE                           │     │
│    │                                                                  │     │
│    │   ┌──────────────────────────────────────────────────────────┐  │     │
│    │   │                    FLASK APPLICATION                      │  │     │
│    │   │                                                           │  │     │
│    │   │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐      │  │     │
│    │   │  │   Routes    │  │   Semantic  │  │   Services  │      │  │     │
│    │   │  │  (Web UI)   │──│   Kernel    │──│  (Cosmos,   │      │  │     │
│    │   │  │             │  │             │  │   Search)   │      │  │     │
│    │   │  └─────────────┘  └─────────────┘  └─────────────┘      │  │     │
│    │   │                          │                │              │  │     │
│    │   └──────────────────────────┼────────────────┼──────────────┘  │     │
│    │                              │                │                  │     │
│    └──────────────────────────────┼────────────────┼──────────────────┘     │
│                                   │                │                         │
│              ┌────────────────────┘                └────────────────┐       │
│              ▼                                                      ▼       │
│    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐       │
│    │  Azure OpenAI   │    │  Azure AI       │    │  Azure Cosmos   │       │
│    │  (GPT-4.1)      │    │  Search         │    │  DB             │       │
│    │                 │    │                 │    │                 │       │
│    │  Chat           │    │  Document       │    │  Chat History   │       │
│    │  Completion     │    │  Retrieval      │    │  Storage        │       │
│    └─────────────────┘    └─────────────────┘    └─────────────────┘       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

                    User Request Flow:
                    
    ┌───────┐    1. User sends question
    │ User  │◄───────────────────────────────────────────────────────────────┐
    │       │    5. Returns AI response with sources                         │
    └───┬───┘                                                                │
        │                                                                    │
        ▼                                                                    │
    ┌───────────────┐   2. Search for    ┌───────────────┐                  │
    │ Flask App     │──────relevant────►│ Azure AI      │                  │
    │               │      context       │ Search        │                  │
    │               │◄───────────────────│               │                  │
    │               │   Return docs      └───────────────┘                  │
    │               │                                                        │
    │               │   3. Send context  ┌───────────────┐                  │
    │               │─────+ question───►│ Azure OpenAI  │                  │
    │               │                    │ (GPT-4.1)     │                  │
    │               │◄───────────────────│               │                  │
    │               │   Return response  └───────────────┘                  │
    │               │                                                        │
    │               │   4. Save to       ┌───────────────┐                  │
    │               │────history───────►│ Cosmos DB     │──────────────────┘
    └───────────────┘                    └───────────────┘
```

### Data Flow

1. **User submits question** through the web chat interface
2. **Azure AI Search** retrieves relevant documents based on the query
3. **Semantic Kernel** combines context + question and sends to Azure OpenAI
4. **Azure OpenAI (GPT-4.1)** generates a contextual response
5. **Cosmos DB** stores the conversation for history
6. **Response** returned to user with source citations

---

## Lab Exercises

> **Note:** All exercises assume you are working from an Azure Government-connected development environment.

---

### Exercise 1: Clone and Configure the Application

**Estimated Time:** 15 minutes

#### Objective

Clone the Flask RAG application repository and configure it for your Azure Government environment.

#### Steps

1. Open a terminal and navigate to your projects directory:

   ```powershell
   cd C:\Projects
   ```

2. Clone or copy the Flask RAG application:

   ```powershell
   # If the app is in a Git repository
   git clone <your-repo-url> flask-rag-app
   
   # Or copy from the demos folder
   Copy-Item -Recurse "path\to\demos\flask-rag-app" "C:\Projects\flask-rag-app"
   
   cd flask-rag-app
   ```

3. Create and activate a Python virtual environment:

   ```powershell
   python -m venv .venv
   .venv\Scripts\activate
   ```

4. Install dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

5. Copy the environment template and configure:

   ```powershell
   Copy-Item .env.example .env
   code .env
   ```

6. Update the `.env` file with your Azure Government resource details:

   ```bash
   # Flask Configuration
   FLASK_ENV=development
   FLASK_DEBUG=1
   SECRET_KEY=your-secret-key-here-change-this
   
   # Azure OpenAI (Azure Government)
   AZURE_OPENAI_ENDPOINT=https://your-openai-resource.openai.azure.us/
   AZURE_OPENAI_API_KEY=your-azure-openai-api-key
   AZURE_OPENAI_DEPLOYMENT=gpt-41
   AZURE_OPENAI_API_VERSION=2024-06-01
   
   # Azure AI Search (Azure Government)
   AZURE_SEARCH_ENDPOINT=https://your-search-service.search.windows.us
   AZURE_SEARCH_KEY=your-search-admin-key
   AZURE_SEARCH_INDEX=documents
   
   # Azure Cosmos DB (will be created - leave empty for now)
   COSMOS_ENDPOINT=
   COSMOS_KEY=
   COSMOS_DATABASE=ragapp
   COSMOS_CONTAINER=chathistory
   ```

   > **Note:** We'll add Cosmos DB credentials after creating the resource in Exercise 3.

#### Validation

```powershell
# Verify dependencies installed
pip list | Select-String "semantic-kernel|flask|azure"

# Verify .env exists
Test-Path .env
```

**Expected Result:** Dependencies listed, `.env` file exists.

✅ **Checkpoint:** Application cloned and configured.

#### Troubleshooting

**Issue:** `pip install` fails with SSL errors
**Symptom:** SSL certificate verification failed
**Solution:** Ensure your proxy/firewall allows PyPI access, or use `pip install --trusted-host pypi.org`

---

### Exercise 2: Understand the Application Structure

**Estimated Time:** 15 minutes

#### Objective

Explore the Flask RAG application architecture and understand how Semantic Kernel orchestrates AI operations.

#### Steps

1. Open the project in VS Code:

   ```powershell
   code .
   ```

2. Review the application structure:

   ```
   flask-rag-app/
   ├── app/
   │   ├── __init__.py           # Flask app factory with logging
   │   ├── routes.py             # Web UI and API endpoints
   │   └── services/
   │       ├── kernel_service.py # Semantic Kernel AI orchestration
   │       ├── search_service.py # Azure AI Search client
   │       └── cosmos_service.py # Cosmos DB chat history
   ├── config.py                 # Configuration management
   ├── run.py                    # Application entry point
   └── requirements.txt
   ```

3. Examine the Semantic Kernel service in `app/services/kernel_service.py`:

   Key components:
   - **Kernel initialization** — Creates Semantic Kernel with Azure OpenAI
   - **Chat method** — Combines context + history for RAG responses
   - **Future hooks** — Placeholders for Agent SDK and MCP integration

   ```python
   # The chat method combines RAG context with chat history
   async def chat(self, user_message: str, context: str = "", chat_history: Optional[list] = None):
       # Build system message with retrieved context
       system_message = self.system_prompt
       if context:
           system_message += f"\n\n## Retrieved Context:\n{context}"
       
       # Add conversation history for multi-turn context
       # Generate response using Azure OpenAI
   ```

4. Review the RAG flow in `app/routes.py`:

   ```python
   async def process_chat(...):
       # 1. Search for relevant documents
       search_results = await search_service.search(user_message)
       
       # 2. Get chat history
       chat_history = await cosmos_service.get_chat_history(session_id)
       
       # 3. Generate response with Semantic Kernel
       response = await kernel_service.chat(user_message, context, chat_history)
       
       # 4. Save to history
       await cosmos_service.save_message(session_id, 'user', user_message)
       await cosmos_service.save_message(session_id, 'assistant', response)
   ```

5. Review the chat UI template in `app/templates/chat.html`:

   - Responsive design with Tailwind CSS
   - JavaScript handles async message sending
   - Markdown rendering for AI responses
   - Source citation expansion

#### Validation

Review these files and understand their roles:
- [ ] `app/__init__.py` — App factory and logging configuration
- [ ] `app/services/kernel_service.py` — Semantic Kernel integration
- [ ] `app/routes.py` — API endpoints and RAG orchestration
- [ ] `config.py` — Environment-based configuration

✅ **Checkpoint:** Application architecture understood.

---

### Exercise 3: Deploy Azure Infrastructure

**Estimated Time:** 25 minutes

#### Objective

Deploy the required Azure infrastructure using Terraform, including Cosmos DB and App Service.

#### Steps

1. Navigate to the infrastructure directory:

   ```powershell
   cd infra
   ```

2. Ensure Azure CLI is configured for Azure Government:

   ```powershell
   az cloud set --name AzureUSGovernment
   az login
   ```

3. Create a resource group (if not exists):

   ```powershell
   $rg = "rg-ragflask-dev"
   $location = "usgovvirginia"
   
   az group create --name $rg --location $location
   ```

4. Copy and configure Terraform variables:

   ```powershell
   Copy-Item terraform.tfvars.example terraform.tfvars
   code terraform.tfvars
   ```

5. Update `terraform.tfvars` with your values:

   ```hcl
   app_name            = "ragflask"
   environment         = "dev"
   location            = "usgovvirginia"
   resource_group_name = "rg-ragflask-dev"
   
   # Your existing Azure OpenAI details
   azure_openai_endpoint   = "https://your-openai.openai.azure.us/"
   azure_openai_key        = "your-key"
   azure_openai_deployment = "gpt-41"
   
   # Your existing Azure AI Search details
   azure_search_endpoint = "https://your-search.search.windows.us"
   azure_search_key      = "your-key"
   azure_search_index    = "documents"
   ```

6. Initialize and deploy with Terraform:

   ```powershell
   terraform init
   terraform plan -out=tfplan
   
   # Review the plan, then apply
   terraform apply tfplan
   ```

7. Capture the outputs:

   ```powershell
   # Get Cosmos DB endpoint
   $cosmosEndpoint = terraform output -raw cosmos_endpoint
   
   # Get App Service name
   $appName = terraform output -raw app_service_name
   
   # Get App URL
   $appUrl = terraform output -raw app_service_url
   
   Write-Host "Cosmos Endpoint: $cosmosEndpoint"
   Write-Host "App Service: $appName"
   Write-Host "App URL: $appUrl"
   ```

8. Update your local `.env` with Cosmos DB credentials:

   ```powershell
   cd ..
   
   # Get Cosmos key from Azure
   $cosmosAccount = "cosmos-ragflask-dev"
   $cosmosKey = az cosmosdb keys list `
       --name $cosmosAccount `
       --resource-group $rg `
       --query primaryMasterKey -o tsv
   
   Write-Host "Add these to your .env file:"
   Write-Host "COSMOS_ENDPOINT=$cosmosEndpoint"
   Write-Host "COSMOS_KEY=$cosmosKey"
   ```

   Update `.env`:

   ```bash
   COSMOS_ENDPOINT=https://cosmos-ragflask-dev.documents.azure.us:443/
   COSMOS_KEY=your-cosmos-key-from-above
   ```

#### Validation

```powershell
# Verify resources created
az resource list --resource-group $rg --output table
```

**Expected Result:** App Service, Cosmos DB account, and App Service Plan listed.

✅ **Checkpoint:** Azure infrastructure deployed.

#### Troubleshooting

**Issue:** Terraform fails with permission error
**Symptom:** `AuthorizationFailed`
**Solution:** Ensure you have Contributor role on the subscription

**Issue:** Cosmos DB name already exists
**Symptom:** `Resource already exists`
**Solution:** Cosmos DB names are globally unique — change `app_name` in tfvars

---

### Exercise 4: Test Locally

**Estimated Time:** 15 minutes

#### Objective

Run the Flask application locally to verify all Azure service integrations work correctly.

#### Steps

1. Return to the application root and activate the virtual environment:

   ```powershell
   cd C:\Projects\flask-rag-app
   .venv\Scripts\activate
   ```

2. Verify your `.env` has all required values:

   ```powershell
   Get-Content .env | Select-String "ENDPOINT|KEY" | ForEach-Object {
       $line = $_.Line
       if ($line -match "=.+") {
           $name = $line.Split("=")[0]
           Write-Host "✅ $name configured" -ForegroundColor Green
       } else {
           $name = $line.Split("=")[0]
           Write-Host "❌ $name missing" -ForegroundColor Red
       }
   }
   ```

3. Run the application:

   ```powershell
   python run.py
   ```

   You should see:

   ```
   ============================================================
   Flask RAG Application Starting
   ============================================================
   Semantic Kernel service initialized
   Cosmos DB service initialized
   Azure AI Search service initialized
   All services initialized successfully
   ============================================================
   Flask RAG Application Ready
   ============================================================
    * Running on http://127.0.0.1:5000
   ```

4. Open a browser to http://localhost:5000

5. Test the chat interface:

   - Type a question related to your search index content
   - Verify you receive an AI-generated response
   - Check that sources are displayed (if citations are enabled)
   - Send a follow-up question to test conversation history

6. Test the health endpoint:

   ```powershell
   Invoke-RestMethod -Uri "http://localhost:5000/health"
   ```

   Expected response:

   ```json
   {
       "status": "healthy",
       "timestamp": "2026-02-03T..."
   }
   ```

7. Stop the local server with `Ctrl+C`.

#### Validation

- [ ] Application starts without errors
- [ ] Chat UI loads at http://localhost:5000
- [ ] Questions receive AI-generated responses
- [ ] Health endpoint returns healthy status

✅ **Checkpoint:** Local testing successful.

#### Troubleshooting

**Issue:** "Configuration error: AZURE_OPENAI_ENDPOINT is required"
**Symptom:** Application fails to start
**Solution:** Verify all required values in `.env` are set correctly

**Issue:** "Failed to initialize Cosmos service"
**Symptom:** Cosmos DB connection error
**Solution:** Verify Cosmos endpoint and key in `.env`, ensure firewall allows access

**Issue:** Search returns no results
**Symptom:** AI responses don't reference documents
**Solution:** Verify Azure AI Search index name and that it contains documents

---

### Exercise 5: Deploy to Azure App Service

**Estimated Time:** 20 minutes

#### Objective

Deploy the Flask application to Azure Government App Service.

#### Steps

1. Ensure you're in the application root:

   ```powershell
   cd C:\Projects\flask-rag-app
   ```

2. Deploy using the provided script:

   ```powershell
   .\infra\deploy.ps1 `
       -AppServiceName "app-ragflask-dev" `
       -ResourceGroupName "rg-ragflask-dev"
   ```

   The script will:
   - Create a deployment package
   - Upload to App Service
   - Display the application URL

3. Alternatively, deploy using Azure CLI directly:

   ```powershell
   # Create deployment package
   $zipPath = "deploy.zip"
   
   # Compress application files (excluding dev files)
   Compress-Archive -Path @(
       "app",
       "config.py", 
       "requirements.txt",
       "run.py"
   ) -DestinationPath $zipPath -Force
   
   # Deploy to App Service
   az webapp deploy `
       --resource-group "rg-ragflask-dev" `
       --name "app-ragflask-dev" `
       --src-path $zipPath `
       --type zip
   ```

4. Verify the deployment:

   ```powershell
   $appUrl = az webapp show `
       --resource-group "rg-ragflask-dev" `
       --name "app-ragflask-dev" `
       --query "defaultHostName" -o tsv
   
   Write-Host "Application URL: https://$appUrl"
   ```

5. Test the deployed application:

   ```powershell
   # Health check
   Invoke-RestMethod -Uri "https://$appUrl/health"
   
   # Open in browser
   Start-Process "https://$appUrl"
   ```

6. Monitor the deployment logs:

   ```powershell
   az webapp log tail `
       --resource-group "rg-ragflask-dev" `
       --name "app-ragflask-dev"
   ```

7. Test the chat functionality in production:

   - Open the application URL in your browser
   - Send a test message
   - Verify the response includes relevant context
   - Check that chat history persists across page refreshes

#### Validation

```powershell
# Verify app is running
$response = Invoke-WebRequest -Uri "https://$appUrl/health" -UseBasicParsing
$response.StatusCode
```

**Expected Result:** Status code 200.

✅ **Checkpoint:** Application deployed to Azure Government.

#### Troubleshooting

**Issue:** Application returns 500 error
**Symptom:** Internal server error on first request
**Solution:** Check App Service logs: `az webapp log tail --name app-ragflask-dev --resource-group rg-ragflask-dev`

**Issue:** "Module not found" errors
**Symptom:** Import errors in logs
**Solution:** Ensure `requirements.txt` is included in deployment package

---

### Exercise 6: Configure Monitoring and Diagnostics

**Estimated Time:** 15 minutes

#### Objective

Enable Application Insights and configure logging for production monitoring.

#### Steps

1. Enable Application Insights for the App Service:

   ```powershell
   $rg = "rg-ragflask-dev"
   $appName = "app-ragflask-dev"
   
   # Create Application Insights
   az monitor app-insights component create `
       --app "appi-ragflask-dev" `
       --location "usgovvirginia" `
       --resource-group $rg `
       --application-type web
   
   # Get the instrumentation key
   $instrumentationKey = az monitor app-insights component show `
       --app "appi-ragflask-dev" `
       --resource-group $rg `
       --query instrumentationKey -o tsv
   
   # Configure App Service to use App Insights
   az webapp config appsettings set `
       --name $appName `
       --resource-group $rg `
       --settings APPINSIGHTS_INSTRUMENTATIONKEY=$instrumentationKey
   ```

2. Enable detailed logging:

   ```powershell
   az webapp log config `
       --name $appName `
       --resource-group $rg `
       --application-logging filesystem `
       --detailed-error-messages true `
       --failed-request-tracing true `
       --web-server-logging filesystem
   ```

3. View live logs:

   ```powershell
   az webapp log tail --name $appName --resource-group $rg
   ```

4. Generate some traffic by using the chat interface.

5. View logs in Azure Portal:

   - Navigate to App Service → Logs
   - Or use Application Insights → Live Metrics

6. Query application logs:

   ```powershell
   az webapp log download `
       --name $appName `
       --resource-group $rg `
       --log-file logs.zip
   ```

#### Validation

- [ ] Application Insights created
- [ ] Live logs show request activity
- [ ] Errors are captured with stack traces

✅ **Checkpoint:** Monitoring configured.

---

## Summary

Congratulations! In this lab, you successfully:

- ✅ **Configured a Flask RAG application** with Semantic Kernel for AI orchestration
- ✅ **Integrated Azure OpenAI** for GPT-4.1 chat completion
- ✅ **Implemented RAG pattern** with Azure AI Search for context retrieval
- ✅ **Persisted chat history** in Azure Cosmos DB with session management
- ✅ **Deployed to Azure Government** App Service with proper configuration
- ✅ **Configured monitoring** with Application Insights

### Key Takeaways

1. **Semantic Kernel simplifies AI orchestration** — The kernel abstraction makes it easy to switch between AI providers and add capabilities

2. **RAG improves response quality** — Grounding responses in search results provides accurate, contextual answers

3. **Session-based history enables conversations** — Cosmos DB partition key on session_id efficiently stores and retrieves conversation context

4. **Azure Government requires specific endpoints** — Use `.azure.us` and `.usgovcloudapi.net` domains for government cloud

5. **Future-ready architecture** — The application is designed for Agent SDK and MCP integration

### What You Built

A production-ready RAG chat application that:

- Provides a responsive web chat interface
- Retrieves relevant documents from Azure AI Search
- Generates contextual responses using GPT-4.1
- Maintains conversation history across sessions
- Runs securely on Azure Government

---

## Clean Up

To avoid incurring charges, clean up the resources created in this lab.

### Delete All Resources

```powershell
# Delete the entire resource group
az group delete --name rg-ragflask-dev --yes --no-wait
```

### Delete Using Terraform

```powershell
cd infra
terraform destroy -auto-approve
```

---

## Next Steps

Ready to extend this application? Here are some ideas:

### Enhance the Application

- **Add streaming responses** — Implement SSE for real-time token streaming
- **File upload** — Allow users to upload documents for indexing
- **Multi-user support** — Add authentication with Azure AD

### Explore Semantic Kernel

- **Add plugins** — Create custom functions for specialized tasks
- **Implement agents** — Use Agent SDK for complex workflows
- **Connect MCP servers** — Integrate external tools and data sources

### Production Hardening

- **Add private endpoints** — Secure all Azure service connections
- **Enable managed identity** — Remove API keys from configuration
- **Implement rate limiting** — Protect against abuse

---

## Feedback

We'd love to hear your thoughts on this lab!

- What worked well?
- What could be improved?
- Any issues you encountered?

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0.0 | 2026-02-03 | Brian | Initial release |
