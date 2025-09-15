# iCloud CalDAV MCP Server

A [FastMCP](https://github.com/jlowin/fastmcp) server that connects to your iCloud calendar via CalDAV. Deploy to Render with just your iCloud credentials as environment variables.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/josejacas/iCal-Poke-Bridge)

## Local Development

### Setup

Fork the repo, then run:

```bash
git clone <your-repo-url>
cd iCal-Poke-Bridge
conda create -n mcp-server python=3.13
conda activate mcp-server
pip install -r requirements.txt
```

### Environment Variables

Set your iCloud credentials as environment variables:

```bash
ICLOUD_EMAIL="your-email@icloud.com"
ICLOUD_PASSWORD="your-app-specific-password"
```

**Important:** Use an [Apple App-Specific Password](https://support.apple.com/en-us/HT204397), not your main Apple ID password.

### Test

```bash
python src/server.py
# then in another terminal run:
npx @modelcontextprotocol/inspector
```

Open http://localhost:3000 and connect to `http://localhost:8000/mcp` using "Streamable HTTP" transport (NOTE THE `/mcp`!).

### Available Tools

**Main tools:**
- `list_my_calendars()` - List all your calendars
- `list_my_events(start?, end?, calendar_name?)` - List events ⚠️ Use 2-7 day ranges minimum
- `create_my_event(summary, start, end, calendar_name?, description?, location?, all_day?, alarm_configs?)` - Create an event with optional alarms
- `update_my_event(event_url?, uid?, summary?, start?, end?, ...)` - Update an existing event
- `delete_my_event(event_url)` - Delete an event
- `list_event_alarms(event_url?, uid?)` - List alarms for an event
- `get_connection_status()` - Check iCloud connection

## Deployment

### Prerequisites

1. **Apple App-Specific Password**: Generate one at [appleid.apple.com](https://appleid.apple.com) → Sign-In and Security → App-Specific Passwords
2. **GitHub Account**: Fork this repository to your GitHub account

### Option 1: One-Click Deploy
1. Click the "Deploy to Render" button above
2. Connect your GitHub account to Render
3. Select your forked repository
4. **Set Environment Variables**:
   - `ICLOUD_EMAIL`: Your iCloud email address
   - `ICLOUD_PASSWORD`: Your Apple app-specific password (not your main password!)
5. Click "Deploy Web Service"

### Option 2: Manual Deployment
1. Fork this repository
2. Connect your GitHub account to Render
3. Create a new Web Service on Render
4. Connect your forked repository
5. **Set Environment Variables**:
   - `ICLOUD_EMAIL`: Your iCloud email address  
   - `ICLOUD_PASSWORD`: Your Apple app-specific password
6. Render will automatically detect the `render.yaml` configuration

Your server will be available at `https://your-service-name.onrender.com/mcp` (NOTE THE `/mcp`!)

### Security Notes
- ✅ Your credentials are encrypted at rest in Render's environment variables
- ✅ Use Apple App-Specific Passwords (not your main Apple ID password)
- ✅ Each deployment is isolated to your own iCloud account
- ✅ No calendar data is stored on the server

## Poke Setup

1. Deploy your server to Render (see Deployment section above)
2. Go to [poke.com/settings/connections](https://poke.com/settings/connections)
3. Add a new MCP connection:
   - **Name**: "iCloud Calendar" (or whatever you prefer)
   - **URL**: `https://your-service-name.onrender.com/mcp`
   - **Transport**: Streamable HTTP
4. Test the connection by asking Poke: `Tell the subagent to use the "iCloud Calendar" integration's "get_connection_status" tool`

If you run into persistent issues of Poke not calling the right MCP (e.g. after you've renamed the connection), you may send `clearhistory` to Poke to delete all message history and start fresh.

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

## Usage Examples

Once connected to Poke, you can ask things like:
- "What events do I have this week?" (uses `list_my_events` with proper date range)
- "Create a meeting tomorrow at 2pm for 1 hour called 'Team Standup'" (uses `create_my_event`)
- "Add a 15-minute reminder to my dentist appointment" (finds event, then recreates with alarm)
- "Change my meeting title from 'Standup' to 'Daily Sync'" (uses `update_my_event`)
- "Show me all my calendars" (uses `list_my_calendars`)
- "Delete my meeting with John tomorrow" (Poke finds the event via `list_my_events`, then uses `delete_my_event`)

### Important Notes:
- **Always use multi-day date ranges** (minimum 2-7 days) when searching for events due to iCloud CalDAV limitations
- **For alarm modifications**: Use delete + recreate pattern since iCloud CalDAV doesn't reliably support alarm updates on existing events (or I havent been able to get them to work)

## Customization

Add more tools by decorating functions with `@mcp.tool`:

```python
@mcp.tool
def my_custom_tool(param1: str, param2: int) -> str:
    """Description of what this tool does."""
    # Your implementation here
    return "result"
```

## Troubleshooting

**Connection Issues:**
- Verify your Apple App-Specific Password is correct
- Check that 2FA is enabled on your Apple ID
- Ensure your iCloud email is correct

**Server Issues:**
- Check Render logs for startup errors
- Use `get_connection_status` tool to test connectivity
- Verify environment variables are set correctly in Render dashboard
