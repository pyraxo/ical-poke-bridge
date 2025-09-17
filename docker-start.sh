#!/bin/bash

# iCloud CalDAV MCP Server - Docker Startup Script
# This script helps you start the server with Docker Compose

set -e

echo "🚀 Starting iCloud CalDAV MCP Server with Docker..."

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "❌ Error: .env file not found!"
    echo "📝 Please create a .env file with your iCloud credentials:"
    echo ""
    echo "ICLOUD_EMAIL=your-email@icloud.com"
    echo "ICLOUD_PASSWORD=your-16-character-app-specific-password"
    echo ""
    echo "💡 You can copy .env.example to .env and fill in your values."
    exit 1
fi

# Check if required environment variables are set
if ! grep -q "ICLOUD_EMAIL=" .env || ! grep -q "ICLOUD_PASSWORD=" .env; then
    echo "❌ Error: Required environment variables not found in .env file!"
    echo "📝 Please ensure your .env file contains:"
    echo "ICLOUD_EMAIL=your-email@icloud.com"
    echo "ICLOUD_PASSWORD=your-16-character-app-specific-password"
    exit 1
fi

# Create logs directory if it doesn't exist
mkdir -p logs

# Start the services
echo "🔨 Building and starting Docker containers..."
docker-compose up --build -d

echo ""
echo "✅ Server started successfully!"
echo "🌐 Server URL: http://localhost:8000"
echo "🔗 MCP Endpoint: http://localhost:8000/mcp"
echo ""
echo "📊 To view logs: docker-compose logs -f"
echo "🛑 To stop: docker-compose down"
echo "🔍 To check status: docker-compose ps"
