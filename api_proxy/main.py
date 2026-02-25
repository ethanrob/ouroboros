"""
FastAPI application for API reselling proxy.
Main entry point.
"""

from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.responses import JSONResponse
from typing import Optional
import time

from .config import config
from .models import ChatCompletionRequest, StatusResponse, PricingInfo
from .router import router
from .database import db


app = FastAPI(
    title=config.API_TITLE,
    description=config.API_DESCRIPTION,
    version=config.API_VERSION,
    docs_url="/docs",
    redoc_url="/redoc"
)


async def verify_api_key(x_api_key: str = Header(...)) -> str:
    """Validate API key from header."""
    if not db.is_key_valid(x_api_key):
        raise HTTPException(status_code=401, detail="Invalid or inactive API key")
    
    allowed, error_msg = db.check_daily_limit(x_api_key)
    if not allowed:
        raise HTTPException(status_code=429, detail=error_msg)
    
    return x_api_key


@app.get("/health", tags=["System"])
async def health():
    """Health check."""
    return {"status": "ok"}


@app.get("/status", tags=["System"])
async def status(api_key: str = Depends(verify_api_key)):
    """Get service status and pricing info."""
    usage = db.get_usage(api_key)
    
    pricing = PricingInfo(
        model=config.DEFAULT_MODEL,
        prompt_cost_per_1k=config.PRICING.openrouter_prompt_cost_per_1k,
        completion_cost_per_1k=config.PRICING.openrouter_completion_cost_per_1k,
        markup_prompt=config.PRICING.prompt_markup,
        markup_completion=config.PRICING.completion_markup,
        your_prompt_cost_per_1k=config.PRICING.reseller_prompt_cost,
        your_completion_cost_per_1k=config.PRICING.reseller_completion_cost,
    )
    
    return StatusResponse(
        status="operational",
        version=config.API_VERSION,
        models_available=[config.DEFAULT_MODEL],
        pricing_info=pricing
    )


@app.post("/v1/chat/completions", tags=["Chat"])
async def chat_completions(
    request: ChatCompletionRequest,
    api_key: str = Depends(verify_api_key)
):
    """
    OpenAI-compatible chat completions endpoint.
    
    Example:
    ```
    curl -X POST http://localhost:8000/v1/chat/completions \
      -H "X-API-Key: your-key" \
      -H "Content-Type: application/json" \
      -d '{
        "model": "anthropic/claude-3.5-sonnet",
        "messages": [{"role": "user", "content": "Hello!"}]
      }'
    ```
    """
    
    try:
        # Forward to OpenRouter
        response, cost_usd = await router.chat_completion(request, api_key)
        
        # Log usage
        db.log_usage(
            api_key=api_key,
            model=request.model,
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            cost_usd=cost_usd
        )
        
        # Return response with cost header
        response_dict = response.model_dump(by_alias=True)
        
        return JSONResponse(
            content=response_dict,
            headers={
                "X-Cost-USD": f"{cost_usd:.6f}",
                "X-Prompt-Tokens": str(response.usage.prompt_tokens),
                "X-Completion-Tokens": str(response.usage.completion_tokens),
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OpenRouter error: {str(e)}")


@app.get("/admin/keys", tags=["Admin"])
async def list_keys(admin_key: str = Header(None, alias="X-Admin-Key")):
    """List all API keys and their usage (admin only)."""
    if admin_key != config.ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")
    
    import sqlite3
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT api_key, cumulative_cost, requests_count, last_used_at, is_active
        FROM api_keys
    """)
    rows = cursor.fetchall()
    conn.close()
    
    return {
        "keys": [
            {
                "api_key": row[0],
                "cumulative_cost": row[1],
                "requests_count": row[2],
                "last_used_at": row[3],
                "is_active": row[4]
            }
            for row in rows
        ]
    }


@app.post("/admin/keys", tags=["Admin"])
async def create_key(admin_key: str = Header(None, alias="X-Admin-Key")):
    """Create a new API key (admin only)."""
    if admin_key != config.ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")
    
    import secrets
    new_key = f"sk-{secrets.token_urlsafe(32)}"
    db.get_or_create_key(new_key)
    
    return {"api_key": new_key, "message": "Store this safely. It won't be shown again."}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=config.HOST,
        port=config.PORT,
        log_level="info" if not config.DEBUG else "debug"
    )
