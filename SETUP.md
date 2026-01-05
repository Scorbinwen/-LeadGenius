# Backend Setup Guide

This guide will help you set up the backend API server for LeadGen AI.

## Quick Start

### Option 1: Using the Startup Scripts

**On Linux/Mac:**
```bash
chmod +x start_backend.sh
./start_backend.sh
```

**On Windows:**
```cmd
start_backend.bat
```

### Option 2: Manual Setup

1. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Install Playwright browsers**
   ```bash
   playwright install chromium
   ```

4. **Configure environment**
   ```bash
   cp env.example .env
   # Edit .env with your settings
   ```

5. **Start the server**
   ```bash
   python backend.py
   ```

## Configuration

### Environment Variables

Edit `.env` file with your configuration:

```env
# LLM Provider (choose one)
LLM_PROVIDER=ollama  # or "openai" or "anthropic"

# For Ollama (local LLM)
OLLAMA_BASE_URL=http://localhost:11434/v1
LLM_MODEL=Qwen2

# For OpenAI
OPENAI_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini

# For Anthropic
ANTHROPIC_API_KEY=sk-ant-...
LLM_MODEL=claude-3-5-sonnet-20241022
```

### LLM Setup

#### Using Ollama (Recommended for Development)

1. Install Ollama: https://ollama.ai
2. Pull a model:
   ```bash
   ollama pull Qwen2
   # or
   ollama pull llama2
   ```
3. Set in `.env`:
   ```env
   LLM_PROVIDER=ollama
   OLLAMA_BASE_URL=http://localhost:11434/v1
   LLM_MODEL=Qwen2
   ```

#### Using OpenAI

1. Get API key from https://platform.openai.com
2. Set in `.env`:
   ```env
   LLM_PROVIDER=openai
   OPENAI_API_KEY=sk-your-key-here
   LLM_MODEL=gpt-4o-mini
   ```

#### Using Anthropic

1. Get API key from https://console.anthropic.com
2. Set in `.env`:
   ```env
   LLM_PROVIDER=anthropic
   ANTHROPIC_API_KEY=sk-ant-your-key-here
   LLM_MODEL=claude-3-5-sonnet-20241022
   ```

## Testing the Backend

### Health Check

```bash
curl http://localhost:8000/health
```

### API Documentation

Once the server is running, visit:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Test Login

```bash
curl -X POST http://localhost:8000/api/login
```

This will open a browser window. Complete the login process in the browser.

## Troubleshooting

### Import Errors

If you get import errors for `xiaohongshu_mcp`:
- Make sure `xiaohongshu_mcp.py` is in the same directory as `backend.py`
- Check that all dependencies are installed: `pip install -r requirements.txt`

### Playwright Issues

If Playwright fails:
```bash
playwright install chromium
playwright install-deps  # Install system dependencies (Linux)
```

### Port Already in Use

If port 8000 is already in use:
- Change the port in `backend.py`:
  ```python
  uvicorn.run("backend:app", port=8001, ...)
  ```
- Update `API_BASE_URL` in `api.js` to match

### Browser Won't Open

- Make sure you're running in a graphical environment (not SSH without X11)
- The browser runs in non-headless mode by default
- Check that Chromium is installed: `playwright install chromium`

## Production Deployment

For production, consider:

1. **Use a process manager** (PM2, systemd, etc.)
2. **Set up reverse proxy** (Nginx, Caddy)
3. **Enable HTTPS** with SSL certificates
4. **Configure CORS** properly in `backend.py`
5. **Use environment-specific configs**
6. **Set up logging** and monitoring
7. **Run browser in headless mode** for production

Example production command:
```bash
uvicorn backend:app --host 0.0.0.0 --port 8000 --workers 4
```

