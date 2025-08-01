#!/bin/bash

echo "🎯 Starting AI Company Screener Demo..."

# Function to check if port is in use
check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null ; then
        echo "❌ Port $port is already in use. Please stop any existing servers on port $port."
        return 1
    fi
    return 0
}

# Function to kill processes using specific ports
kill_port_processes() {
    local port=$1
    local pids=$(lsof -ti:$port 2>/dev/null)
    if [ ! -z "$pids" ]; then
        echo "🛑 Killing processes using port $port..."
        kill -9 $pids 2>/dev/null
        sleep 1
    fi
}

# Function to cleanup on exit
cleanup() {
    echo "🛑 Stopping servers..."
    pkill -f "uvicorn main:app"
    pkill -f "python -m http.server"
    exit 0
}

# Set up signal handlers
trap cleanup SIGINT SIGTERM

# Check if ports are available and kill existing processes if needed
echo "🔍 Checking if ports are available..."
if ! check_port 8000; then
    echo "💡 Attempting to kill existing processes on port 8000..."
    kill_port_processes 8000
    if ! check_port 8000; then
        echo "❌ Port 8000 is still in use. Please manually stop any servers on port 8000."
        exit 1
    fi
fi

if ! check_port 8080; then
    echo "💡 Attempting to kill existing processes on port 8080..."
    kill_port_processes 8080
    if ! check_port 8080; then
        echo "❌ Port 8080 is still in use. Please manually stop any servers on port 8080."
        exit 1
    fi
fi

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
python -m http.server 8080 --bind 127.0.0.1 &
FRONTEND_PID=$!

# Wait a moment for frontend to start
sleep 2

echo ""
echo "✅ Demo servers started!"
echo ""
echo "📱 Frontend: http://localhost:8080/frontend.html"
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