#!/bin/bash
# Script to start the backend server

echo "Starting LeadGen AI Backend Server..."
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  Warning: .env file not found!"
    echo "Creating .env from env.example..."
    cp env.example .env
    echo "Please edit .env and add your configuration before continuing."
    echo ""
fi

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Install Playwright browsers
echo "Installing Playwright browsers..."
playwright install chromium

# Start the server
echo ""
echo "🚀 Starting backend server on http://localhost:8000"
echo "📚 API Documentation: http://localhost:8000/docs"
echo ""
# Use run_server.py if it exists (for Windows compatibility), otherwise use backend.py
if [ -f "run_server.py" ]; then
    python run_server.py
else
    python backend.py
fi

