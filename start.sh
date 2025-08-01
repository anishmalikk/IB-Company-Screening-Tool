#!/bin/bash

echo "🚀 Starting AI Company Screener..."

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
uvicorn main:app --reload &
BACKEND_PID=$!
cd ..

# Wait a moment for backend to start
sleep 3

# Start frontend
echo "🌐 Starting frontend server..."
python -m http.server 8080 &
FRONTEND_PID=$!

# Wait a moment for frontend to start
sleep 2

echo ""
echo "✅ Servers started!"
echo ""
echo "📱 Frontend: http://localhost:8080/frontend.html"
echo "🔧 Backend API: http://localhost:8000"
echo "📚 API Docs: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop servers"

# Wait for user to stop
wait 