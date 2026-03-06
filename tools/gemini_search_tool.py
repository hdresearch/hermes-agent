"""
Gemini Search Tool - Web search using Google's Gemini with grounding.

Uses the Gemini API with Google Search grounding to perform web searches
and return AI-summarized results.

Supports authentication via:
    - GOOGLE_API_KEY environment variable (API key auth)
    - GOOGLE_CLIENT_ID + GOOGLE_CLIENT_SECRET (OAuth)
    - Application Default Credentials (gcloud auth)
"""

import json
import logging
import os
from typing import Optional

from tools.registry import registry

logger = logging.getLogger(__name__)


def check_gemini_requirements() -> bool:
    """Check if Gemini credentials are available."""
    # API key auth
    if os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"):
        return True
    # OAuth client credentials
    if os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET"):
        return True
    return False


def gemini_search(
    query: str,
    model: str = "gemini-2.0-flash",
    task_id: str = None,
) -> str:
    """
    Search the web using Gemini with Google Search grounding.
    
    Args:
        query: The search query
        model: Gemini model to use (default: gemini-2.0-flash)
        task_id: Task ID for session isolation
    
    Returns:
        JSON string with search results or error
    """
    try:
        from google import genai
        from google.genai import types
        
        # Initialize client - supports multiple auth methods:
        # 1. API key (GOOGLE_API_KEY or GEMINI_API_KEY)
        # 2. OAuth (GOOGLE_CLIENT_ID + GOOGLE_CLIENT_SECRET)
        # 3. Application Default Credentials
        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if api_key:
            client = genai.Client(api_key=api_key)
        else:
            # Use default auth (OAuth or ADC)
            client = genai.Client()
        
        # Configure grounding with Google Search
        grounding_tool = types.Tool(
            google_search=types.GoogleSearch()
        )
        
        config = types.GenerateContentConfig(
            tools=[grounding_tool]
        )
        
        # Make the search request
        response = client.models.generate_content(
            model=model,
            contents=query,
            config=config,
        )
        
        # Extract grounding metadata if available
        sources = []
        
        if hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, 'grounding_metadata'):
                gm = candidate.grounding_metadata
                if gm and hasattr(gm, 'grounding_chunks') and gm.grounding_chunks:
                    for chunk in gm.grounding_chunks:
                        if hasattr(chunk, 'web') and chunk.web:
                            sources.append({
                                "title": getattr(chunk.web, 'title', ''),
                                "uri": getattr(chunk.web, 'uri', ''),
                            })
        
        return json.dumps({
            "success": True,
            "query": query,
            "response": response.text,
            "sources": sources[:5],  # Limit to 5 sources
            "model": model,
        }, ensure_ascii=False)
        
    except ImportError:
        return json.dumps({
            "success": False,
            "error": "google-genai package not installed. Install with: pip install google-genai",
        })
    except Exception as e:
        logger.exception("Gemini search error")
        return json.dumps({
            "success": False,
            "error": str(e),
        })


GEMINI_SEARCH_SCHEMA = {
    "name": "gemini_search",
    "description": (
        "Search the web using Google's Gemini AI with Google Search grounding. "
        "Returns AI-summarized results with source citations. "
        "Use this for current information, news, facts, or any web research."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query or question to research",
            },
            "model": {
                "type": "string",
                "description": "Gemini model to use (default: gemini-2.0-flash)",
                "enum": ["gemini-2.0-flash", "gemini-2.5-pro-preview-03-25"],
            },
        },
        "required": ["query"],
    },
}

# Register the tool
registry.register(
    name="gemini_search",
    toolset="web",
    schema=GEMINI_SEARCH_SCHEMA,
    handler=lambda args, **kw: gemini_search(
        query=args.get("query", ""),
        model=args.get("model", "gemini-2.0-flash"),
        task_id=kw.get("task_id"),
    ),
    check_fn=check_gemini_requirements,
    requires_env=[],  # Multiple auth methods supported
)
