#!/bin/bash

echo "🎯 Starting AI Company Screener Demo..."

# Function to cleanup on exit
cleanup() {
    echo "🛑 Stopping servers..."
    pkill -f "uvicorn main:app"
    pkill -f "python -m http.server"
    exit 0
}

# Set up signal handlers
trap cleanup SIGINT SIGTERM

# Start backend
echo "🚀 Starting backend server..."
cd backend
source venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
cd ..

# Wait a moment for backend to start
sleep 3

# Start frontend
echo "🌐 Starting frontend server..."
python -m http.server 3000 --bind 127.0.0.1 &
FRONTEND_PID=$!

# Wait a moment for frontend to start
sleep 2

echo ""
echo "✅ Demo servers started!"
echo ""
echo "📱 Frontend: http://localhost:3000/frontend.html"
echo "🔧 Backend API: http://localhost:8000"
echo "📚 API Docs: http://localhost:8000/docs"
echo ""
echo "🎯 Demo Companies to try:"
echo "  • Apple Inc. / AAPL"
echo "  • Microsoft Corporation / MSFT"
echo "  • Tesla, Inc. / TSLA"
echo ""
echo "Press Ctrl+C to stop servers"

# Wait for user to stop
wait 