"""
Flask Routes for RAG Application
Handles web UI and API endpoints
"""

import asyncio
import uuid
from datetime import datetime, timezone
from flask import Blueprint, render_template, request, jsonify, current_app, session

# Create blueprints
main_bp = Blueprint('main', __name__)
api_bp = Blueprint('api', __name__)


# =============================================================================
# Web UI Routes
# =============================================================================

@main_bp.route('/')
def index():
    """Render the main chat interface"""
    # Generate or retrieve session ID for chat history
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    
    return render_template('chat.html', session_id=session['session_id'])


@main_bp.route('/health')
def health():
    """Health check endpoint for App Service"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now(timezone.utc).isoformat()
    })


# =============================================================================
# API Routes
# =============================================================================

@api_bp.route('/chat', methods=['POST'])
def chat():
    """
    Handle chat requests
    
    Request body:
    {
        "message": "User's question",
        "session_id": "optional-session-id"
    }
    
    Response:
    {
        "response": "AI response",
        "sources": [...],
        "session_id": "session-id"
    }
    """
    try:
        data = request.get_json()
        
        if not data or 'message' not in data:
            return jsonify({'error': 'Message is required'}), 400
        
        user_message = data['message'].strip()
        if not user_message:
            return jsonify({'error': 'Message cannot be empty'}), 400
        
        # Get or create session ID
        session_id = data.get('session_id') or session.get('session_id') or str(uuid.uuid4())
        session['session_id'] = session_id
        
        # Get services from app context
        from app.services import get_kernel_service, get_cosmos_service, get_search_service
        
        kernel_service = get_kernel_service()
        cosmos_service = get_cosmos_service()
        search_service = get_search_service()
        
        # Run async chat processing
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(
                process_chat(
                    user_message=user_message,
                    session_id=session_id,
                    kernel_service=kernel_service,
                    cosmos_service=cosmos_service,
                    search_service=search_service
                )
            )
        finally:
            loop.close()
        
        return jsonify(result)
        
    except Exception as e:
        current_app.logger.error(f"Chat error: {e}")
        return jsonify({'error': 'An error occurred processing your request'}), 500


@api_bp.route('/history/<session_id>', methods=['GET'])
def get_history(session_id: str):
    """
    Get chat history for a session
    
    Response:
    {
        "messages": [
            {"role": "user", "content": "..."},
            {"role": "assistant", "content": "..."}
        ]
    }
    """
    try:
        from app.services import get_cosmos_service
        cosmos_service = get_cosmos_service()
        
        if not cosmos_service:
            return jsonify({'messages': []})
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            messages = loop.run_until_complete(
                cosmos_service.get_chat_history(session_id)
            )
        finally:
            loop.close()
        
        return jsonify({'messages': messages})
        
    except Exception as e:
        current_app.logger.error(f"History error: {e}")
        return jsonify({'messages': []})


@api_bp.route('/history/<session_id>', methods=['DELETE'])
def clear_history(session_id: str):
    """Clear chat history for a session"""
    try:
        from app.services import get_cosmos_service
        cosmos_service = get_cosmos_service()
        
        if cosmos_service:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                loop.run_until_complete(
                    cosmos_service.clear_chat_history(session_id)
                )
            finally:
                loop.close()
        
        return jsonify({'status': 'cleared'})
        
    except Exception as e:
        current_app.logger.error(f"Clear history error: {e}")
        return jsonify({'error': 'Failed to clear history'}), 500


@api_bp.route('/sessions', methods=['POST'])
def new_session():
    """Create a new chat session"""
    new_session_id = str(uuid.uuid4())
    session['session_id'] = new_session_id
    return jsonify({'session_id': new_session_id})


# =============================================================================
# Chat Processing Logic
# =============================================================================

async def process_chat(
    user_message: str,
    session_id: str,
    kernel_service,
    cosmos_service,
    search_service
) -> dict:
    """
    Process a chat message through the RAG pipeline
    
    1. Retrieve relevant documents from Azure AI Search
    2. Get chat history from Cosmos DB
    3. Generate response using Semantic Kernel + Azure OpenAI
    4. Save the exchange to Cosmos DB
    5. Return response with sources
    """
    sources = []
    chat_history = []
    
    # Step 1: Search for relevant context
    if search_service:
        try:
            search_results = await search_service.search(user_message)
            sources = [
                {
                    'title': doc.get('title', 'Untitled'),
                    'content': doc.get('content', '')[:500],  # Truncate for display
                    'score': doc.get('@search.score', 0)
                }
                for doc in search_results
            ]
        except Exception as e:
            current_app.logger.warning(f"Search failed: {e}")
    
    # Step 2: Get chat history
    if cosmos_service:
        try:
            chat_history = await cosmos_service.get_chat_history(
                session_id, 
                limit=current_app.config.get('MAX_HISTORY_MESSAGES', 10)
            )
        except Exception as e:
            current_app.logger.warning(f"Failed to get history: {e}")
    
    # Step 3: Generate response using Semantic Kernel
    if kernel_service:
        try:
            # Build context from search results
            context = "\n\n".join([
                f"Source: {s['title']}\n{s['content']}"
                for s in sources
            ]) if sources else ""
            
            response = await kernel_service.chat(
                user_message=user_message,
                context=context,
                chat_history=chat_history
            )
        except Exception as e:
            current_app.logger.error(f"Kernel chat failed: {e}")
            response = "I'm sorry, I encountered an error processing your request. Please try again."
    else:
        response = "Chat service is not available. Please check configuration."
    
    # Step 4: Save to history
    if cosmos_service:
        try:
            await cosmos_service.save_message(
                session_id=session_id,
                role='user',
                content=user_message
            )
            await cosmos_service.save_message(
                session_id=session_id,
                role='assistant',
                content=response,
                sources=sources
            )
        except Exception as e:
            current_app.logger.warning(f"Failed to save history: {e}")
    
    # Step 5: Return response
    return {
        'response': response,
        'sources': sources if current_app.config.get('ENABLE_CITATIONS', True) else [],
        'session_id': session_id
    }
