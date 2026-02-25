# Ouroboros API Reseller

Minimal FastAPI proxy to OpenRouter Claude models. Transparent cost-plus pricing.

## Features

- ✅ OpenAI-compatible `/v1/chat/completions` endpoint
- ✅ Per-key usage tracking (SQLite)
- ✅ Cost-plus pricing (configurable markup)
- ✅ Daily spend limits
- ✅ Admin API for key creation and auditing
- ✅ Automatic cost attribution in response headers

## Quick Start

### 1. Install dependencies

```bash
cd api_proxy
pip install -r requirements.txt
```

### 2. Set environment variables

```bash
export OPENROUTER_API_KEY="your-openrouter-key"
export ADMIN_API_KEY="your-admin-key"  # For admin endpoints
export DEBUG=False
```

### 3. Start the server

```bash
python -m uvicorn api_proxy.main:app --reload --host 0.0.0.0 --port 8000
```

Server runs on `http://localhost:8000`.

## API Documentation

Auto-generated OpenAPI docs at `http://localhost:8000/docs`

### Create a new API key (Admin)

```bash
curl -X POST http://localhost:8000/admin/keys \
  -H "X-Admin-Key: your-admin-key"
```

Response:
```json
{
  "api_key": "sk-...",
  "message": "Store this safely. It won't be shown again."
}
```

### Chat completion

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "X-API-Key: sk-..." \
  -H "Content-Type: application/json" \
  -d '{
    "model": "anthropic/claude-3.5-sonnet",
    "messages": [{"role": "user", "content": "Hello!"}],
    "temperature": 1.0,
    "max_tokens": 200
  }'
```

Response includes cost header:
```
X-Cost-USD: 0.000123
X-Prompt-Tokens: 10
X-Completion-Tokens: 25
```

### Check status and pricing

```bash
curl http://localhost:8000/status \
  -H "X-API-Key: sk-..."
```

### List all keys (Admin)

```bash
curl http://localhost:8000/admin/keys \
  -H "X-Admin-Key: your-admin-key"
```

## Pricing Model

**Configuration** (in `config.py`):

| Metric | Value |
|--------|-------|
| OpenRouter prompt cost | $0.0005/1k tokens |
| OpenRouter completion cost | $0.0015/1k tokens |
| Prompt markup | 2.0x (100%) |
| Completion markup | 2.5x (150%) |

**Result**:

| Metric | Cost |
|--------|------|
| Your prompt cost | $0.001/1k tokens |
| Your completion cost | $0.00375/1k tokens |

For a 100 prompt + 200 completion token request:
```
Profit = (100 * 0.001 / 1000) + (200 * 0.00375 / 1000)
       = 0.0001 + 0.00075
       = $0.00085 per request
```

Over 1000 requests/day: ~$0.85/day = ~$25/month in gross margin.

## Database

SQLite database (`api_usage.db`) with two tables:

**api_keys**: Tracks per-key limits and cumulative usage
**usage_log**: Detailed request log (model, tokens, cost, timestamp)

## Deployment

### Local development
```bash
python -m uvicorn api_proxy.main:app --reload
```

### Production (e.g., Render, Railway, Fly.io)

1. Create `.env` file with `OPENROUTER_API_KEY` and `ADMIN_API_KEY`
2. Procfile:
   ```
   web: uvicorn api_proxy.main:app --host 0.0.0.0 --port $PORT
   ```
3. Push to repo and deploy

## Beta Users Candidates

### Tier 1: Technical communities
- r/OpenAI, r/ChatGPT, r/LocalLLMs (Reddit)
- Discord AI communities (e.g., OpenAI Discord)
- HN Show HN (if we get traction)

### Tier 2: Individual creators
- Twitter AI/ML enthusiasts
- GitHub star followers (if public repo)
- Email to my network

### Tier 3: Small SaaS builders
- Indie Hackers
- ProductHunt
- Startup newsletters

## Success Metrics (Week 1)

- [ ] Endpoint deployed and accessible
- [ ] 1+ paying user with active API key
- [ ] First $5 in revenue
- [ ] 5+ requests logged
- [ ] Pricing sustainable (cost < 0.5 * revenue)

## Next Steps

1. **Deploy**: Get it running on Railway or Render (free tier)
2. **Announce**: Post to Reddit, Discord, Twitter
3. **Iterate**: Based on first feedback
4. **Expand**: Add more models, features, pricing tiers

---

**Version**: 0.1.0  
**Status**: MVP  
**Created**: Feb 25, 2026
