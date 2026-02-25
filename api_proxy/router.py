"""
OpenRouter integration layer.
Forwards requests, tracks costs, handles errors.
"""

import httpx
import time
import uuid
from typing import Dict, Any, Optional
import json

from .config import config
from .models import ChatCompletionRequest, ChatCompletionResponse, Usage, Choice, Message


class OpenRouterClient:
    """Minimal OpenRouter client for chat completions."""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or config.OPENROUTER_API_KEY
        self.base_url = config.OPENROUTER_BASE_URL
    
    async def chat_completion(
        self,
        request: ChatCompletionRequest,
        user_api_key: str  # for tracking
    ) -> tuple[ChatCompletionResponse, float]:
        """
        Call OpenRouter and return response + cost in USD.
        
        Returns:
            (response, cost_usd)
        """
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://ouroboros.ai",
            "X-Title": "Ouroboros API Reseller",
        }
        
        payload = {
            "model": request.model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
            "top_p": request.top_p,
            "frequency_penalty": request.frequency_penalty,
            "presence_penalty": request.presence_penalty,
        }
        
        if request.max_tokens:
            payload["max_tokens"] = request.max_tokens
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            data = response.json()
        
        # Calculate cost
        prompt_tokens = data["usage"]["prompt_tokens"]
        completion_tokens = data["usage"]["completion_tokens"]
        
        # Cost from OpenRouter (in response headers if available, else compute)
        # For now, compute from config
        openrouter_cost = self._compute_cost(
            request.model,
            prompt_tokens,
            completion_tokens
        )
        
        # What we charge the user (marked up)
        user_cost = self._compute_reseller_cost(
            prompt_tokens,
            completion_tokens
        )
        
        # Convert OpenRouter response to our format
        response_obj = ChatCompletionResponse(
            id=f"ouroboros-{uuid.uuid4().hex[:12]}",
            created=int(time.time()),
            model=request.model,
            choices=[
                Choice(
                    index=choice["index"],
                    message=Message(
                        role=choice["message"]["role"],
                        content=choice["message"]["content"]
                    ),
                    finish_reason=choice.get("finish_reason")
                )
                for choice in data["choices"]
            ],
            usage=Usage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens
            )
        )
        
        return response_obj, user_cost
    
    def _compute_cost(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int
    ) -> float:
        """Compute OpenRouter cost (what we pay)."""
        prompt_cost = (prompt_tokens / 1000) * config.PRICING.openrouter_prompt_cost_per_1k
        completion_cost = (completion_tokens / 1000) * config.PRICING.openrouter_completion_cost_per_1k
        return prompt_cost + completion_cost
    
    def _compute_reseller_cost(
        self,
        prompt_tokens: int,
        completion_tokens: int
    ) -> float:
        """Compute what we charge the user (cost-plus with markup)."""
        prompt_cost = (prompt_tokens / 1000) * config.PRICING.reseller_prompt_cost
        completion_cost = (completion_tokens / 1000) * config.PRICING.reseller_completion_cost
        return prompt_cost + completion_cost


# Global instance
router = OpenRouterClient()
