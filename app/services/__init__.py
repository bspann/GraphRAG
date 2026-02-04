"""
Services Package
Provides AI, search, and database services for the RAG application
"""

from flask import current_app

# Service instances (initialized once)
_kernel_service = None
_cosmos_service = None
_search_service = None


async def init_services(app):
    """Initialize all services"""
    global _kernel_service, _cosmos_service, _search_service
    
    # Initialize Semantic Kernel service
    try:
        from app.services.kernel_service import KernelService
        _kernel_service = KernelService(
            endpoint=app.config['AZURE_OPENAI_ENDPOINT'],
            api_key=app.config['AZURE_OPENAI_API_KEY'],
            deployment=app.config['AZURE_OPENAI_DEPLOYMENT'],
            api_version=app.config['AZURE_OPENAI_API_VERSION'],
            system_prompt=app.config['SYSTEM_PROMPT']
        )
        await _kernel_service.initialize()
        app.logger.info("Semantic Kernel service initialized")
    except Exception as e:
        app.logger.error(f"Failed to initialize Kernel service: {e}")
        _kernel_service = None
    
    # Initialize Cosmos DB service
    try:
        from app.services.cosmos_service import CosmosService
        _cosmos_service = CosmosService(
            endpoint=app.config['COSMOS_ENDPOINT'],
            key=app.config['COSMOS_KEY'],
            database=app.config['COSMOS_DATABASE'],
            container=app.config['COSMOS_CONTAINER']
        )
        await _cosmos_service.initialize()
        app.logger.info("Cosmos DB service initialized")
    except Exception as e:
        app.logger.error(f"Failed to initialize Cosmos service: {e}")
        _cosmos_service = None
    
    # Initialize Azure AI Search service
    try:
        from app.services.search_service import SearchService
        _search_service = SearchService(
            endpoint=app.config['AZURE_SEARCH_ENDPOINT'],
            key=app.config['AZURE_SEARCH_KEY'],
            index_name=app.config['AZURE_SEARCH_INDEX'],
            semantic_config=app.config.get('AZURE_SEARCH_SEMANTIC_CONFIG'),
            top_k=app.config.get('AZURE_SEARCH_TOP_K', 5)
        )
        await _search_service.initialize()
        app.logger.info("Azure AI Search service initialized")
    except Exception as e:
        app.logger.error(f"Failed to initialize Search service: {e}")
        _search_service = None


def get_kernel_service():
    """Get the Semantic Kernel service instance"""
    return _kernel_service


def get_cosmos_service():
    """Get the Cosmos DB service instance"""
    return _cosmos_service


def get_search_service():
    """Get the Azure AI Search service instance"""
    return _search_service
