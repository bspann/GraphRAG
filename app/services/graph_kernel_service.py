"""
Graph RAG Kernel Service
Enhanced Semantic Kernel service with GraphRAG capabilities

This service extends the standard RAG pattern with:
1. Entity extraction from user queries
2. Graph context retrieval (relationships, community summaries)
3. OmniRAG pattern (combining vector search + graph traversal)

Use this instead of kernel_service.py for GraphRAG functionality.
"""

import logging
import time
import functools
import re
from typing import Optional, Callable, Any

from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from semantic_kernel.connectors.ai.open_ai.prompt_execution_settings.azure_chat_prompt_execution_settings import (
    AzureChatPromptExecutionSettings
)
from semantic_kernel.contents.chat_history import ChatHistory

logger = logging.getLogger(__name__)


class GraphKernelServiceError(Exception):
    """Custom exception for Graph Kernel Service errors"""
    
    def __init__(self, message: str, operation: str = None, details: dict = None):
        super().__init__(message)
        self.operation = operation
        self.details = details or {}


def log_operation(operation_name: str) -> Callable:
    """Decorator to log operations with timing"""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(self, *args, **kwargs) -> Any:
            start_time = time.perf_counter()
            logger.debug(f"Starting {operation_name}")
            try:
                result = await func(self, *args, **kwargs)
                elapsed = (time.perf_counter() - start_time) * 1000
                logger.info(f"{operation_name} completed in {elapsed:.2f}ms")
                return result
            except Exception as e:
                elapsed = (time.perf_counter() - start_time) * 1000
                logger.error(f"{operation_name} failed after {elapsed:.2f}ms: {e}", exc_info=True)
                raise
        return wrapper
    return decorator


# Entity extraction prompt for query analysis
QUERY_ENTITY_EXTRACTION_PROMPT = """Extract the key entities (names, concepts, technologies, organizations) 
mentioned in this user question. Return ONLY a comma-separated list of entity names.
If no clear entities, return "NONE".

Question: {question}

Entities:"""


class GraphKernelService:
    """
    Semantic Kernel service with GraphRAG capabilities
    
    Implements the OmniRAG pattern:
    1. Analyze query to extract entity mentions
    2. Retrieve graph context (entities, relationships, communities)
    3. Combine with vector search results
    4. Generate response with multi-source grounding
    
    Designed for future extension with:
    - Agent SDK for multi-step reasoning
    - MCP servers for external tool integration
    """
    
    # System prompts
    GRAPH_RAG_SYSTEM_PROMPT = """You are an intelligent assistant with access to a knowledge graph.

You have been provided with:
1. **Graph Context**: Entities and their relationships from a knowledge graph
2. **Document Context**: Relevant text passages from document search
3. **Conversation History**: Previous messages in this chat session

When answering questions:
- Use the graph context to understand relationships between concepts
- Use the document context for specific details and facts
- Cite your sources when possible (e.g., "According to the knowledge graph..." or "The documents mention...")
- If you don't have enough information, say so clearly
- Be concise but thorough

Remember: The graph shows HOW things are connected. The documents show WHAT is said about them."""

    def __init__(
        self,
        azure_endpoint: str,
        api_key: str,
        deployment_name: str,
        api_version: str = "2024-06-01",
        system_prompt: str = None
    ):
        """
        Initialize the Graph RAG Kernel Service
        
        Args:
            azure_endpoint: Azure OpenAI endpoint
            api_key: Azure OpenAI API key
            deployment_name: Chat model deployment name
            api_version: API version
            system_prompt: Optional custom system prompt
        """
        self.azure_endpoint = azure_endpoint
        self.api_key = api_key
        self.deployment_name = deployment_name
        self.api_version = api_version
        self.system_prompt = system_prompt or self.GRAPH_RAG_SYSTEM_PROMPT
        
        self.kernel: Optional[Kernel] = None
        self.chat_service: Optional[AzureChatCompletion] = None
        self._initialized = False
        
        logger.info(f"GraphKernelService configured with endpoint: {azure_endpoint[:30]}...")
    
    async def initialize(self) -> None:
        """Initialize Semantic Kernel with Azure OpenAI"""
        if self._initialized:
            logger.debug("GraphKernelService already initialized")
            return
        
        logger.info("Initializing GraphKernelService")
        
        try:
            self.kernel = Kernel()
            
            self.chat_service = AzureChatCompletion(
                deployment_name=self.deployment_name,
                endpoint=self.azure_endpoint,
                api_key=self.api_key,
                api_version=self.api_version
            )
            
            self.kernel.add_service(self.chat_service)
            
            self._initialized = True
            logger.info("GraphKernelService initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize GraphKernelService: {e}", exc_info=True)
            raise GraphKernelServiceError(
                f"Initialization failed: {e}",
                operation="initialize"
            ) from e
    
    @log_operation("extract_query_entities")
    async def extract_query_entities(self, question: str) -> list[str]:
        """
        Extract entity names mentioned in a user question
        
        Args:
            question: The user's question
            
        Returns:
            List of entity names found
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            prompt = QUERY_ENTITY_EXTRACTION_PROMPT.format(question=question)
            
            chat_history = ChatHistory()
            chat_history.add_user_message(prompt)
            
            settings = AzureChatPromptExecutionSettings(
                temperature=0.0,
                max_tokens=200
            )
            
            response = await self.chat_service.get_chat_message_content(
                chat_history=chat_history,
                settings=settings
            )
            
            response_text = str(response).strip()
            
            if response_text.upper() == "NONE":
                return []
            
            # Parse comma-separated entities
            entities = [e.strip() for e in response_text.split(",") if e.strip()]
            
            logger.debug(f"Extracted entities from query: {entities}")
            return entities
            
        except Exception as e:
            logger.warning(f"Entity extraction failed, using fallback: {e}")
            # Fallback: simple noun extraction
            return self._simple_entity_extraction(question)
    
    def _simple_entity_extraction(self, text: str) -> list[str]:
        """
        Simple fallback entity extraction using patterns
        
        Args:
            text: Text to extract from
            
        Returns:
            List of potential entity names
        """
        # Find capitalized words/phrases (potential proper nouns)
        pattern = r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b'
        matches = re.findall(pattern, text)
        
        # Filter common words
        stop_words = {"What", "How", "Why", "When", "Where", "Who", "The", "This", "That"}
        entities = [m for m in matches if m not in stop_words]
        
        return entities[:5]  # Limit to 5
    
    @log_operation("graph_rag_chat")
    async def chat(
        self,
        user_message: str,
        graph_context: str = "",
        vector_context: str = "",
        chat_history: Optional[list[dict]] = None
    ) -> str:
        """
        Generate a response using GraphRAG pattern
        
        Combines graph context (entities/relationships) with vector search results
        for comprehensive, grounded responses.
        
        Args:
            user_message: The user's question
            graph_context: Context from knowledge graph (entities, relationships)
            vector_context: Context from vector search (document chunks)
            chat_history: Previous conversation messages
            
        Returns:
            Generated response string
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            # Build augmented system prompt with both contexts
            augmented_system = self.system_prompt
            
            if graph_context:
                augmented_system += f"\n\n## Knowledge Graph Context:\n{graph_context}"
            
            if vector_context:
                augmented_system += f"\n\n## Document Context:\n{vector_context}"
            
            # Build chat history
            sk_chat_history = ChatHistory()
            sk_chat_history.add_system_message(augmented_system)
            
            # Add conversation history
            if chat_history:
                for msg in chat_history[-10:]:  # Last 10 messages
                    role = msg.get("role", "user")
                    content = msg.get("content", "")
                    
                    if role == "user":
                        sk_chat_history.add_user_message(content)
                    elif role == "assistant":
                        sk_chat_history.add_assistant_message(content)
            
            # Add current user message
            sk_chat_history.add_user_message(user_message)
            
            # Configure response settings
            settings = AzureChatPromptExecutionSettings(
                temperature=0.7,
                max_tokens=1500,
                top_p=0.9
            )
            
            # Generate response
            response = await self.chat_service.get_chat_message_content(
                chat_history=sk_chat_history,
                settings=settings
            )
            
            response_text = str(response)
            
            logger.debug(
                f"GraphRAG response generated",
                extra={
                    "graph_context_length": len(graph_context),
                    "vector_context_length": len(vector_context),
                    "response_length": len(response_text)
                }
            )
            
            return response_text
            
        except Exception as e:
            logger.error(f"GraphRAG chat failed: {e}", exc_info=True)
            raise GraphKernelServiceError(
                f"Chat generation failed: {e}",
                operation="chat"
            ) from e
    
    @log_operation("determine_query_strategy")
    async def determine_query_strategy(self, question: str) -> str:
        """
        Determine the best retrieval strategy for a question (OmniRAG)
        
        Strategies:
        - "graph": Question about relationships, hierarchies, connections
        - "vector": Question about specific facts, details, content
        - "hybrid": Question that benefits from both
        
        Args:
            question: The user's question
            
        Returns:
            Strategy name: "graph", "vector", or "hybrid"
        """
        if not self._initialized:
            await self.initialize()
        
        # Keywords that suggest graph queries
        graph_keywords = [
            "related", "relationship", "connected", "connection",
            "depends", "dependency", "uses", "used by",
            "hierarchy", "parent", "child", "belongs to",
            "author", "created by", "works for",
            "all the", "list all", "what are the"
        ]
        
        # Keywords that suggest vector search
        vector_keywords = [
            "what is", "define", "explain", "describe",
            "how to", "how do", "steps to",
            "example", "code", "syntax",
            "specific", "details about"
        ]
        
        question_lower = question.lower()
        
        graph_score = sum(1 for kw in graph_keywords if kw in question_lower)
        vector_score = sum(1 for kw in vector_keywords if kw in question_lower)
        
        if graph_score > vector_score + 1:
            strategy = "graph"
        elif vector_score > graph_score + 1:
            strategy = "vector"
        else:
            strategy = "hybrid"
        
        logger.info(
            f"Query strategy: {strategy}",
            extra={
                "graph_score": graph_score,
                "vector_score": vector_score,
                "question_preview": question[:50]
            }
        )
        
        return strategy
    
    @log_operation("generate_community_summary")
    async def generate_community_summary(
        self,
        entity_names: list[str],
        entity_descriptions: list[str],
        relationship_descriptions: list[str]
    ) -> str:
        """
        Generate a summary for a community of related entities
        
        Used during graph indexing to create community summaries for global search.
        
        Args:
            entity_names: Names of entities in the community
            entity_descriptions: Descriptions of each entity
            relationship_descriptions: Descriptions of relationships
            
        Returns:
            Generated community summary
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            # Build context for summary
            entity_list = "\n".join([
                f"- {name}: {desc}" 
                for name, desc in zip(entity_names, entity_descriptions)
            ])
            
            rel_list = "\n".join([f"- {r}" for r in relationship_descriptions])
            
            prompt = f"""Summarize this cluster of related entities and their relationships 
in 2-3 sentences. Focus on the main theme and key insights.

Entities:
{entity_list}

Relationships:
{rel_list}

Summary:"""
            
            chat_history = ChatHistory()
            chat_history.add_user_message(prompt)
            
            settings = AzureChatPromptExecutionSettings(
                temperature=0.3,
                max_tokens=300
            )
            
            response = await self.chat_service.get_chat_message_content(
                chat_history=chat_history,
                settings=settings
            )
            
            return str(response).strip()
            
        except Exception as e:
            logger.error(f"Community summary generation failed: {e}")
            return f"A community containing: {', '.join(entity_names[:5])}"
    
    async def close(self) -> None:
        """Clean up resources"""
        self.kernel = None
        self.chat_service = None
        self._initialized = False
        logger.info("GraphKernelService closed")
