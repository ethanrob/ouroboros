"""
Pydantic models for API requests and responses.
Compatible with OpenAI API format.
"""

from typing import Any, List, Optional
from pydantic import BaseModel, Field


class Message(BaseModel):
    """Chat message."""
    role: str  # "system", "user", "assistant"
    content: str


class ChatCompletionRequest(BaseModel):
    """OpenAI-compatible chat completion request."""
    model: str
    messages: List[Message]
    temperature: Optional[float] = Field(default=1.0, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=1)
    top_p: Optional[float] = Field(default=1.0, ge=0.0, le=1.0)
    frequency_penalty: Optional[float] = Field(default=0.0, ge=-2.0, le=2.0)
    presence_penalty: Optional[float] = Field(default=0.0, ge=-2.0, le=2.0)


class Choice(BaseModel):
    """Completion choice."""
    index: int
    message: Message
    finish_reason: Optional[str] = None


class Usage(BaseModel):
    """Token usage."""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(BaseModel):
    """OpenAI-compatible chat completion response."""
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[Choice]
    usage: Usage


class PricingInfo(BaseModel):
    """Pricing information for a model."""
    model: str
    prompt_cost_per_1k: float
    completion_cost_per_1k: float
    markup_prompt: float
    markup_completion: float
    your_prompt_cost_per_1k: float
    your_completion_cost_per_1k: float


class StatusResponse(BaseModel):
    """Status endpoint response."""
    status: str
    version: str
    models_available: List[str]
    pricing_info: PricingInfo
