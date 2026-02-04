# =============================================================================
# Azure Government App Service Deployment
# Terraform configuration for RAG Flask Application
# =============================================================================

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.85"
    }
  }
}

provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy = false
    }
  }
  environment = "usgovernment"
}

# -----------------------------------------------------------------------------
# Data Sources
# -----------------------------------------------------------------------------

data "azurerm_client_config" "current" {}

# -----------------------------------------------------------------------------
# Variables
# -----------------------------------------------------------------------------

variable "app_name" {
  description = "Application name (used for resource naming)"
  type        = string
  default     = "ragflask"
}

variable "environment" {
  description = "Environment (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "location" {
  description = "Azure Government region"
  type        = string
  default     = "usgovvirginia"
}

variable "resource_group_name" {
  description = "Resource group name"
  type        = string
}

# Azure OpenAI
variable "azure_openai_endpoint" {
  description = "Azure OpenAI endpoint"
  type        = string
  sensitive   = true
}

variable "azure_openai_key" {
  description = "Azure OpenAI API key"
  type        = string
  sensitive   = true
}

variable "azure_openai_deployment" {
  description = "Azure OpenAI deployment name"
  type        = string
  default     = "gpt-41"
}

# Azure AI Search
variable "azure_search_endpoint" {
  description = "Azure AI Search endpoint"
  type        = string
  sensitive   = true
}

variable "azure_search_key" {
  description = "Azure AI Search admin key"
  type        = string
  sensitive   = true
}

variable "azure_search_index" {
  description = "Azure AI Search index name"
  type        = string
  default     = "documents"
}

# -----------------------------------------------------------------------------
# Local Values
# -----------------------------------------------------------------------------

locals {
  base_name = "${var.app_name}-${var.environment}"
  tags = {
    Application = "RAG Flask App"
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# -----------------------------------------------------------------------------
# Resource Group (use existing or create)
# -----------------------------------------------------------------------------

data "azurerm_resource_group" "main" {
  name = var.resource_group_name
}

# -----------------------------------------------------------------------------
# Cosmos DB Account
# -----------------------------------------------------------------------------

resource "azurerm_cosmosdb_account" "main" {
  name                = "cosmos-${local.base_name}"
  location            = data.azurerm_resource_group.main.location
  resource_group_name = data.azurerm_resource_group.main.name
  offer_type          = "Standard"
  kind                = "GlobalDocumentDB"
  tags                = local.tags

  consistency_policy {
    consistency_level = "Session"
  }

  geo_location {
    location          = data.azurerm_resource_group.main.location
    failover_priority = 0
  }

  capabilities {
    name = "EnableServerless"
  }
}

resource "azurerm_cosmosdb_sql_database" "main" {
  name                = "ragapp"
  resource_group_name = data.azurerm_resource_group.main.name
  account_name        = azurerm_cosmosdb_account.main.name
}

resource "azurerm_cosmosdb_sql_container" "chathistory" {
  name                = "chathistory"
  resource_group_name = data.azurerm_resource_group.main.name
  account_name        = azurerm_cosmosdb_account.main.name
  database_name       = azurerm_cosmosdb_sql_database.main.name
  partition_key_paths = ["/session_id"]

  indexing_policy {
    indexing_mode = "consistent"

    included_path {
      path = "/*"
    }
  }
}

# -----------------------------------------------------------------------------
# App Service Plan
# -----------------------------------------------------------------------------

resource "azurerm_service_plan" "main" {
  name                = "asp-${local.base_name}"
  location            = data.azurerm_resource_group.main.location
  resource_group_name = data.azurerm_resource_group.main.name
  os_type             = "Linux"
  sku_name            = "B1"
  tags                = local.tags
}

# -----------------------------------------------------------------------------
# App Service
# -----------------------------------------------------------------------------

resource "azurerm_linux_web_app" "main" {
  name                = "app-${local.base_name}"
  location            = data.azurerm_resource_group.main.location
  resource_group_name = data.azurerm_resource_group.main.name
  service_plan_id     = azurerm_service_plan.main.id
  https_only          = true
  tags                = local.tags

  identity {
    type = "SystemAssigned"
  }

  site_config {
    always_on = false # Set to true for production
    
    application_stack {
      python_version = "3.11"
    }

    app_command_line = "gunicorn --bind 0.0.0.0:8000 --workers 2 --threads 4 run:app"
  }

  app_settings = {
    # Flask
    "FLASK_ENV"                       = var.environment == "prod" ? "production" : "development"
    "SECRET_KEY"                      = random_password.secret_key.result
    
    # Azure OpenAI
    "AZURE_OPENAI_ENDPOINT"           = var.azure_openai_endpoint
    "AZURE_OPENAI_API_KEY"            = var.azure_openai_key
    "AZURE_OPENAI_DEPLOYMENT"         = var.azure_openai_deployment
    "AZURE_OPENAI_API_VERSION"        = "2024-06-01"
    
    # Azure AI Search
    "AZURE_SEARCH_ENDPOINT"           = var.azure_search_endpoint
    "AZURE_SEARCH_KEY"                = var.azure_search_key
    "AZURE_SEARCH_INDEX"              = var.azure_search_index
    
    # Cosmos DB
    "COSMOS_ENDPOINT"                 = azurerm_cosmosdb_account.main.endpoint
    "COSMOS_KEY"                      = azurerm_cosmosdb_account.main.primary_key
    "COSMOS_DATABASE"                 = azurerm_cosmosdb_sql_database.main.name
    "COSMOS_CONTAINER"                = azurerm_cosmosdb_sql_container.chathistory.name
    
    # App Settings
    "ENABLE_CITATIONS"                = "true"
    "MAX_HISTORY_MESSAGES"            = "10"
  }

  logs {
    http_logs {
      file_system {
        retention_in_days = 7
        retention_in_mb   = 35
      }
    }
    application_logs {
      file_system_level = "Information"
    }
  }
}

# -----------------------------------------------------------------------------
# Random Secret Key
# -----------------------------------------------------------------------------

resource "random_password" "secret_key" {
  length  = 64
  special = true
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "app_service_url" {
  value       = "https://${azurerm_linux_web_app.main.default_hostname}"
  description = "App Service URL"
}

output "cosmos_endpoint" {
  value       = azurerm_cosmosdb_account.main.endpoint
  description = "Cosmos DB endpoint"
  sensitive   = true
}

output "app_service_name" {
  value       = azurerm_linux_web_app.main.name
  description = "App Service name for deployment"
}
