"""
Configuration for API reselling proxy.
Pricing, markup, and feature flags.
"""

import os
from dataclasses import dataclass


@dataclass
class PricingConfig:
    """Cost-plus pricing model based on OpenRouter token costs."""
    
    # OpenRouter base costs (from pricing API)
    # These are approximate; we fetch fresh on startup
    openrouter_prompt_cost_per_1k = 0.0005  # gpt-3.5-turbo-like
    openrouter_completion_cost_per_1k = 0.0015
    
    # Markup multiplier on top of OpenRouter cost
    prompt_markup = 2.0  # 100% markup: 2x cost
    completion_markup = 2.5  # 150% markup: 2.5x cost
    
    @property
    def reseller_prompt_cost(self):
        """What we charge per 1k prompt tokens."""
        return self.openrouter_prompt_cost_per_1k * self.prompt_markup
    
    @property
    def reseller_completion_cost(self):
        """What we charge per 1k completion tokens."""
        return self.openrouter_completion_cost_per_1k * self.completion_markup


class Config:
    """Main configuration."""
    
    # API
    API_TITLE = "Ouroboros API Reseller"
    API_VERSION = "0.1.0"
    API_DESCRIPTION = "Claude API access with transparent pricing"
    
    # OpenRouter
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_BASE_URL = "https://openrouter.io/api/v1"
    
    # Default model (configurable per request)
    DEFAULT_MODEL = "anthropic/claude-3.5-sonnet"
    
    # Database
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./api_usage.db")
    
    # Pricing
    PRICING = PricingConfig()
    
    # Admin
    ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "sk-admin-default-change-in-prod")
    
    # Deployment
    DEBUG = os.getenv("DEBUG", "False").lower() == "true"
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "8000"))


config = Config()
