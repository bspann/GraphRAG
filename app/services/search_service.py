"""
Azure AI Search Service
Handles document retrieval for RAG applications with comprehensive error handling
"""

import logging
import time
import functools
from typing import Optional, Callable, Any

from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import (
    HttpResponseError,
    ServiceRequestError,
    ClientAuthenticationError
)
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery

logger = logging.getLogger(__name__)


class SearchServiceError(Exception):
    """Custom exception for Search Service errors"""
    
    def __init__(self, message: str, operation: str = None, details: dict = None):
        super().__init__(message)
        self.operation = operation
        self.details = details or {}
    
    def __str__(self):
        if self.operation:
            return f"[{self.operation}] {super().__str__()}"
        return super().__str__()


def log_operation(operation_name: str) -> Callable:
    """Decorator to log search operations with timing and error handling"""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(self, *args, **kwargs) -> Any:
            start_time = time.perf_counter()
            
            # Extract query for logging (first positional arg or from kwargs)
            query_preview = ""
            if args:
                first_arg = args[0]
                if isinstance(first_arg, str):
                    query_preview = first_arg[:50] + "..." if len(first_arg) > 50 else first_arg
                elif isinstance(first_arg, list):
                    query_preview = f"[vector: {len(first_arg)} dimensions]"
            
            logger.debug(
                f"Starting {operation_name}",
                extra={
                    "operation": operation_name,
                    "query_preview": query_preview,
                    "index": getattr(self, 'index_name', 'unknown')
                }
            )
            
            try:
                result = await func(self, *args, **kwargs)
                elapsed = (time.perf_counter() - start_time) * 1000
                
                result_count = len(result) if isinstance(result, list) else 1
                logger.info(
                    f"{operation_name} completed in {elapsed:.2f}ms ({result_count} results)",
                    extra={
                        "operation": operation_name,
                        "elapsed_ms": elapsed,
                        "result_count": result_count
                    }
                )
                return result
                
            except Exception as e:
                elapsed = (time.perf_counter() - start_time) * 1000
                logger.error(
                    f"{operation_name} failed after {elapsed:.2f}ms: {e}",
                    extra={
                        "operation": operation_name,
                        "elapsed_ms": elapsed,
                        "error_type": type(e).__name__
                    },
                    exc_info=True
                )
                raise
        return wrapper
    return decorator


class SearchService:
    """
    Azure AI Search service for RAG document retrieval
    
    Supports:
    - Keyword search
    - Semantic search (when configured)
    - Vector search (when embeddings are available)
    - Hybrid search (combination of above)
    """
    
    def __init__(
        self,
        endpoint: str,
        key: str,
        index_name: str,
        semantic_config: Optional[str] = None,
        top_k: int = 5
    ):
        """
        Initialize the Search Service
        
        Args:
            endpoint: Azure AI Search endpoint (e.g., https://xxx.search.windows.us)
            key: Azure AI Search admin key
            index_name: Name of the search index
            semantic_config: Semantic configuration name (optional)
            top_k: Number of results to return
        """
        self.endpoint = endpoint
        self.key = key
        self.index_name = index_name
        self.semantic_config = semantic_config
        self.top_k = top_k
        
        self.client: Optional[SearchClient] = None
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize the search client with comprehensive error handling"""
        if self._initialized:
            logger.debug("Search client already initialized")
            return
        
        logger.info(
            f"Initializing Azure AI Search client",
            extra={
                "endpoint": self.endpoint,
                "index": self.index_name,
                "semantic_config": self.semantic_config
            }
        )
        
        try:
            credential = AzureKeyCredential(self.key)
            self.client = SearchClient(
                endpoint=self.endpoint,
                index_name=self.index_name,
                credential=credential
            )
            
            self._initialized = True
            logger.info(
                f"Search client initialized successfully for index: {self.index_name}"
            )
            
        except ClientAuthenticationError as e:
            logger.error(
                f"Authentication failed for Azure AI Search: {e}",
                extra={"endpoint": self.endpoint},
                exc_info=True
            )
            raise SearchServiceError(
                "Failed to authenticate with Azure AI Search. Check your API key.",
                operation="initialize",
                details={"endpoint": self.endpoint}
            ) from e
            
        except ServiceRequestError as e:
            logger.error(
                f"Network error connecting to Azure AI Search: {e}",
                extra={"endpoint": self.endpoint},
                exc_info=True
            )
            raise SearchServiceError(
                f"Network error connecting to Azure AI Search at {self.endpoint}",
                operation="initialize",
                details={"endpoint": self.endpoint}
            ) from e
            
        except Exception as e:
            logger.error(
                f"Failed to initialize search client: {e}",
                extra={"endpoint": self.endpoint, "index": self.index_name},
                exc_info=True
            )
            raise SearchServiceError(
                f"Failed to initialize search client: {e}",
                operation="initialize"
            ) from e
    
    @log_operation("text_search")
    async def search(
        self,
        query: str,
        top_k: Optional[int] = None,
        filter_expression: Optional[str] = None
    ) -> list[dict]:
        """
        Search for documents matching the query
        
        Args:
            query: Search query text
            top_k: Number of results (overrides default)
            filter_expression: OData filter expression
            
        Returns:
            List of matching documents
            
        Raises:
            SearchServiceError: If search fails with non-recoverable error
        """
        if not self._initialized:
            await self.initialize()
        
        results = []
        k = top_k or self.top_k
        
        try:
            # Build search options
            search_options = {
                "search_text": query,
                "top": k,
                "include_total_count": True
            }
            
            # Add semantic configuration if available
            if self.semantic_config:
                search_options["query_type"] = "semantic"
                search_options["semantic_configuration_name"] = self.semantic_config
                logger.debug(f"Using semantic search with config: {self.semantic_config}")
            
            # Add filter if provided
            if filter_expression:
                search_options["filter"] = filter_expression
                logger.debug(f"Applying filter: {filter_expression}")
            
            # Execute search
            response = self.client.search(**search_options)
            
            # Process results
            for doc in response:
                results.append({
                    'id': doc.get('id'),
                    'title': doc.get('title', doc.get('name', 'Untitled')),
                    'content': doc.get('content', doc.get('text', '')),
                    'url': doc.get('url', ''),
                    'metadata': doc.get('metadata', {}),
                    '@search.score': doc.get('@search.score', 0),
                    '@search.reranker_score': doc.get('@search.reranker_score')
                })
            
            return results
            
        except HttpResponseError as e:
            error_msg = f"Azure AI Search query failed: {e.message}"
            logger.error(
                error_msg,
                extra={
                    "status_code": e.status_code,
                    "error_code": getattr(e.error, 'code', None) if e.error else None,
                    "query_preview": query[:50]
                },
                exc_info=True
            )
            
            # Return empty results for invalid query syntax
            if e.status_code == 400:
                logger.warning("Invalid search query syntax, returning empty results")
                return []
            
            raise SearchServiceError(
                error_msg,
                operation="search",
                details={"status_code": e.status_code, "query": query[:50]}
            ) from e
            
        except Exception as e:
            logger.error(f"Unexpected search error: {e}", exc_info=True)
            # Return empty results to allow application to continue
            return []
    
    @log_operation("vector_search")
    async def vector_search(
        self,
        query_vector: list[float],
        vector_field: str = "embedding",
        top_k: Optional[int] = None
    ) -> list[dict]:
        """
        Perform vector similarity search
        
        Args:
            query_vector: Query embedding vector
            vector_field: Name of the vector field in the index
            top_k: Number of results
            
        Returns:
            List of matching documents
            
        Raises:
            SearchServiceError: If vector search fails
        """
        if not self._initialized:
            await self.initialize()
        
        results = []
        k = top_k or self.top_k
        
        try:
            # Build vector query
            vector_query = VectorizedQuery(
                vector=query_vector,
                k_nearest_neighbors=k,
                fields=vector_field
            )
            
            # Execute vector search
            response = self.client.search(
                search_text=None,
                vector_queries=[vector_query],
                top=k
            )
            
            # Process results
            for doc in response:
                results.append({
                    'id': doc.get('id'),
                    'title': doc.get('title', doc.get('name', 'Untitled')),
                    'content': doc.get('content', doc.get('text', '')),
                    'url': doc.get('url', ''),
                    '@search.score': doc.get('@search.score', 0)
                })
            
            return results
            
        except HttpResponseError as e:
            logger.error(
                f"Vector search HTTP error: {e.message}",
                extra={"status_code": e.status_code},
                exc_info=True
            )
            raise SearchServiceError(
                f"Vector search failed: {e.message}",
                operation="vector_search",
                details={"status_code": e.status_code}
            ) from e
            
        except Exception as e:
            logger.error(f"Vector search failed: {e}", exc_info=True)
            return []
    
    @log_operation("hybrid_search")
    async def hybrid_search(
        self,
        query: str,
        query_vector: Optional[list[float]] = None,
        vector_field: str = "embedding",
        top_k: Optional[int] = None
    ) -> list[dict]:
        """
        Perform hybrid search (text + vector)
        
        Args:
            query: Search query text
            query_vector: Query embedding vector (optional)
            vector_field: Name of the vector field
            top_k: Number of results
            
        Returns:
            List of matching documents
        """
        if not self._initialized:
            await self.initialize()
        
        if not query_vector:
            # Fall back to text search
            return await self.search(query, top_k)
        
        results = []
        k = top_k or self.top_k
        
        try:
            # Build vector query
            vector_query = VectorizedQuery(
                vector=query_vector,
                k_nearest_neighbors=k,
                fields=vector_field
            )
            
            # Build search options
            search_options = {
                "search_text": query,
                "vector_queries": [vector_query],
                "top": k
            }
            
            # Add semantic if configured
            if self.semantic_config:
                search_options["query_type"] = "semantic"
                search_options["semantic_configuration_name"] = self.semantic_config
            
            # Execute hybrid search
            response = self.client.search(**search_options)
            
            # Process results
            for doc in response:
                results.append({
                    'id': doc.get('id'),
                    'title': doc.get('title', doc.get('name', 'Untitled')),
                    'content': doc.get('content', doc.get('text', '')),
                    'url': doc.get('url', ''),
                    '@search.score': doc.get('@search.score', 0),
                    '@search.reranker_score': doc.get('@search.reranker_score')
                })
            
            return results
            
        except HttpResponseError as e:
            logger.error(
                f"Hybrid search HTTP error: {e.message}",
                extra={"status_code": e.status_code, "query_preview": query[:50]},
                exc_info=True
            )
            raise SearchServiceError(
                f"Hybrid search failed: {e.message}",
                operation="hybrid_search",
                details={"status_code": e.status_code}
            ) from e
            
        except Exception as e:
            logger.error(f"Hybrid search failed: {e}", exc_info=True)
            return []
    
    async def get_document(self, document_id: str) -> Optional[dict]:
        """
        Retrieve a specific document by ID
        
        Args:
            document_id: The document ID to retrieve
            
        Returns:
            The document dict or None if not found
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            doc = self.client.get_document(key=document_id)
            logger.debug(f"Retrieved document: {document_id}")
            return dict(doc)
            
        except HttpResponseError as e:
            if e.status_code == 404:
                logger.debug(f"Document not found: {document_id}")
                return None
            logger.error(f"Error retrieving document {document_id}: {e}", exc_info=True)
            raise SearchServiceError(
                f"Failed to retrieve document: {e.message}",
                operation="get_document",
                details={"document_id": document_id}
            ) from e
            
        except Exception as e:
            logger.error(f"Error retrieving document {document_id}: {e}", exc_info=True)
            return None
    
    async def close(self) -> None:
        """Close the search client connection"""
        if self.client:
            try:
                self.client.close()
                logger.info("Search client connection closed")
            except Exception as e:
                logger.warning(f"Error closing search client: {e}")
        self._initialized = False
