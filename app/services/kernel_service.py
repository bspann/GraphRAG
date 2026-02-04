"""
Semantic Kernel Service
Handles AI orchestration using Microsoft Semantic Kernel

This service is designed to be future-proof for:
- Agent SDK integration for multi-agent orchestration
- MCP (Model Context Protocol) server integration
- Plugin extensibility
"""

import logging
from typing import Optional
from functools import wraps
import time

import semantic_kernel as sk
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from semantic_kernel.connectors.ai.open_ai.prompt_execution_settings.azure_chat_prompt_execution_settings import (
    AzureChatPromptExecutionSettings
)
from semantic_kernel.contents.chat_history import ChatHistory

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
                logger.debug(f"{operation_name} completed in {duration:.2f}ms")
                return result
            except Exception as e:
                duration = (time.time() - start_time) * 1000
                logger.error(f"{operation_name} failed after {duration:.2f}ms: {e}")
                raise
        return wrapper
    return decorator


class KernelServiceError(Exception):
    """Custom exception for Kernel Service errors"""
    pass


class KernelService:
    """
    Semantic Kernel-based chat service for RAG applications
    
    Designed for future extensibility:
    - Agent SDK: Add agents for complex multi-step workflows
    - MCP Servers: Connect external tools and data sources
    - Plugins: Extend with custom functions
    """
    
    def __init__(
        self,
        endpoint: str,
        api_key: str,
        deployment: str,
        api_version: str = "2024-06-01",
        system_prompt: Optional[str] = None
    ):
        """
        Initialize the Kernel Service
        
        Args:
            endpoint: Azure OpenAI endpoint (e.g., https://xxx.openai.azure.us/)
            api_key: Azure OpenAI API key
            deployment: Deployment name (e.g., gpt-41)
            api_version: API version
            system_prompt: System message for the assistant
        """
        self.endpoint = endpoint
        self.api_key = api_key
        self.deployment = deployment
        self.api_version = api_version
        self.system_prompt = system_prompt or self._default_system_prompt()
        
        self.kernel: Optional[sk.Kernel] = None
        self.chat_service: Optional[AzureChatCompletion] = None
        self._initialized = False
    
    def _default_system_prompt(self) -> str:
        """Default RAG system prompt"""
        return """You are a helpful AI assistant with access to a knowledge base. 

Your task is to answer questions based on the provided context. Follow these guidelines:

1. Use the provided context to answer questions accurately
2. If the context doesn't contain enough information, say so clearly
3. Cite sources when providing information from the context
4. Be concise but thorough in your responses
5. If asked about something outside the context, acknowledge the limitation

Remember: Only use information from the provided context. Do not make up information."""
    
    async def initialize(self) -> None:
        """Initialize the Semantic Kernel and chat service"""
        if self._initialized:
            return
        
        try:
            # Create the kernel
            self.kernel = sk.Kernel()
            
            # Add Azure OpenAI chat completion service
            self.chat_service = AzureChatCompletion(
                service_id="chat",
                deployment_name=self.deployment,
                endpoint=self.endpoint,
                api_key=self.api_key,
                api_version=self.api_version
            )
            
            self.kernel.add_service(self.chat_service)
            
            self._initialized = True
            logger.info(f"Kernel initialized with deployment: {self.deployment}")
            logger.info(f"  Endpoint: {self.endpoint[:50]}...")
            
        except Exception as e:
            logger.error(f"Failed to initialize kernel: {e}", exc_info=True)
            raise KernelServiceError(f"Kernel initialization failed: {e}") from e
    
    @log_operation("Chat completion")
    async def chat(
        self,
        user_message: str,
        context: str = "",
        chat_history: Optional[list] = None
    ) -> str:
        """
        Process a chat message with RAG context
        
        Args:
            user_message: The user's question
            context: Retrieved context from Azure AI Search
            chat_history: Previous conversation history
            
        Returns:
            The AI's response
        """
        if not self._initialized:
            await self.initialize()
        
        # Build chat history
        history = ChatHistory()
        
        # Add system message with context
        system_message = self.system_prompt
        if context:
            system_message += f"\n\n## Retrieved Context:\n{context}"
        
        history.add_system_message(system_message)
        
        # Add conversation history
        if chat_history:
            for msg in chat_history:
                if msg.get('role') == 'user':
                    history.add_user_message(msg.get('content', ''))
                elif msg.get('role') == 'assistant':
                    history.add_assistant_message(msg.get('content', ''))
        
        # Add current user message
        history.add_user_message(user_message)
        
        # Configure execution settings
        settings = AzureChatPromptExecutionSettings(
            service_id="chat",
            temperature=0.7,
            max_tokens=2000,
            top_p=0.95
        )
        
        try:
            # Get chat completion
            response = await self.chat_service.get_chat_message_contents(
                chat_history=history,
                settings=settings
            )
            
            if response and len(response) > 0:
                response_text = str(response[0])
                logger.debug(f"Generated response: {len(response_text)} chars")
                return response_text
            else:
                logger.warning("Empty response from chat completion")
                return "I couldn't generate a response. Please try again."
                
        except Exception as e:
            logger.error(f"Chat completion failed: {e}", exc_info=True)
            raise KernelServiceError(f"Chat completion failed: {e}") from e
    
    # =========================================================================
    # Future: Agent SDK Integration Points
    # =========================================================================
    
    async def register_plugin(self, plugin_name: str, plugin) -> None:
        """
        Register a plugin with the kernel
        
        Future: Use this to add custom functions that agents can call
        
        Args:
            plugin_name: Name of the plugin
            plugin: Plugin instance
        """
        if not self._initialized:
            await self.initialize()
        
        self.kernel.add_plugin(plugin, plugin_name)
        logger.info(f"Registered plugin: {plugin_name}")
    
    async def create_agent(self, name: str, instructions: str):
        """
        Create an agent for complex orchestration
        
        Future: Implement with Semantic Kernel Agent SDK
        
        Args:
            name: Agent name
            instructions: Agent instructions
            
        Returns:
            Agent instance (when implemented)
        """
        # TODO: Implement when migrating to Agent SDK
        # from semantic_kernel.agents import ChatCompletionAgent
        # agent = ChatCompletionAgent(
        #     kernel=self.kernel,
        #     name=name,
        #     instructions=instructions
        # )
        # return agent
        raise NotImplementedError("Agent SDK integration coming soon")
    
    # =========================================================================
    # Future: MCP Server Integration Points
    # =========================================================================
    
    async def connect_mcp_server(self, server_url: str, server_name: str):
        """
        Connect to an MCP (Model Context Protocol) server
        
        Future: Enable external tool integrations via MCP
        
        Args:
            server_url: URL of the MCP server
            server_name: Name for the server connection
        """
        # TODO: Implement MCP server connection
        # This will allow the AI to use external tools and data sources
        raise NotImplementedError("MCP server integration coming soon")
