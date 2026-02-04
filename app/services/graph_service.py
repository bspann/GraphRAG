"""
Graph Service for CosmosAIGraph Pattern
Implements knowledge graph storage and traversal using Cosmos DB NoSQL

This service stores entities and relationships as documents in Cosmos DB,
enabling graph-like queries without requiring the Gremlin API.

Pattern: CosmosAIGraph (https://aka.ms/cosmosaigraph)
"""

import logging
import time
import functools
import uuid
from typing import Optional, Callable, Any
from datetime import datetime, timezone

from azure.cosmos import CosmosClient, PartitionKey
from azure.cosmos.exceptions import CosmosHttpResponseError

logger = logging.getLogger(__name__)


class GraphServiceError(Exception):
    """Custom exception for Graph Service errors"""
    
    def __init__(self, message: str, operation: str = None, details: dict = None):
        super().__init__(message)
        self.operation = operation
        self.details = details or {}


def log_operation(operation_name: str) -> Callable:
    """Decorator to log graph operations with timing"""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(self, *args, **kwargs) -> Any:
            start_time = time.perf_counter()
            logger.debug(f"Starting {operation_name}")
            
            try:
                result = await func(self, *args, **kwargs)
                elapsed = (time.perf_counter() - start_time) * 1000
                
                result_info = len(result) if isinstance(result, list) else "1 item"
                logger.info(f"{operation_name} completed in {elapsed:.2f}ms ({result_info})")
                return result
                
            except Exception as e:
                elapsed = (time.perf_counter() - start_time) * 1000
                logger.error(f"{operation_name} failed after {elapsed:.2f}ms: {e}", exc_info=True)
                raise
        return wrapper
    return decorator


class GraphService:
    """
    Knowledge Graph service using Cosmos DB NoSQL
    
    Stores three types of documents:
    - Entities: Nodes in the graph (people, concepts, documents, etc.)
    - Relationships: Edges connecting entities
    - Communities: Clustered groups of related entities with summaries
    
    This enables graph-like queries without Gremlin API:
    - Find all entities related to a concept
    - Traverse relationships to N degrees
    - Query community summaries for global context
    """
    
    # Document type constants
    DOC_TYPE_ENTITY = "entity"
    DOC_TYPE_RELATIONSHIP = "relationship"
    DOC_TYPE_COMMUNITY = "community"
    
    def __init__(
        self,
        endpoint: str,
        key: str,
        database_name: str = "graphrag",
        entities_container: str = "entities",
        relationships_container: str = "relationships",
        communities_container: str = "communities"
    ):
        """
        Initialize the Graph Service
        
        Args:
            endpoint: Cosmos DB endpoint (e.g., https://xxx.documents.azure.us:443/)
            key: Cosmos DB primary key
            database_name: Name of the database for graph data
            entities_container: Container for entity documents
            relationships_container: Container for relationship documents
            communities_container: Container for community summaries
        """
        self.endpoint = endpoint
        self.key = key
        self.database_name = database_name
        self.entities_container_name = entities_container
        self.relationships_container_name = relationships_container
        self.communities_container_name = communities_container
        
        self.client: Optional[CosmosClient] = None
        self.database = None
        self.entities_container = None
        self.relationships_container = None
        self.communities_container = None
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize Cosmos DB client and containers"""
        if self._initialized:
            logger.debug("Graph service already initialized")
            return
        
        logger.info(f"Initializing Graph Service with database: {self.database_name}")
        
        try:
            self.client = CosmosClient(self.endpoint, credential=self.key)
            
            # Create database if not exists
            self.database = self.client.create_database_if_not_exists(
                id=self.database_name
            )
            
            # Create containers with appropriate partition keys
            # Entities partitioned by entity_type for efficient type queries
            self.entities_container = self.database.create_container_if_not_exists(
                id=self.entities_container_name,
                partition_key=PartitionKey(path="/entity_type"),
                offer_throughput=400
            )
            
            # Relationships partitioned by source_id for efficient traversal
            self.relationships_container = self.database.create_container_if_not_exists(
                id=self.relationships_container_name,
                partition_key=PartitionKey(path="/source_id"),
                offer_throughput=400
            )
            
            # Communities partitioned by level for hierarchical queries
            self.communities_container = self.database.create_container_if_not_exists(
                id=self.communities_container_name,
                partition_key=PartitionKey(path="/level"),
                offer_throughput=400
            )
            
            self._initialized = True
            logger.info("Graph Service initialized successfully")
            
        except CosmosHttpResponseError as e:
            logger.error(f"Failed to initialize Graph Service: {e.message}", exc_info=True)
            raise GraphServiceError(
                f"Failed to initialize graph database: {e.message}",
                operation="initialize",
                details={"status_code": e.status_code}
            ) from e
        except Exception as e:
            logger.error(f"Unexpected error initializing Graph Service: {e}", exc_info=True)
            raise GraphServiceError(f"Failed to initialize: {e}", operation="initialize") from e
    
    # =========================================================================
    # Entity Operations
    # =========================================================================
    
    @log_operation("create_entity")
    async def create_entity(
        self,
        name: str,
        entity_type: str,
        description: str = "",
        properties: dict = None,
        embedding: list[float] = None,
        source_document_id: str = None
    ) -> dict:
        """
        Create an entity (node) in the knowledge graph
        
        Args:
            name: Entity name (e.g., "Azure Functions", "John Smith")
            entity_type: Type category (e.g., "technology", "person", "concept")
            description: Text description of the entity
            properties: Additional key-value properties
            embedding: Vector embedding for similarity search
            source_document_id: ID of document this entity was extracted from
            
        Returns:
            Created entity document
        """
        if not self._initialized:
            await self.initialize()
        
        entity_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        
        entity = {
            "id": entity_id,
            "doc_type": self.DOC_TYPE_ENTITY,
            "name": name,
            "name_lower": name.lower(),  # For case-insensitive search
            "entity_type": entity_type,
            "description": description,
            "properties": properties or {},
            "source_document_id": source_document_id,
            "created_at": now,
            "updated_at": now
        }
        
        # Add embedding if provided (for vector similarity)
        if embedding:
            entity["embedding"] = embedding
        
        try:
            result = self.entities_container.create_item(body=entity)
            logger.debug(f"Created entity: {name} ({entity_type})")
            return result
            
        except CosmosHttpResponseError as e:
            logger.error(f"Failed to create entity {name}: {e.message}")
            raise GraphServiceError(
                f"Failed to create entity: {e.message}",
                operation="create_entity",
                details={"name": name, "type": entity_type}
            ) from e
    
    @log_operation("get_entity")
    async def get_entity(self, entity_id: str, entity_type: str) -> Optional[dict]:
        """
        Retrieve an entity by ID
        
        Args:
            entity_id: The entity's unique ID
            entity_type: The entity type (partition key)
            
        Returns:
            Entity document or None if not found
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            return self.entities_container.read_item(
                item=entity_id,
                partition_key=entity_type
            )
        except CosmosHttpResponseError as e:
            if e.status_code == 404:
                return None
            raise GraphServiceError(
                f"Failed to get entity: {e.message}",
                operation="get_entity"
            ) from e
    
    @log_operation("find_entities_by_name")
    async def find_entities_by_name(
        self,
        name: str,
        entity_type: str = None,
        limit: int = 10
    ) -> list[dict]:
        """
        Find entities by name (case-insensitive partial match)
        
        Args:
            name: Name to search for
            entity_type: Optional type filter
            limit: Maximum results
            
        Returns:
            List of matching entities
        """
        if not self._initialized:
            await self.initialize()
        
        name_lower = name.lower()
        
        if entity_type:
            query = """
                SELECT * FROM c 
                WHERE c.entity_type = @entity_type 
                AND CONTAINS(c.name_lower, @name)
            """
            params = [
                {"name": "@entity_type", "value": entity_type},
                {"name": "@name", "value": name_lower}
            ]
        else:
            query = "SELECT * FROM c WHERE CONTAINS(c.name_lower, @name)"
            params = [{"name": "@name", "value": name_lower}]
        
        results = list(self.entities_container.query_items(
            query=query,
            parameters=params,
            max_item_count=limit,
            enable_cross_partition_query=True
        ))
        
        return results
    
    @log_operation("get_entities_by_type")
    async def get_entities_by_type(
        self,
        entity_type: str,
        limit: int = 100
    ) -> list[dict]:
        """
        Get all entities of a specific type
        
        Args:
            entity_type: The type to filter by
            limit: Maximum results
            
        Returns:
            List of entities
        """
        if not self._initialized:
            await self.initialize()
        
        query = "SELECT * FROM c WHERE c.entity_type = @type"
        
        results = list(self.entities_container.query_items(
            query=query,
            parameters=[{"name": "@type", "value": entity_type}],
            partition_key=entity_type,
            max_item_count=limit
        ))
        
        return results
    
    # =========================================================================
    # Relationship Operations
    # =========================================================================
    
    @log_operation("create_relationship")
    async def create_relationship(
        self,
        source_id: str,
        target_id: str,
        relationship_type: str,
        description: str = "",
        weight: float = 1.0,
        properties: dict = None,
        source_document_id: str = None
    ) -> dict:
        """
        Create a relationship (edge) between two entities
        
        Args:
            source_id: Source entity ID
            target_id: Target entity ID
            relationship_type: Type of relationship (e.g., "uses", "related_to", "authored_by")
            description: Text description of the relationship
            weight: Relationship strength (0.0 to 1.0)
            properties: Additional properties
            source_document_id: Document this relationship was extracted from
            
        Returns:
            Created relationship document
        """
        if not self._initialized:
            await self.initialize()
        
        rel_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        
        relationship = {
            "id": rel_id,
            "doc_type": self.DOC_TYPE_RELATIONSHIP,
            "source_id": source_id,
            "target_id": target_id,
            "relationship_type": relationship_type,
            "description": description,
            "weight": weight,
            "properties": properties or {},
            "source_document_id": source_document_id,
            "created_at": now
        }
        
        try:
            result = self.relationships_container.create_item(body=relationship)
            logger.debug(f"Created relationship: {source_id} --[{relationship_type}]--> {target_id}")
            return result
            
        except CosmosHttpResponseError as e:
            logger.error(f"Failed to create relationship: {e.message}")
            raise GraphServiceError(
                f"Failed to create relationship: {e.message}",
                operation="create_relationship"
            ) from e
    
    @log_operation("get_outgoing_relationships")
    async def get_outgoing_relationships(
        self,
        entity_id: str,
        relationship_type: str = None,
        limit: int = 50
    ) -> list[dict]:
        """
        Get all relationships where entity is the source
        
        Args:
            entity_id: The source entity ID
            relationship_type: Optional filter by type
            limit: Maximum results
            
        Returns:
            List of relationship documents
        """
        if not self._initialized:
            await self.initialize()
        
        if relationship_type:
            query = """
                SELECT * FROM c 
                WHERE c.source_id = @entity_id 
                AND c.relationship_type = @rel_type
            """
            params = [
                {"name": "@entity_id", "value": entity_id},
                {"name": "@rel_type", "value": relationship_type}
            ]
        else:
            query = "SELECT * FROM c WHERE c.source_id = @entity_id"
            params = [{"name": "@entity_id", "value": entity_id}]
        
        results = list(self.relationships_container.query_items(
            query=query,
            parameters=params,
            partition_key=entity_id,
            max_item_count=limit
        ))
        
        return results
    
    @log_operation("get_incoming_relationships")
    async def get_incoming_relationships(
        self,
        entity_id: str,
        relationship_type: str = None,
        limit: int = 50
    ) -> list[dict]:
        """
        Get all relationships where entity is the target
        
        Args:
            entity_id: The target entity ID
            relationship_type: Optional filter by type
            limit: Maximum results
            
        Returns:
            List of relationship documents
        """
        if not self._initialized:
            await self.initialize()
        
        if relationship_type:
            query = """
                SELECT * FROM c 
                WHERE c.target_id = @entity_id 
                AND c.relationship_type = @rel_type
            """
            params = [
                {"name": "@entity_id", "value": entity_id},
                {"name": "@rel_type", "value": relationship_type}
            ]
        else:
            query = "SELECT * FROM c WHERE c.target_id = @entity_id"
            params = [{"name": "@entity_id", "value": entity_id}]
        
        # Cross-partition query needed since partition is source_id
        results = list(self.relationships_container.query_items(
            query=query,
            parameters=params,
            enable_cross_partition_query=True,
            max_item_count=limit
        ))
        
        return results
    
    @log_operation("traverse_graph")
    async def traverse_graph(
        self,
        start_entity_id: str,
        max_depth: int = 2,
        relationship_types: list[str] = None
    ) -> dict:
        """
        Traverse the graph from a starting entity to N degrees
        
        Args:
            start_entity_id: Entity to start traversal from
            max_depth: Maximum traversal depth
            relationship_types: Optional filter for relationship types
            
        Returns:
            Dict with 'entities' and 'relationships' found
        """
        if not self._initialized:
            await self.initialize()
        
        visited_entities = set()
        all_relationships = []
        current_frontier = {start_entity_id}
        
        for depth in range(max_depth):
            if not current_frontier:
                break
            
            next_frontier = set()
            
            for entity_id in current_frontier:
                if entity_id in visited_entities:
                    continue
                
                visited_entities.add(entity_id)
                
                # Get outgoing relationships
                relationships = await self.get_outgoing_relationships(
                    entity_id,
                    relationship_type=relationship_types[0] if relationship_types and len(relationship_types) == 1 else None
                )
                
                for rel in relationships:
                    if relationship_types and rel["relationship_type"] not in relationship_types:
                        continue
                    
                    all_relationships.append(rel)
                    next_frontier.add(rel["target_id"])
            
            current_frontier = next_frontier - visited_entities
        
        # Fetch entity details for all visited nodes
        entities = []
        for entity_id in visited_entities:
            # We need to query since we don't know the entity_type (partition key)
            query = "SELECT * FROM c WHERE c.id = @id"
            results = list(self.entities_container.query_items(
                query=query,
                parameters=[{"name": "@id", "value": entity_id}],
                enable_cross_partition_query=True,
                max_item_count=1
            ))
            if results:
                entities.append(results[0])
        
        return {
            "entities": entities,
            "relationships": all_relationships,
            "depth_reached": min(max_depth, len(visited_entities))
        }
    
    # =========================================================================
    # Community Operations (for Global Search)
    # =========================================================================
    
    @log_operation("create_community")
    async def create_community(
        self,
        name: str,
        level: int,
        summary: str,
        entity_ids: list[str],
        key_entities: list[str] = None,
        properties: dict = None
    ) -> dict:
        """
        Create a community (cluster of related entities with summary)
        
        Communities enable "global search" by providing pre-computed summaries
        of entity clusters at different hierarchy levels.
        
        Args:
            name: Community name/title
            level: Hierarchy level (0 = most granular, higher = broader)
            summary: LLM-generated summary of this community
            entity_ids: List of entity IDs in this community
            key_entities: Most important entities in the community
            properties: Additional metadata
            
        Returns:
            Created community document
        """
        if not self._initialized:
            await self.initialize()
        
        community_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        
        community = {
            "id": community_id,
            "doc_type": self.DOC_TYPE_COMMUNITY,
            "name": name,
            "level": level,
            "summary": summary,
            "entity_ids": entity_ids,
            "entity_count": len(entity_ids),
            "key_entities": key_entities or [],
            "properties": properties or {},
            "created_at": now
        }
        
        try:
            result = self.communities_container.create_item(body=community)
            logger.debug(f"Created community: {name} (level {level}, {len(entity_ids)} entities)")
            return result
            
        except CosmosHttpResponseError as e:
            logger.error(f"Failed to create community: {e.message}")
            raise GraphServiceError(
                f"Failed to create community: {e.message}",
                operation="create_community"
            ) from e
    
    @log_operation("get_communities_by_level")
    async def get_communities_by_level(
        self,
        level: int,
        limit: int = 50
    ) -> list[dict]:
        """
        Get all communities at a specific hierarchy level
        
        Args:
            level: The hierarchy level
            limit: Maximum results
            
        Returns:
            List of community documents
        """
        if not self._initialized:
            await self.initialize()
        
        query = "SELECT * FROM c WHERE c.level = @level ORDER BY c.entity_count DESC"
        
        results = list(self.communities_container.query_items(
            query=query,
            parameters=[{"name": "@level", "value": level}],
            partition_key=level,
            max_item_count=limit
        ))
        
        return results
    
    @log_operation("get_community_summaries")
    async def get_community_summaries(
        self,
        level: int = None,
        limit: int = 20
    ) -> list[str]:
        """
        Get community summaries for global context
        
        Args:
            level: Optional level filter (None = all levels)
            limit: Maximum summaries to return
            
        Returns:
            List of summary strings
        """
        if not self._initialized:
            await self.initialize()
        
        if level is not None:
            query = "SELECT c.summary FROM c WHERE c.level = @level ORDER BY c.entity_count DESC"
            params = [{"name": "@level", "value": level}]
            results = list(self.communities_container.query_items(
                query=query,
                parameters=params,
                partition_key=level,
                max_item_count=limit
            ))
        else:
            query = "SELECT c.summary, c.level FROM c ORDER BY c.level ASC, c.entity_count DESC"
            results = list(self.communities_container.query_items(
                query=query,
                parameters=[],
                enable_cross_partition_query=True,
                max_item_count=limit
            ))
        
        return [r["summary"] for r in results if r.get("summary")]
    
    # =========================================================================
    # Graph Context for RAG
    # =========================================================================
    
    @log_operation("get_graph_context")
    async def get_graph_context(
        self,
        entity_names: list[str],
        include_communities: bool = True,
        max_depth: int = 1
    ) -> str:
        """
        Build graph context string for RAG augmentation
        
        This is the key method for Graph RAG - it takes entity names mentioned
        in a query and returns structured context about those entities and
        their relationships.
        
        Args:
            entity_names: List of entity names to look up
            include_communities: Whether to include community summaries
            max_depth: How many relationship hops to include
            
        Returns:
            Formatted string context for LLM prompt
        """
        if not self._initialized:
            await self.initialize()
        
        context_parts = []
        found_entity_ids = set()
        
        # Find entities matching the names
        for name in entity_names:
            entities = await self.find_entities_by_name(name, limit=3)
            for entity in entities:
                found_entity_ids.add(entity["id"])
                context_parts.append(
                    f"**{entity['name']}** ({entity['entity_type']}): {entity.get('description', 'No description')}"
                )
        
        # Get relationships for found entities
        if found_entity_ids:
            relationship_descriptions = []
            for entity_id in found_entity_ids:
                outgoing = await self.get_outgoing_relationships(entity_id, limit=10)
                for rel in outgoing:
                    # Get target entity name
                    target_query = "SELECT c.name FROM c WHERE c.id = @id"
                    targets = list(self.entities_container.query_items(
                        query=target_query,
                        parameters=[{"name": "@id", "value": rel["target_id"]}],
                        enable_cross_partition_query=True,
                        max_item_count=1
                    ))
                    target_name = targets[0]["name"] if targets else rel["target_id"]
                    
                    # Get source entity name
                    source_query = "SELECT c.name FROM c WHERE c.id = @id"
                    sources = list(self.entities_container.query_items(
                        query=source_query,
                        parameters=[{"name": "@id", "value": rel["source_id"]}],
                        enable_cross_partition_query=True,
                        max_item_count=1
                    ))
                    source_name = sources[0]["name"] if sources else rel["source_id"]
                    
                    relationship_descriptions.append(
                        f"- {source_name} --[{rel['relationship_type']}]--> {target_name}"
                    )
            
            if relationship_descriptions:
                context_parts.append("\n**Relationships:**")
                context_parts.extend(relationship_descriptions[:15])  # Limit relationships
        
        # Add community summaries for global context
        if include_communities:
            summaries = await self.get_community_summaries(limit=5)
            if summaries:
                context_parts.append("\n**Related Topics (from knowledge graph):**")
                for summary in summaries[:3]:
                    # Truncate long summaries
                    truncated = summary[:500] + "..." if len(summary) > 500 else summary
                    context_parts.append(f"- {truncated}")
        
        return "\n".join(context_parts) if context_parts else ""
    
    async def close(self) -> None:
        """Close the Cosmos DB client"""
        if self.client:
            try:
                # CosmosClient doesn't have explicit close, but we reset state
                self.client = None
                self.database = None
                self.entities_container = None
                self.relationships_container = None
                self.communities_container = None
                self._initialized = False
                logger.info("Graph service closed")
            except Exception as e:
                logger.warning(f"Error closing graph service: {e}")
