# GraphRAG Implementation Guide

This application supports two RAG modes:

1. **Standard RAG** - Vector search with Azure AI Search
2. **GraphRAG** - Knowledge graph + vector search (OmniRAG pattern)

## Architecture Comparison

### Standard RAG (Default)
```
User Query → Vector Search → LLM → Response
```

Files:
- `app/routes.py` - Standard routes
- `app/services/kernel_service.py` - Standard Semantic Kernel
- `app/services/search_service.py` - Azure AI Search
- `app/templates/chat.html` - Standard chat UI

### GraphRAG (Alternative)
```
User Query → Entity Extraction → Strategy Selection
                                      ↓
                    ┌─────────────────┴─────────────────┐
                    ↓                                   ↓
              Graph Context                      Vector Context
           (entities, relationships,          (document chunks)
            community summaries)
                    └─────────────────┬─────────────────┘
                                      ↓
                                     LLM → Response
```

Files:
- `app/graph_routes.py` - GraphRAG routes
- `app/services/graph_kernel_service.py` - Enhanced Semantic Kernel with OmniRAG
- `app/services/graph_service.py` - Knowledge graph in Cosmos DB NoSQL
- `app/services/entity_extraction_service.py` - LLM-based entity extraction
- `app/templates/graph_chat.html` - GraphRAG chat UI

## Switching to GraphRAG

### Option 1: Replace Routes

In `app/__init__.py`, change:

```python
# From:
from .routes import main_bp
app.register_blueprint(main_bp)

# To:
from .graph_routes import graph_bp, init_graph_services
init_graph_services(app)
app.register_blueprint(graph_bp)
```

### Option 2: Mount Both (A/B Testing)

```python
from .routes import main_bp
from .graph_routes import graph_bp, init_graph_services

# Standard RAG at /
app.register_blueprint(main_bp)

# GraphRAG at /graph
init_graph_services(app)
app.register_blueprint(graph_bp, url_prefix='/graph')
```

Then access:
- Standard RAG: `http://localhost:5000/`
- GraphRAG: `http://localhost:5000/graph/`

## Additional Configuration

Add these environment variables for GraphRAG:

```bash
# Graph Database (separate from chat history)
GRAPH_DATABASE=graphrag
GRAPH_ENTITIES_CONTAINER=entities
GRAPH_RELATIONSHIPS_CONTAINER=relationships
GRAPH_COMMUNITIES_CONTAINER=communities
```

## Building the Knowledge Graph

The knowledge graph needs to be populated before GraphRAG queries will work. Use the Entity Extraction Service to process documents:

```python
from app.services.entity_extraction_service import EntityExtractionService
from app.services.graph_service import GraphService

# Initialize services
extractor = EntityExtractionService(
    azure_endpoint="...",
    api_key="...",
    deployment_name="gpt-41"
)

graph = GraphService(
    endpoint="...",
    key="...",
    database_name="graphrag"
)

# Process a document
async def index_document(document_id: str, text: str):
    # Extract entities and relationships
    result = await extractor.extract_entities_and_relationships(
        text=text,
        source_document_id=document_id
    )
    
    # Create entities in graph
    entity_id_map = {}
    for entity in result["entities"]:
        created = await graph.create_entity(
            name=entity["name"],
            entity_type=entity["type"],
            description=entity.get("description", ""),
            source_document_id=document_id
        )
        entity_id_map[entity["name"]] = created["id"]
    
    # Create relationships
    for rel in result["relationships"]:
        source_id = entity_id_map.get(rel["source"])
        target_id = entity_id_map.get(rel["target"])
        
        if source_id and target_id:
            await graph.create_relationship(
                source_id=source_id,
                target_id=target_id,
                relationship_type=rel["type"],
                description=rel.get("description", ""),
                source_document_id=document_id
            )
```

## OmniRAG Strategy Selection

The GraphKernelService automatically selects the best retrieval strategy:

| Strategy | When Used | Example Questions |
|----------|-----------|-------------------|
| **Graph** | Questions about relationships, hierarchies, connections | "What depends on Azure Functions?" |
| **Vector** | Questions about specific facts, definitions, how-to | "What is Azure Functions?" |
| **Hybrid** | Questions that benefit from both | "How is Azure Functions related to serverless computing?" |

## Cosmos DB Container Structure

### Entities Container
Partition key: `/entity_type`
```json
{
    "id": "uuid",
    "name": "Azure Functions",
    "entity_type": "technology",
    "description": "Serverless compute service...",
    "properties": {},
    "source_document_id": "doc-123"
}
```

### Relationships Container
Partition key: `/source_id`
```json
{
    "id": "uuid",
    "source_id": "entity-uuid-1",
    "target_id": "entity-uuid-2",
    "relationship_type": "uses",
    "description": "Azure Functions uses triggers...",
    "weight": 1.0
}
```

### Communities Container
Partition key: `/level`
```json
{
    "id": "uuid",
    "name": "Serverless Technologies",
    "level": 0,
    "summary": "This community includes serverless compute services...",
    "entity_ids": ["entity-1", "entity-2", ...],
    "key_entities": ["Azure Functions", "AWS Lambda"]
}
```

## Cost Considerations

⚠️ **GraphRAG indexing is expensive** due to LLM calls for entity extraction.

- Each document requires 1-2 LLM calls for entity extraction
- Community summarization requires additional LLM calls
- Start with a small dataset to validate the approach

## References

- [Microsoft GraphRAG](https://github.com/microsoft/graphrag)
- [CosmosAIGraph](https://aka.ms/cosmosaigraph)
- [Azure Cosmos DB for RAG](https://learn.microsoft.com/azure/cosmos-db/gen-ai/cosmos-ai-graph)
