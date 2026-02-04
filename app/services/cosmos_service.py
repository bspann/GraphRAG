"""
Azure Cosmos DB Service
Handles chat history persistence for RAG applications
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional
from functools import wraps
import time

from azure.cosmos.aio import CosmosClient
from azure.cosmos import PartitionKey, exceptions

logger = logging.getLogger(__name__)


def log_operation(operation_name: str):
    """Decorator to log operation timing and errors"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                duration = (time.time() - start_time) * 1000
                logger.debug(f"Cosmos {operation_name} completed in {duration:.2f}ms")
                return result
            except Exception as e:
                duration = (time.time() - start_time) * 1000
                logger.error(f"Cosmos {operation_name} failed after {duration:.2f}ms: {e}")
                raise
        return wrapper
    return decorator


class CosmosServiceError(Exception):
    """Custom exception for Cosmos DB Service errors"""
    pass


class CosmosService:
    """
    Azure Cosmos DB service for chat history storage
    
    Schema:
    {
        "id": "unique-message-id",
        "session_id": "conversation-session-id",
        "role": "user" | "assistant",
        "content": "message content",
        "timestamp": "ISO timestamp",
        "sources": [...] (optional, for assistant messages)
    }
    """
    
    def __init__(
        self,
        endpoint: str,
        key: str,
        database: str,
        container: str
    ):
        """
        Initialize the Cosmos DB Service
        
        Args:
            endpoint: Cosmos DB endpoint (e.g., https://xxx.documents.azure.us:443/)
            key: Cosmos DB primary key
            database: Database name
            container: Container name
        """
        self.endpoint = endpoint
        self.key = key
        self.database_name = database
        self.container_name = container
        
        self.client: Optional[CosmosClient] = None
        self.database = None
        self.container = None
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize the Cosmos DB client and ensure database/container exist"""
        if self._initialized:
            return
        
        try:
            # Create async client
            self.client = CosmosClient(self.endpoint, credential=self.key)
            
            # Get or create database
            try:
                self.database = await self.client.create_database_if_not_exists(
                    id=self.database_name
                )
            except exceptions.CosmosResourceExistsError:
                self.database = self.client.get_database_client(self.database_name)
            
            # Get or create container with session_id as partition key
            try:
                self.container = await self.database.create_container_if_not_exists(
                    id=self.container_name,
                    partition_key=PartitionKey(path="/session_id"),
                    offer_throughput=400  # Minimum RU/s
                )
            except exceptions.CosmosResourceExistsError:
                self.container = self.database.get_container_client(self.container_name)
            
            self._initialized = True
            logger.info(f"Cosmos DB initialized: {self.database_name}/{self.container_name}")
            logger.info(f"  Endpoint: {self.endpoint[:50]}...")
            
        except exceptions.CosmosHttpResponseError as e:
            logger.error(f"Cosmos DB HTTP error: {e.status_code} - {e.message}", exc_info=True)
            raise CosmosServiceError(f"Cosmos DB connection failed: {e}") from e
        except Exception as e:
            logger.error(f"Failed to initialize Cosmos DB: {e}", exc_info=True)
            raise CosmosServiceError(f"Cosmos DB initialization failed: {e}") from e
    
    @log_operation("save_message")
    async def save_message(
        self,
        session_id: str,
        role: str,
        content: str,
        sources: Optional[list] = None
    ) -> dict:
        """
        Save a chat message to Cosmos DB
        
        Args:
            session_id: Conversation session ID
            role: Message role ('user' or 'assistant')
            content: Message content
            sources: Source documents (for assistant messages)
            
        Returns:
            The created document
        """
        if not self._initialized:
            await self.initialize()
        
        message = {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sources": sources or []
        }
        
        try:
            result = await self.container.create_item(body=message)
            logger.debug(f"Saved {role} message for session {session_id[:8]}...")
            return result
        except exceptions.CosmosHttpResponseError as e:
            logger.error(f"Failed to save message: {e.status_code} - {e.message}")
            raise CosmosServiceError(f"Failed to save message: {e}") from e
        except Exception as e:
            logger.error(f"Failed to save message: {e}")
            raise CosmosServiceError(f"Failed to save message: {e}") from e
    
    @log_operation("get_chat_history")
    async def get_chat_history(
        self,
        session_id: str,
        limit: int = 10
    ) -> list[dict]:
        """
        Get chat history for a session
        
        Args:
            session_id: Conversation session ID
            limit: Maximum number of messages to return
            
        Returns:
            List of messages ordered by timestamp
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            query = """
                SELECT c.role, c.content, c.timestamp, c.sources
                FROM c
                WHERE c.session_id = @session_id
                ORDER BY c.timestamp DESC
                OFFSET 0 LIMIT @limit
            """
            
            parameters = [
                {"name": "@session_id", "value": session_id},
                {"name": "@limit", "value": limit}
            ]
            
            items = []
            async for item in self.container.query_items(
                query=query,
                parameters=parameters,
                partition_key=session_id
            ):
                items.append({
                    "role": item.get("role"),
                    "content": item.get("content"),
                    "timestamp": item.get("timestamp"),
                    "sources": item.get("sources", [])
                })
            
            # Reverse to get chronological order (oldest first)
            items.reverse()
            
            logger.debug(f"Retrieved {len(items)} messages for session {session_id[:8]}...")
            return items
            
        except exceptions.CosmosHttpResponseError as e:
            logger.error(f"Failed to get chat history: {e.status_code} - {e.message}")
            return []
        except Exception as e:
            logger.error(f"Failed to get chat history: {e}")
            return []
    
    @log_operation("clear_chat_history")
    async def clear_chat_history(self, session_id: str) -> int:
        """
        Clear all messages for a session
        
        Args:
            session_id: Conversation session ID
            
        Returns:
            Number of deleted messages
        """
        if not self._initialized:
            await self.initialize()
        
        deleted_count = 0
        
        try:
            # Query all items in the session
            query = "SELECT c.id FROM c WHERE c.session_id = @session_id"
            parameters = [{"name": "@session_id", "value": session_id}]
            
            items_to_delete = []
            async for item in self.container.query_items(
                query=query,
                parameters=parameters,
                partition_key=session_id
            ):
                items_to_delete.append(item["id"])
            
            # Delete each item
            for item_id in items_to_delete:
                await self.container.delete_item(
                    item=item_id,
                    partition_key=session_id
                )
                deleted_count += 1
            
            logger.info(f"Deleted {deleted_count} messages for session {session_id}")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Failed to clear chat history: {e}")
            return deleted_count
    
    async def get_sessions(self, limit: int = 20) -> list[dict]:
        """
        Get list of recent sessions
        
        Args:
            limit: Maximum number of sessions to return
            
        Returns:
            List of sessions with metadata
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            query = """
                SELECT DISTINCT c.session_id, 
                       MIN(c.timestamp) as first_message,
                       MAX(c.timestamp) as last_message,
                       COUNT(1) as message_count
                FROM c
                GROUP BY c.session_id
                ORDER BY MAX(c.timestamp) DESC
                OFFSET 0 LIMIT @limit
            """
            
            parameters = [{"name": "@limit", "value": limit}]
            
            sessions = []
            async for item in self.container.query_items(
                query=query,
                parameters=parameters,
                enable_cross_partition_query=True
            ):
                sessions.append({
                    "session_id": item.get("session_id"),
                    "first_message": item.get("first_message"),
                    "last_message": item.get("last_message"),
                    "message_count": item.get("message_count")
                })
            
            return sessions
            
        except Exception as e:
            logger.error(f"Failed to get sessions: {e}")
            return []
    
    async def close(self) -> None:
        """Close the Cosmos DB client"""
        if self.client:
            await self.client.close()
            self._initialized = False
            logger.info("Cosmos DB client closed")
