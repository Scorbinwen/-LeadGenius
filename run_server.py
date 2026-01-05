"""
Wrapper script to start the backend server with proper Windows event loop policy
This ensures Playwright can create subprocesses on Windows
"""
# CRITICAL: Set event loop policy BEFORE any imports

# Now import normally - but import backend AFTER policy is set
from backend import app

from uvicorn import Config, Server

if __name__ == "__main__":
    print("Starting LeadGen AI Backend Server...")
    print("Server will be available at http://localhost:8000")
    print("API Documentation: http://localhost:8000/docs")
    print()
    

    config = Config(
        app,  # Pass app object directly, not "backend:app" string
        host="0.0.0.0",
        port=8000,
        reload=False,  # Disable reload to avoid subprocess issues
        log_level="info",
        loop="asyncio"  # Explicitly use asyncio loop
    )
    
    server = Server(config)

    
    # Use server.run() which internally uses asyncio.run()
    # The policy we set should be used when asyncio.run() creates the loop
    server.run()

