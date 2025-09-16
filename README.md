<div align="center">
  <img width="120" height="120" src="/assets/logo.png" alt="iCloud CalDAV MCP Server Logo">
  <h1><b>iCloud CalDAV MCP Server</b></h1>
  <p>
    An experimental <strong>iCloud calendar integration</strong> for Poke using <a href="https://github.com/jlowin/fastmcp">FastMCP</a> that provides seamless CalDAV access to your iCloud calendars with full CRUD operations and alarm management.
  </p>
  <p><em>Built for <a href="https://poke.com">Poke</a> but should work with other agents.</em></p>
</div><br><br>



[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/josejacas/iCal-Poke-Bridge)

> **⚠️ Important Notes**
> - **Apple App-Specific Password Required**: This server requires an Apple App-Specific Password, not your main Apple ID password
> - **iCloud CalDAV Limitations**: Some operations (like reminder modifications) have limitations due to iCloud's CalDAV complexities. Work in progress.

## 🚀 Quick Start

1. **Deploy**: Click the "Deploy to Render" button above
2. **Configure**: Set your iCloud app specific credentials as environment variables
3. **Connect**: Add to Poke at [poke.com/settings/connections](https://poke.com/settings/connections)
4. **Test**: Ask Poke to check your calendar!

## 🌟 Features

- 📅 **Full Calendar Access** - List, create, update, and delete iCloud calendar events
- ⏰ **Event Reminder Management** - Create events with multiple alarms and notifications
- 🔍 **Search** - Find events across all calendars with flexible date ranges
- 🌐 **Timezone Support** - Handle events in any timezone with proper conversion
- 🛡️ **Secure** - Uses Apple App-Specific Passwords for enhanced security

## 📋 Complete Setup Guide

### 1. Prerequisites

Before starting, you'll need:
- An [Apple ID](https://appleid.apple.com) with iCloud calendar enabled
- A [Render](https://render.com) account (for deployment) or VPS
- A [Poke](https://poke.com) account

### 2. Get Apple App-Specific Password

1. Go to [account.apple.com](https://account.apple.com) and sign in
2. Navigate to **Sign-In and Security** → **App-Specific Passwords**
3. Click **Generate an app-specific password**
4. Enter a label like "iCloud CalDAV MCP Server"
5. **Copy the generated password** - you won't be able to see it again!

### 3. Deploy the Server

#### Option A: Deploy to Render (Recommended)
1. Click the "Deploy to Render" button above
2. Connect your GitHub account to Render
3. Fork the repository when prompted
4. IMPORTANT: Configure environment variables (see step 4)

#### Option B: VPS Deployment (Best Performance)
```bash
# On your VPS (Ubuntu/Debian):
git clone https://github.com/your-username/icloud-caldav-mcp.git
cd icloud-caldav-mcp
sudo apt update && sudo apt install python3-pip
pip3 install -r requirements.txt

# Set environment variables
export ICLOUD_EMAIL="your-email@icloud.com"
export ICLOUD_PASSWORD="your-app-specific-password"

# Run the server
python3 src/server.py
```

### 4. Configure Environment Variables in Render 

Set these in your Render dashboard settings:

```bash
# Required - iCloud Credentials
ICLOUD_EMAIL=your-email@icloud.com
ICLOUD_PASSWORD=your-16-character-app-specific-password

```

### 5. Connect to Poke

1. Go to [poke.com/settings/connections](https://poke.com/settings/connections)
2. Add a new MCP server:
   - **MCP Name**: `iCloud Calendar` (or any name you prefer)
   - **Server URL**: `https://your-render-app-name.onrender.com/mcp`
   - **Transport**: Streamable HTTP
3. Test the connection by asking Poke: `"Check my icloud calendar connection status"`

## 🛠️ Local Development

### Setup Development Environment

```bash
# Clone the repository
git clone https://github.com/your-username/icloud-caldav-mcp.git
cd icloud-caldav-mcp

# Create virtual environment
conda create -n icloud-mcp python=3.13
conda activate icloud-mcp

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export ICLOUD_EMAIL="your-email@icloud.com"
export ICLOUD_PASSWORD="your-app-specific-password"
```

### Run Locally

```bash
# Start the server
python src/server.py

# In another terminal, test with MCP Inspector
npx @modelcontextprotocol/inspector
```

Open http://localhost:3000 and connect to `http://localhost:8000/mcp` using "Streamable HTTP" transport.

## 🛠️ Available Tools & Capabilities

| Tool Name | Description | Example Usage |
|-----------|-------------|---------------|
| `get_connection_status` | Test iCloud CalDAV connection | Connection Testing |
| `list_my_calendars` | List all your calendars | "Show me all my calendars" |
| `list_my_events` | List events with date range ⚠️ Use 2 day minimum | "What events do I have this week?" |
| `create_my_event` | Create events with alarms | "Create a meeting tomorrow at 2pm" |
| `update_my_event` | Update existing events | "Change my meeting title to 'Team Sync'" |
| `delete_my_event` | Delete events | "Cancel my dentist appointment" |
| `list_event_alarms` | List alarms for an event | "What reminders do I have set?" |

### Example Poke Commands

Ask Poke questions like:
- "What events do I have this week?"
- "Create a dentist appointment for next Tuesday at 3pm with a 30-minute reminder"
- "Change my 'Meeting' event title to 'Team Standup'"
- "Show me all my calendars"
- "Delete the event called 'Old Meeting'"
- "What alarms are set for my doctor appointment?"

## 🏗️ Project Structure

```
icloud-caldav-mcp/
├── src/                          # Main application code
│   ├── server.py                 # FastMCP server and MCP tools
│   ├── caldav_client.py         # CalDAV client for iCloud
│   ├── ical_utils.py            # iCalendar utilities
│   └── __init__.py
├── assets/                       # Static assets
│   └── logo.png                  # Logo image
├── requirements.txt              # Python dependencies
├── render.yaml                   # Render deployment config
└── README.md                     # This file
```

## 🔧 Customization

### Adding New MCP Tools

Add new tools by decorating functions with `@mcp.tool`:

```python
@mcp.tool
def create_recurring_event(summary: str, start: str, rrule: str) -> dict:
    """Create a recurring calendar event."""
    # Implementation here
    return {"success": True, "event_url": "..."}
```

## 🚀 Future Enhancements

Potential improvements for future versions:

- **Recurrence**: Recurring event patterns
- **Actual Alarm Support**: Proper implementation of adding/editing/removing event alarms

## HTTP Request Format (For AI Agents)

**📡 CRITICAL: All tool calls must use this exact format to avoid 400/406 errors:**

### Required Headers
```json
{
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream"
}
```

### Request Body Format (JSON-RPC 2.0 - REQUIRED)
```json
{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
        "name": "tool_name_here",
        "arguments": {
            "param1": "value1",
            "param2": "value2"
        }
    }
}
```

**⚠️ CRITICAL:** All requests MUST include `jsonrpc: "2.0"` and `id` fields or you'll get 400 errors!

### Example: List Events
```bash
curl -X POST https://your-server.onrender.com/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
        "name": "list_my_events",
        "arguments": {
            "calendar_name": "Work",
            "start": "2025-09-01",
            "end": "2025-09-07",
            "limit": 5
        }
    }
}'
```

### Response Format
The server responds with **Server-Sent Events** format:
```
data: {"jsonrpc": "2.0", "id": 1, "result": {"success": true, "events": [...]}}
```

**⚠️  IMPORTANT:** The response body is prefixed with `data: ` - AI agents must parse this correctly!

## 🔍 Troubleshooting

### Connection Issues
- ❌ **"Failed to connect to CalDAV server"**
  - ✅ Verify your Apple App-Specific Password is correct (16 characters)
  - ✅ Check that 2FA is enabled on your Apple ID
  - ✅ Ensure your iCloud email is exactly correct
  - ✅ Try generating a new App-Specific Password

### Server Issues  
- ❌ **Server won't start**
  - ✅ Check Render/VPS logs for startup errors
  - ✅ Verify environment variables are set correctly
  - ✅ Ensure Python dependencies are installed

### AI Agent Issues
- ❌ **"400 Bad Request" errors**
  - ✅ Ensure JSON-RPC 2.0 format with `jsonrpc` and `id` fields
  - ✅ Use correct headers: `Content-Type: application/json`
  - ✅ Check the endpoint URL includes `/mcp`

- ❌ **Events not found after creation**
  - ✅ Use broader date ranges (minimum 2 days)
  - ✅ Search across all calendars if unsure
