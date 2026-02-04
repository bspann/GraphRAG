"""
Configuration module for Flask RAG Application
Loads settings from environment variables with Azure Government defaults
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Base configuration class"""
    
    # Flask settings
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    DEBUG = os.environ.get('FLASK_DEBUG', '0') == '1'
    
    # Azure OpenAI Configuration (Azure Government endpoints)
    AZURE_OPENAI_ENDPOINT = os.environ.get('AZURE_OPENAI_ENDPOINT', '')
    AZURE_OPENAI_API_KEY = os.environ.get('AZURE_OPENAI_API_KEY', '')
    AZURE_OPENAI_API_VERSION = os.environ.get('AZURE_OPENAI_API_VERSION', '2024-06-01')
    AZURE_OPENAI_DEPLOYMENT = os.environ.get('AZURE_OPENAI_DEPLOYMENT', 'gpt-41')
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT = os.environ.get('AZURE_OPENAI_EMBEDDING_DEPLOYMENT', '')
    
    # Azure AI Search Configuration (Azure Government)
    AZURE_SEARCH_ENDPOINT = os.environ.get('AZURE_SEARCH_ENDPOINT', '')
    AZURE_SEARCH_KEY = os.environ.get('AZURE_SEARCH_KEY', '')
    AZURE_SEARCH_INDEX = os.environ.get('AZURE_SEARCH_INDEX', 'documents')
    AZURE_SEARCH_SEMANTIC_CONFIG = os.environ.get('AZURE_SEARCH_SEMANTIC_CONFIG', 'default')
    AZURE_SEARCH_TOP_K = int(os.environ.get('AZURE_SEARCH_TOP_K', '5'))
    
    # Azure Cosmos DB Configuration (Azure Government)
    COSMOS_ENDPOINT = os.environ.get('COSMOS_ENDPOINT', '')
    COSMOS_KEY = os.environ.get('COSMOS_KEY', '')
    COSMOS_DATABASE = os.environ.get('COSMOS_DATABASE', 'ragapp')
    COSMOS_CONTAINER = os.environ.get('COSMOS_CONTAINER', 'chathistory')
    
    # Application Settings
    SYSTEM_PROMPT = os.environ.get(
        'SYSTEM_PROMPT',
        """You are a helpful AI assistant. Use the provided context from the search results to answer questions accurately. 
        If you cannot find the answer in the provided context, clearly state that. 
        Always cite the sources when providing information from the context."""
    )
    MAX_HISTORY_MESSAGES = int(os.environ.get('MAX_HISTORY_MESSAGES', '10'))
    ENABLE_STREAMING = os.environ.get('ENABLE_STREAMING', 'false').lower() == 'true'
    ENABLE_CITATIONS = os.environ.get('ENABLE_CITATIONS', 'true').lower() == 'true'
    
    @classmethod
    def validate(cls) -> list[str]:
        """Validate that required configuration is present"""
        errors = []
        
        if not cls.AZURE_OPENAI_ENDPOINT:
            errors.append("AZURE_OPENAI_ENDPOINT is required")
        if not cls.AZURE_OPENAI_API_KEY:
            errors.append("AZURE_OPENAI_API_KEY is required")
        if not cls.AZURE_SEARCH_ENDPOINT:
            errors.append("AZURE_SEARCH_ENDPOINT is required")
        if not cls.AZURE_SEARCH_KEY:
            errors.append("AZURE_SEARCH_KEY is required")
        if not cls.COSMOS_ENDPOINT:
            errors.append("COSMOS_ENDPOINT is required")
        if not cls.COSMOS_KEY:
            errors.append("COSMOS_KEY is required")
            
        return errors


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    
    @classmethod
    def validate(cls) -> list[str]:
        errors = super().validate()
        
        if cls.SECRET_KEY == 'dev-secret-key-change-in-production':
            errors.append("SECRET_KEY must be changed for production")
            
        return errors


# Configuration mapping
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}


def get_config():
    """Get configuration based on FLASK_ENV"""
    env = os.environ.get('FLASK_ENV', 'development')
    return config.get(env, config['default'])
