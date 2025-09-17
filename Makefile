# iCloud CalDAV MCP Server - Docker Management

.PHONY: help build up down logs restart clean status test

# Default target
help:
	@echo "🚀 iCloud CalDAV MCP Server - Docker Commands"
	@echo ""
	@echo "📋 Available commands:"
	@echo "  make build     - Build the Docker image"
	@echo "  make up        - Start the services"
	@echo "  make down      - Stop the services"
	@echo "  make restart   - Restart the services"
	@echo "  make logs      - View service logs"
	@echo "  make status    - Check service status"
	@echo "  make test      - Test the MCP connection"
	@echo "  make clean     - Clean up Docker resources"
	@echo ""
	@echo "💡 Make sure to create .env file first:"
	@echo "   cp env.example .env"
	@echo "   # Edit .env with your iCloud credentials"

# Build the Docker image
build:
	@echo "🔨 Building Docker image..."
	docker-compose build

# Start the services
up:
	@echo "🚀 Starting services..."
	docker-compose up -d
	@echo "✅ Services started! Check status with 'make status'"

# Stop the services
down:
	@echo "🛑 Stopping services..."
	docker-compose down

# Restart the services
restart: down up

# View logs
logs:
	@echo "📊 Viewing logs (Ctrl+C to exit)..."
	docker-compose logs -f

# Check service status
status:
	@echo "📊 Service status:"
	docker-compose ps
	@echo ""
	@echo "🌐 Server should be available at: http://localhost:8000"
	@echo "🔗 MCP Endpoint: http://localhost:8000/mcp"

# Test the MCP connection
test:
	@echo "🧪 Testing MCP connection..."
	@curl -s http://localhost:8000/mcp \
		-H "Content-Type: application/json" \
		-H "Accept: application/json, text/event-stream" \
		-d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_server_info","arguments":{}}}' \
		&& echo "✅ MCP server is responding!" || echo "❌ MCP server test failed"

# Clean up Docker resources
clean:
	@echo "🧹 Cleaning up Docker resources..."
	docker-compose down -v
	docker system prune -f
	@echo "✅ Cleanup complete!"

# Development shortcuts
dev: build up logs

# Quick setup for new users
setup:
	@echo "⚙️  Setting up iCloud CalDAV MCP Server..."
	@if [ ! -f .env ]; then \
		cp env.example .env; \
		echo "📝 Created .env file from template"; \
		echo "⚠️  Please edit .env with your iCloud credentials!"; \
	else \
		echo "✅ .env file already exists"; \
	fi
	@make build
	@echo "🎉 Setup complete! Run 'make up' to start the server."
