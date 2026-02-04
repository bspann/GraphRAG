"""
Entity Extraction Service
Uses Azure OpenAI to extract entities and relationships from text

This service powers the indexing pipeline for GraphRAG by:
1. Extracting named entities from text
2. Identifying relationships between entities
3. Generating entity descriptions

Pattern: Microsoft GraphRAG entity extraction
"""

import logging
import json
import re
from typing import Optional

from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from semantic_kernel.connectors.ai.open_ai.prompt_execution_settings.azure_chat_prompt_execution_settings import (
    AzureChatPromptExecutionSettings
)
from semantic_kernel.contents.chat_history import ChatHistory

logger = logging.getLogger(__name__)


class EntityExtractionError(Exception):
    """Custom exception for entity extraction errors"""
    pass


# Prompt templates for entity extraction
ENTITY_EXTRACTION_PROMPT = """You are an expert at extracting structured information from text.

Analyze the following text and extract:
1. **Entities**: Named things like people, organizations, technologies, concepts, locations, products
2. **Relationships**: How entities are connected to each other

For each entity, provide:
- name: The entity name as it appears or a normalized form
- type: Category (person, organization, technology, concept, location, product, event, other)
- description: Brief description based on context (1-2 sentences)

For each relationship, provide:
- source: Name of the source entity
- target: Name of the target entity
- type: Relationship type (uses, related_to, created_by, part_of, located_in, works_for, depends_on, etc.)
- description: Brief description of how they're related

Return your response as valid JSON with this exact structure:
{
    "entities": [
        {"name": "...", "type": "...", "description": "..."}
    ],
    "relationships": [
        {"source": "...", "target": "...", "type": "...", "description": "..."}
    ]
}

TEXT TO ANALYZE:
---
{text}
---

Respond ONLY with the JSON, no other text."""


ENTITY_RESOLUTION_PROMPT = """You are an expert at entity resolution and deduplication.

Given the following list of entities, identify which ones refer to the same real-world entity
and should be merged. Consider:
- Different spellings or abbreviations
- Nicknames or aliases
- Partial vs full names

Current entities:
{entities}

Return a JSON object mapping duplicate entity names to the canonical (preferred) name:
{{
    "duplicates": {{
        "duplicate_name": "canonical_name",
        ...
    }}
}}

If no duplicates found, return: {{"duplicates": {{}}}}

Respond ONLY with JSON."""


class EntityExtractionService:
    """
    Service for extracting entities and relationships from text using LLMs
    
    This service is used during the indexing phase of GraphRAG to:
    1. Process documents and extract structured graph data
    2. Resolve duplicate entities
    3. Generate entity embeddings for similarity search
    """
    
    def __init__(
        self,
        azure_endpoint: str,
        api_key: str,
        deployment_name: str,
        api_version: str = "2024-06-01"
    ):
        """
        Initialize the Entity Extraction Service
        
        Args:
            azure_endpoint: Azure OpenAI endpoint
            api_key: Azure OpenAI API key
            deployment_name: Deployment name for chat model
            api_version: API version
        """
        self.azure_endpoint = azure_endpoint
        self.api_key = api_key
        self.deployment_name = deployment_name
        self.api_version = api_version
        
        self.kernel: Optional[Kernel] = None
        self.chat_service: Optional[AzureChatCompletion] = None
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize Semantic Kernel and Azure OpenAI connection"""
        if self._initialized:
            return
        
        logger.info("Initializing Entity Extraction Service")
        
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
            logger.info("Entity Extraction Service initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize entity extraction: {e}", exc_info=True)
            raise EntityExtractionError(f"Initialization failed: {e}") from e
    
    async def extract_entities_and_relationships(
        self,
        text: str,
        source_document_id: str = None
    ) -> dict:
        """
        Extract entities and relationships from text
        
        Args:
            text: The text to analyze
            source_document_id: Optional ID of source document
            
        Returns:
            Dict with 'entities' and 'relationships' lists
        """
        if not self._initialized:
            await self.initialize()
        
        if not text or len(text.strip()) < 50:
            logger.warning("Text too short for entity extraction")
            return {"entities": [], "relationships": []}
        
        # Truncate very long text to avoid token limits
        max_chars = 8000
        if len(text) > max_chars:
            text = text[:max_chars] + "\n\n[Text truncated...]"
        
        try:
            # Build the prompt
            prompt = ENTITY_EXTRACTION_PROMPT.format(text=text)
            
            # Create chat history
            chat_history = ChatHistory()
            chat_history.add_user_message(prompt)
            
            # Configure for JSON response
            settings = AzureChatPromptExecutionSettings(
                temperature=0.0,  # Deterministic for extraction
                max_tokens=2000
            )
            
            # Get completion
            response = await self.chat_service.get_chat_message_content(
                chat_history=chat_history,
                settings=settings
            )
            
            response_text = str(response)
            
            # Parse JSON response
            result = self._parse_json_response(response_text)
            
            # Add source document ID if provided
            if source_document_id:
                for entity in result.get("entities", []):
                    entity["source_document_id"] = source_document_id
                for rel in result.get("relationships", []):
                    rel["source_document_id"] = source_document_id
            
            logger.info(
                f"Extracted {len(result.get('entities', []))} entities and "
                f"{len(result.get('relationships', []))} relationships"
            )
            
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse extraction response as JSON: {e}")
            return {"entities": [], "relationships": [], "error": "JSON parse error"}
            
        except Exception as e:
            logger.error(f"Entity extraction failed: {e}", exc_info=True)
            raise EntityExtractionError(f"Extraction failed: {e}") from e
    
    async def resolve_duplicate_entities(
        self,
        entities: list[dict]
    ) -> dict[str, str]:
        """
        Identify duplicate entities that should be merged
        
        Args:
            entities: List of entity dicts with 'name' field
            
        Returns:
            Dict mapping duplicate names to canonical names
        """
        if not self._initialized:
            await self.initialize()
        
        if len(entities) < 2:
            return {}
        
        try:
            # Format entity list for prompt
            entity_list = "\n".join([
                f"- {e['name']} ({e.get('type', 'unknown')}): {e.get('description', '')[:100]}"
                for e in entities
            ])
            
            prompt = ENTITY_RESOLUTION_PROMPT.format(entities=entity_list)
            
            chat_history = ChatHistory()
            chat_history.add_user_message(prompt)
            
            settings = AzureChatPromptExecutionSettings(
                temperature=0.0,
                max_tokens=1000
            )
            
            response = await self.chat_service.get_chat_message_content(
                chat_history=chat_history,
                settings=settings
            )
            
            result = self._parse_json_response(str(response))
            
            return result.get("duplicates", {})
            
        except Exception as e:
            logger.error(f"Entity resolution failed: {e}", exc_info=True)
            return {}
    
    async def generate_entity_description(
        self,
        entity_name: str,
        entity_type: str,
        context_snippets: list[str]
    ) -> str:
        """
        Generate a comprehensive description for an entity based on context
        
        Args:
            entity_name: The entity name
            entity_type: The entity type
            context_snippets: Text snippets where this entity appears
            
        Returns:
            Generated description string
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            context = "\n---\n".join(context_snippets[:5])  # Limit context
            
            prompt = f"""Based on the following context, write a concise 2-3 sentence description 
of "{entity_name}" (a {entity_type}).

Context:
{context}

Description:"""
            
            chat_history = ChatHistory()
            chat_history.add_user_message(prompt)
            
            settings = AzureChatPromptExecutionSettings(
                temperature=0.3,
                max_tokens=200
            )
            
            response = await self.chat_service.get_chat_message_content(
                chat_history=chat_history,
                settings=settings
            )
            
            return str(response).strip()
            
        except Exception as e:
            logger.error(f"Description generation failed: {e}")
            return f"A {entity_type} mentioned in the documents."
    
    def _parse_json_response(self, response_text: str) -> dict:
        """
        Parse JSON from LLM response, handling common issues
        
        Args:
            response_text: Raw response from LLM
            
        Returns:
            Parsed dict
        """
        # Clean up response
        text = response_text.strip()
        
        # Remove markdown code blocks if present
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        
        if text.endswith("```"):
            text = text[:-3]
        
        text = text.strip()
        
        # Try to find JSON object in the response
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            text = json_match.group()
        
        return json.loads(text)
    
    async def close(self) -> None:
        """Clean up resources"""
        self.kernel = None
        self.chat_service = None
        self._initialized = False
        logger.info("Entity Extraction Service closed")
