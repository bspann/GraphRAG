"""
Graph RAG Routes
Alternative routes file implementing the GraphRAG pattern

To use GraphRAG instead of standard RAG:
1. Update app/__init__.py to import from graph_routes instead of routes
2. Or mount these routes at a different path for A/B testing

Features:
- OmniRAG: Automatic strategy selection (graph vs vector vs hybrid)
- Entity extraction from queries
- Graph context + vector context combined
- Community summaries for global questions
"""

import logging
import uuid
from flask import Blueprint, render_template, request, jsonify, session

logger = logging.getLogger(__name__)

# Create blueprint for graph routes
graph_bp = Blueprint('graph', __name__)

# Services will be injected via app context
graph_service = None
graph_kernel_service = None
search_service = None
cosmos_service = None


def init_graph_services(app):
    """
    Initialize GraphRAG services from app config
    
    Call this from app factory after creating services
    """
    global graph_service, graph_kernel_service, search_service, cosmos_service
    
    from .services.graph_service import GraphService
    from .services.graph_kernel_service import GraphKernelService
    from .services.search_service import SearchService
    from .services.cosmos_service import CosmosService
    
    config = app.config
    
    # Initialize Graph Service (knowledge graph in Cosmos DB)
    graph_service = GraphService(
        endpoint=config['COSMOS_ENDPOINT'],
        key=config['COSMOS_KEY'],
        database_name=config.get('GRAPH_DATABASE', 'graphrag'),
        entities_container=config.get('GRAPH_ENTITIES_CONTAINER', 'entities'),
        relationships_container=config.get('GRAPH_RELATIONSHIPS_CONTAINER', 'relationships'),
        communities_container=config.get('GRAPH_COMMUNITIES_CONTAINER', 'communities')
    )
    
    # Initialize Graph Kernel Service (enhanced Semantic Kernel)
    graph_kernel_service = GraphKernelService(
        azure_endpoint=config['AZURE_OPENAI_ENDPOINT'],
        api_key=config['AZURE_OPENAI_API_KEY'],
        deployment_name=config['AZURE_OPENAI_DEPLOYMENT'],
        api_version=config.get('AZURE_OPENAI_API_VERSION', '2024-06-01')
    )
    
    # Reuse existing search service for vector search
    search_service = SearchService(
        endpoint=config['AZURE_SEARCH_ENDPOINT'],
        key=config['AZURE_SEARCH_KEY'],
        index_name=config['AZURE_SEARCH_INDEX'],
        semantic_config=config.get('AZURE_SEARCH_SEMANTIC_CONFIG')
    )
    
    # Reuse existing cosmos service for chat history
    cosmos_service = CosmosService(
        endpoint=config['COSMOS_ENDPOINT'],
        key=config['COSMOS_KEY'],
        database_name=config.get('COSMOS_DATABASE', 'ragapp'),
        container_name=config.get('COSMOS_CONTAINER', 'chathistory')
    )
    
    logger.info("GraphRAG services initialized")


@graph_bp.route('/')
def index():
    """Render the GraphRAG chat interface"""
    # Ensure session has an ID
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    
    return render_template(
        'graph_chat.html',
        session_id=session['session_id']
    )


@graph_bp.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "mode": "graphrag",
        "services": {
            "graph": graph_service is not None,
            "kernel": graph_kernel_service is not None,
            "search": search_service is not None,
            "cosmos": cosmos_service is not None
        }
    })


@graph_bp.route('/api/chat', methods=['POST'])
async def chat():
    """
    GraphRAG chat endpoint
    
    Implements OmniRAG pattern:
    1. Extract entities from user query
    2. Determine optimal retrieval strategy
    3. Retrieve context from graph and/or vector search
    4. Generate response with combined context
    5. Save to chat history
    """
    try:
        data = request.get_json()
        user_message = data.get('message', '').strip()
        session_id = data.get('session_id') or session.get('session_id', str(uuid.uuid4()))
        
        if not user_message:
            return jsonify({"error": "Message is required"}), 400
        
        logger.info(
            f"GraphRAG chat request",
            extra={"session_id": session_id, "message_preview": user_message[:50]}
        )
        
        # Step 1: Extract entities from the question
        entities = await graph_kernel_service.extract_query_entities(user_message)
        logger.debug(f"Extracted entities: {entities}")
        
        # Step 2: Determine retrieval strategy
        strategy = await graph_kernel_service.determine_query_strategy(user_message)
        logger.info(f"Using retrieval strategy: {strategy}")
        
        # Step 3: Retrieve context based on strategy
        graph_context = ""
        vector_context = ""
        sources = []
        
        if strategy in ["graph", "hybrid"]:
            # Get graph context
            if entities:
                graph_context = await graph_service.get_graph_context(
                    entity_names=entities,
                    include_communities=True,
                    max_depth=2
                )
            else:
                # No entities found, use community summaries for global context
                summaries = await graph_service.get_community_summaries(limit=5)
                if summaries:
                    graph_context = "## Knowledge Graph Summaries:\n" + "\n".join(
                        f"- {s}" for s in summaries
                    )
        
        if strategy in ["vector", "hybrid"]:
            # Get vector search results
            search_results = await search_service.search(user_message, top_k=5)
            
            if search_results:
                vector_context = "## Retrieved Documents:\n"
                for i, result in enumerate(search_results, 1):
                    title = result.get('title', 'Document')
                    content = result.get('content', '')[:500]
                    vector_context += f"\n### [{i}] {title}\n{content}\n"
                    
                    sources.append({
                        "title": title,
                        "url": result.get('url', ''),
                        "score": result.get('@search.score', 0)
                    })
        
        # Step 4: Get chat history
        chat_history = await cosmos_service.get_chat_history(session_id, limit=10)
        
        # Step 5: Generate response with combined context
        response = await graph_kernel_service.chat(
            user_message=user_message,
            graph_context=graph_context,
            vector_context=vector_context,
            chat_history=chat_history
        )
        
        # Step 6: Save to chat history
        await cosmos_service.save_message(session_id, 'user', user_message)
        await cosmos_service.save_message(
            session_id, 
            'assistant', 
            response,
            metadata={
                "strategy": strategy,
                "entities": entities,
                "source_count": len(sources)
            }
        )
        
        return jsonify({
            "response": response,
            "session_id": session_id,
            "metadata": {
                "strategy": strategy,
                "entities_found": entities,
                "sources": sources[:3],  # Limit sources in response
                "graph_context_used": len(graph_context) > 0,
                "vector_context_used": len(vector_context) > 0
            }
        })
        
    except Exception as e:
        logger.error(f"GraphRAG chat error: {e}", exc_info=True)
        return jsonify({
            "error": "An error occurred processing your request",
            "details": str(e) if logger.isEnabledFor(logging.DEBUG) else None
        }), 500


@graph_bp.route('/api/graph/entities', methods=['GET'])
async def get_entities():
    """
    Get entities from the knowledge graph
    
    Query params:
    - type: Filter by entity type
    - name: Search by name (partial match)
    - limit: Max results (default 50)
    """
    try:
        entity_type = request.args.get('type')
        name = request.args.get('name')
        limit = int(request.args.get('limit', 50))
        
        if name:
            entities = await graph_service.find_entities_by_name(
                name=name,
                entity_type=entity_type,
                limit=limit
            )
        elif entity_type:
            entities = await graph_service.get_entities_by_type(
                entity_type=entity_type,
                limit=limit
            )
        else:
            # Return entity types summary
            return jsonify({
                "message": "Provide 'type' or 'name' parameter to search entities",
                "example": "/api/graph/entities?type=technology&limit=10"
            })
        
        return jsonify({
            "entities": entities,
            "count": len(entities)
        })
        
    except Exception as e:
        logger.error(f"Error fetching entities: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@graph_bp.route('/api/graph/traverse', methods=['GET'])
async def traverse_graph():
    """
    Traverse the knowledge graph from a starting entity
    
    Query params:
    - entity_id: Starting entity ID (required)
    - depth: Max traversal depth (default 2)
    - rel_types: Comma-separated relationship types to follow
    """
    try:
        entity_id = request.args.get('entity_id')
        if not entity_id:
            return jsonify({"error": "entity_id is required"}), 400
        
        depth = int(request.args.get('depth', 2))
        rel_types_str = request.args.get('rel_types', '')
        rel_types = [r.strip() for r in rel_types_str.split(',') if r.strip()] or None
        
        result = await graph_service.traverse_graph(
            start_entity_id=entity_id,
            max_depth=depth,
            relationship_types=rel_types
        )
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Graph traversal error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@graph_bp.route('/api/graph/communities', methods=['GET'])
async def get_communities():
    """
    Get community summaries from the knowledge graph
    
    Query params:
    - level: Filter by hierarchy level
    - limit: Max results (default 20)
    """
    try:
        level = request.args.get('level', type=int)
        limit = int(request.args.get('limit', 20))
        
        if level is not None:
            communities = await graph_service.get_communities_by_level(
                level=level,
                limit=limit
            )
        else:
            # Return summaries from all levels
            summaries = await graph_service.get_community_summaries(limit=limit)
            return jsonify({
                "summaries": summaries,
                "count": len(summaries)
            })
        
        return jsonify({
            "communities": communities,
            "count": len(communities)
        })
        
    except Exception as e:
        logger.error(f"Error fetching communities: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@graph_bp.route('/api/history', methods=['GET'])
async def get_history():
    """Get chat history for the current session"""
    session_id = request.args.get('session_id') or session.get('session_id')
    
    if not session_id:
        return jsonify({"messages": []})
    
    try:
        messages = await cosmos_service.get_chat_history(session_id, limit=50)
        return jsonify({"messages": messages, "session_id": session_id})
        
    except Exception as e:
        logger.error(f"Error fetching history: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@graph_bp.route('/api/history', methods=['DELETE'])
async def clear_history():
    """Clear chat history for the current session"""
    session_id = request.args.get('session_id') or session.get('session_id')
    
    if not session_id:
        return jsonify({"message": "No session to clear"})
    
    try:
        deleted = await cosmos_service.clear_chat_history(session_id)
        return jsonify({
            "message": f"Cleared {deleted} messages",
            "session_id": session_id
        })
        
    except Exception as e:
        logger.error(f"Error clearing history: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500
