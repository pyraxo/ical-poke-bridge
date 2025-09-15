#!/usr/bin/env python3
"""
iCloud CalDAV MCP Server
A FastMCP server that provides calendar operations for iCloud using CalDAV.
"""
import os
import json
import logging
import sys
from datetime import datetime, date, timezone, timedelta
from typing import List, Dict, Optional
from uuid import uuid4

from fastmcp import FastMCP
from icalendar import Calendar as IcsCalendar, Event as IcsEvent

from caldav_client import CalDAVClient
from ical_utils import ICalUtils

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Initialize FastMCP
mcp = FastMCP("iCloud CalDAV MCP Server")

# Initialize CalDAV client
caldav_client = CalDAVClient()
ical_utils = ICalUtils()


# =============================================================================
# MCP TOOLS
# =============================================================================

@mcp.tool(description=(
    "Greet a user by name with a welcome message from the MCP server. "
    "⚡ FIRST TIME? Call get_server_info() for complete HTTP request format guidance! "
    "All tools require: POST /mcp, headers {'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream'}, JSON-RPC 2.0 format with jsonrpc and id fields."
))
def greet(name: str) -> str:
    """Simple greeting function for testing MCP connectivity."""
    logger.info(f"🔧 TOOL CALL: greet(name='{name}')")
    return f"Hello, {name}! Welcome to the iCloud CalDAV MCP server."


@mcp.tool(description=(
    "Get information about the MCP server including name, version, environment, Python version, and HTTP request format guidance. "
    "📡 IMPORTANT: This server requires specific HTTP headers and JSON-RPC format for all tool calls!"
))
def get_server_info() -> dict:
    """Returns basic information about the MCP server for debugging/monitoring."""
    return {
        "server_name": "iCloud CalDAV MCP Server",
        "version": "1.0.0",
        "environment": os.environ.get("ENVIRONMENT", "development"),
        "python_version": os.sys.version.split()[0],
        "http_request_format": {
            "method": "POST",
            "endpoint": "/mcp",
            "required_headers": {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            },
            "json_body_format": {
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
            },
            "response_format": "Server-Sent Events (text/event-stream) with 'data: ' prefix"
        }
    }


@mcp.tool(description="Test the connection status to iCloud CalDAV using environment variables.")
def get_connection_status() -> Dict[str, object]:
    """Test the iCloud CalDAV connection."""
    logger.info("🔧 TOOL CALL: get_connection_status()")
    try:
        if not caldav_client.connect():
            return {
                "success": False,
                "error": "Failed to connect to CalDAV server"
            }
        
        calendars = caldav_client.get_calendars()
        result = {
            "success": True,
            "status": "connected",
            "email": caldav_client.email,
            "calendars_found": len(calendars),
            "server_url": "https://caldav.icloud.com"
        }
        logger.info(f"✅ get_connection_status result: {result}")
        return result
    except Exception as e:
        logger.error(f"❌ get_connection_status failed: {type(e).__name__}: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


@mcp.tool(description="List your iCloud calendars.")
def list_my_calendars() -> Dict[str, object]:
    """List calendars."""
    logger.info("🔧 TOOL CALL: list_my_calendars()")
    try:
        if not caldav_client.connect():
            return {
                "success": False,
                "error": "Failed to connect to CalDAV server"
            }
        
        calendars = caldav_client.get_calendars()
        logger.info(f"✅ list_my_calendars found {len(calendars)} calendars")
        return {
            "success": True,
            "calendars": calendars,
            "count": len(calendars)
        }
    except Exception as e:
        logger.error(f"❌ list_my_calendars failed: {type(e).__name__}: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


@mcp.tool(description=(
    "List events from your iCloud calendars. "
    "If no calendar_name is specified, searches ALL calendars. "
    "Dates accept YYYY-MM-DD or full ISO-8601; defaults to past 7 days through next 30 days. "
    "⚠️ IMPORTANT: Don't search single-day ranges! Always use at least 2-7 days or broader ranges due to iCloud CalDAV limitations. "
    "Optional timezone_name parameter for date filtering (defaults to UTC if not provided)."
))
def list_my_events(
    start: Optional[str] = None,
    end: Optional[str] = None,
    calendar_name: Optional[str] = None,
    timezone_name: Optional[str] = None,
    limit: Optional[int] = None
) -> Dict[str, object]:
    """List events using credentials from environment variables."""
    logger.info(f"🔧 TOOL CALL: list_my_events(calendar_name='{calendar_name}', start='{start}', end='{end}')")
    
    try:
        if not caldav_client.connect():
            return {
                "success": False,
                "error": "Failed to connect to CalDAV server"
            }
        
        # Parse date range
        start_dt = ical_utils.parse_iso_datetime(start, timezone_name) or (datetime.now(timezone.utc) - timedelta(days=7))
        end_dt = ical_utils.parse_iso_datetime(end, timezone_name) or (datetime.now(timezone.utc) + timedelta(days=30))
        
        all_events = []
        
        if calendar_name:
            # Search specific calendar
            cal = caldav_client.find_calendar(calendar_name=calendar_name)
            events = cal.date_search(start_dt, end_dt)
            cal_display_name = calendar_name
            
            for ev in events:
                event_data = ical_utils.parse_event_from_ics(ev)
                event_data["calendar_name"] = cal_display_name
                all_events.append(event_data)
        else:
            # Search all calendars
            calendars = caldav_client.principal.calendars()
            
            for cal in calendars:
                cal_name = caldav_client._get_calendar_display_name(cal)
                try:
                    events = cal.date_search(start_dt, end_dt)
                    for ev in events:
                        event_data = ical_utils.parse_event_from_ics(ev)
                        event_data["calendar_name"] = cal_name
                        all_events.append(event_data)
                except Exception as e:
                    logger.warning(f"Failed to search calendar '{cal_name}': {e}")
                    continue
        
        # Sort by start time
        all_events.sort(key=lambda e: (e.get("start") or "", e.get("summary") or ""))
        
        # Apply limit
        if limit is not None:
            all_events = all_events[:max(0, int(limit))]
        
        logger.info(f"✅ list_my_events found {len(all_events)} events")
        return {
            "success": True,
            "events": all_events,
            "count": len(all_events),
            "date_range": {
                "start": start_dt.isoformat(),
                "end": end_dt.isoformat()
            }
        }
        
    except Exception as e:
        logger.error(f"❌ list_my_events failed: {type(e).__name__}: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


@mcp.tool(description=(
    "Create an event in your iCloud calendar."
    "Provide ISO datetimes or YYYY-MM-DD for all-day. "
    "If no calendar_name is provided, uses the first calendar. "
    "Supports recurrence rules (RRULE) and alarms. For multiple alarms, use alarm_configs as JSON array. "
    "For single alarm, use alarm_minutes_before. Optional timezone_name parameter (defaults to UTC if not provided). "
    "💡 ALARM MODIFICATIONS: To modify alarms on existing events, use the delete+recreate pattern: "
    "1) list_event_alarms to get current alarms, 2) delete_my_event, 3) create_my_event with modified alarm_configs."
))
def create_my_event(
    summary: str,
    start: str,
    end: str,
    calendar_name: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
    all_day: bool = False,
    timezone_name: Optional[str] = None,
    rrule: Optional[str] = None,
    alarm_minutes_before: Optional[int] = None,
    alarm_configs: Optional[str] = None
) -> Dict[str, object]:
    """Create an event using credentials from environment variables."""
    logger.info(f"🔧 TOOL CALL: create_my_event(summary='{summary}', start='{start}', end='{end}')")
    
    try:
        if not caldav_client.connect():
            return {
                "success": False,
                "error": "Failed to connect to CalDAV server"
            }
        
        cal = caldav_client.find_calendar(calendar_name=calendar_name)
        
        # Parse dates
        start_dt = ical_utils.parse_iso_datetime(start, timezone_name)
        end_dt = ical_utils.parse_iso_datetime(end, timezone_name)
        
        if all_day:
            if len(start.strip()) != 10 or len(end.strip()) != 10:
                return {
                    "success": False,
                    "error": "For all_day events, start and end must be YYYY-MM-DD."
                }
            start_date = date.fromisoformat(start.strip())
            end_date = date.fromisoformat(end.strip())
        else:
            if start_dt is None or end_dt is None:
                return {
                    "success": False,
                    "error": "Start and end must be valid ISO-8601 datetimes."
                }
        
        # Create iCalendar
        ics_cal = ical_utils.create_ics_calendar()
        evt = IcsEvent()
        evt.add('uid', f"{uuid4()}@icloud-caldav-mcp")
        evt.add('summary', summary)
        evt.add('dtstamp', datetime.now(timezone.utc))
        
        if description:
            evt.add('description', description)
        if location:
            evt.add('location', location)
        
        if all_day:
            evt.add('dtstart', start_date)
            evt.add('dtend', end_date)
        else:
            # Ensure timezone-aware datetime
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=timezone.utc)
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=timezone.utc)
            evt.add('dtstart', start_dt)
            evt.add('dtend', end_dt)
        
        if rrule:
            evt.add('rrule', rrule)
        
        # Handle alarms - support both single alarm and multiple alarms
        if alarm_configs is not None and alarm_configs.strip() != "":
            # Multiple alarms via JSON config
            try:
                parsed_alarm_configs = json.loads(alarm_configs)
                if isinstance(parsed_alarm_configs, list):
                    for alarm_config in parsed_alarm_configs:
                        minutes_before = alarm_config.get('minutes_before', 15)
                        description = alarm_config.get('description', 'Reminder')
                        action = alarm_config.get('action', 'DISPLAY')
                        related = alarm_config.get('related', 'START')
                        alarm = ical_utils.create_alarm(minutes_before, description, action, related)
                        evt.add_component(alarm)
            except Exception:
                # If JSON parsing fails, ignore alarm_configs
                pass
        elif alarm_minutes_before is not None and alarm_minutes_before >= 0:
            # Single alarm via simple parameter
            alarm = ical_utils.create_alarm(alarm_minutes_before)
            evt.add_component(alarm)
        
        ics_cal.add_component(evt)
        
        # Add timezones
        try:
            ics_cal.add_missing_timezones()
        except Exception:
            pass
        
        ics_text = ics_cal.to_ical().decode('utf-8')
        
        # Create event
        created = cal.add_event(ics_text)
        event_url = str(getattr(created, 'url', None)) if created is not None else None
        
        logger.info(f"✅ create_my_event created event: {event_url}")
        return {
            "success": True,
            "event_url": event_url or "",
            "summary": summary,
            "start": start,
            "end": end
        }
        
    except Exception as e:
        logger.error(f"❌ create_my_event failed: {type(e).__name__}: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


@mcp.tool(description=(
    "Update an existing event by URL or UID. You can change summary, start/end, "
    "description, location, and add/change RRULE. "
    "⚠️  ALARM LIMITATION: Due to iCloud CalDAV restrictions, alarm_minutes_before may not work reliably. "
    "💡 TO MODIFY ALARMS: Use the delete+recreate pattern: 1) list_event_alarms, 2) delete_my_event, 3) create_my_event with alarm_configs. "
    "If uid is provided, the first matching event is updated. "
    "Optional timezone_name parameter for new event times (defaults to UTC if not provided)."
))
def update_my_event(
    event_url: Optional[str] = None,
    uid: Optional[str] = None,
    summary: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    calendar_name: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
    timezone_name: Optional[str] = None,
    rrule: Optional[str] = None,
    alarm_minutes_before: Optional[int] = None
) -> Dict[str, object]:
    """Update an event using credentials from environment variables."""
    logger.info(f"🔧 TOOL CALL: update_my_event(event_url='{event_url}', uid='{uid}', summary='{summary}')")
    
    try:
        if not caldav_client.connect():
            return {
                "success": False,
                "error": "Failed to connect to CalDAV server"
            }
        
        if not event_url and not uid:
            return {
                "success": False,
                "error": "Provide either event_url or uid to identify the event to update."
            }
        
        cal = caldav_client.find_calendar(calendar_name=calendar_name)
        event_obj = caldav_client.get_event_by_url_or_uid(cal, event_url, uid)
        
        # Parse the original event to get existing properties
        try:
            original_cal = IcsCalendar.from_ical(ical_utils.get_event_ics_bytes(event_obj))
            original_event = None
            for comp in original_cal.walk('vevent'):
                original_event = comp
                break
        except Exception:
            original_event = None
        
        if original_event is None:
            return {
                "success": False,
                "error": "Unable to parse original event for update."
            }
        
        # Create a new event using the SIMPLE approach that works
        new_cal = ical_utils.create_ics_calendar()
        new_event = IcsEvent()
        
        # Copy essential properties (UID, timestamps, dates)
        if original_event.get('uid'):
            new_event.add('uid', original_event.get('uid'))
        if original_event.get('dtstamp'):
            new_event.add('dtstamp', original_event.get('dtstamp').dt)
        
        # Set dates (use new ones if provided, otherwise keep originals)
        if start is not None:
            new_start = ical_utils.parse_iso_datetime(start, timezone_name)
            if new_start:
                new_event.add('dtstart', new_start)
        elif original_event.get('dtstart'):
            new_event.add('dtstart', original_event.get('dtstart').dt)
            
        if end is not None:
            new_end = ical_utils.parse_iso_datetime(end, timezone_name)
            if new_end:
                new_event.add('dtend', new_end)
        elif original_event.get('dtend'):
            new_event.add('dtend', original_event.get('dtend').dt)
        
        # Set content (use new values if provided, otherwise keep originals)
        if summary is not None:
            new_event.add('summary', summary)
        elif original_event.get('summary'):
            new_event.add('summary', str(original_event.get('summary')))
            
        if description is not None:
            new_event.add('description', description)
        elif original_event.get('description'):
            new_event.add('description', str(original_event.get('description')))
            
        if location is not None:
            new_event.add('location', location)
        elif original_event.get('location'):
            new_event.add('location', str(original_event.get('location')))
            
        if rrule is not None:
            new_event.add('rrule', rrule)
        elif original_event.get('rrule'):
            new_event.add('rrule', str(original_event.get('rrule')))
        
        # Increment sequence number
        sequence = ical_utils.get_sequence_number(original_event)
        new_event.add('sequence', sequence)
        
        # Copy existing alarms (skip new alarm functionality for now - too complex)
        if original_event:
            for a in original_event.walk('valarm'):
                try:
                    from icalendar import Alarm as IcsAlarm
                    cloned = IcsAlarm.from_ical(a.to_ical())
                    new_event.add_component(cloned)
                except Exception:
                    new_event.add_component(a)
        
        new_cal.add_component(new_event)
        
        # Add timezones
        try:
            new_cal.add_missing_timezones()
        except Exception:
            pass
        
        # Save the updated event
        new_ics_text = new_cal.to_ical().decode('utf-8')
        logger.info(f"🔍 Generated iCalendar data for update:")
        logger.info(new_ics_text)
        
        event_obj.data = new_ics_text
        try:
            logger.info(f"🔄 Attempting to save event: {event_obj.url}")
            event_obj.save()
            logger.info(f"✅ Successfully saved updated event to iCloud")
        except Exception as save_error:
            logger.error(f"❌ Failed to save event update: {type(save_error).__name__}: {str(save_error)}")
            return {
                "success": False,
                "error": f"Failed to save event update: {str(save_error)}"
            }
        
        logger.info(f"✅ update_my_event updated event: {event_url or uid}")
        return {
            "success": True,
            "event_url": event_url or "",
            "uid": uid or "",
            "updated_fields": {
                "summary": summary,
                "start": start,
                "end": end,
                "description": description,
                "location": location
            }
        }
        
    except Exception as e:
        logger.error(f"❌ update_my_event failed: {type(e).__name__}: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


@mcp.tool(description="Delete an event by its CalDAV event URL using environment variables.")
def delete_my_event(event_url: str) -> Dict[str, object]:
    """Delete an event using credentials from environment variables."""
    logger.info(f"🔧 TOOL CALL: delete_my_event(event_url='{event_url}')")
    
    try:
        if not caldav_client.connect():
            return {
                "success": False,
                "error": "Failed to connect to CalDAV server"
            }
        
        import caldav
        ev = caldav.Event(client=caldav_client.client, url=event_url)
        ev.delete()
        
        logger.info(f"✅ delete_my_event deleted event: {event_url}")
        return {
            "success": True,
            "event_url": event_url
        }
        
    except Exception as e:
        logger.error(f"❌ delete_my_event failed: {type(e).__name__}: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


@mcp.tool(description=(
    "List VALARMs for an event by URL or UID. Returns alarm UID, Apple X-WR-ALARMUID, "
    "trigger (normalized minutes_before when relative), RELATED, ACTION, and DESCRIPTION."
))
def list_event_alarms(
    event_url: Optional[str] = None,
    uid: Optional[str] = None,
    calendar_name: Optional[str] = None
) -> Dict[str, object]:
    """List alarms for an event using credentials from environment variables."""
    logger.info(f"🔧 TOOL CALL: list_event_alarms(event_url='{event_url}', uid='{uid}')")
    
    try:
        if not caldav_client.connect():
            return {
                "success": False,
                "error": "Failed to connect to CalDAV server"
            }
        
        if not event_url and not uid:
            return {
                "success": False,
                "error": "Provide either event_url or uid to identify the event."
            }
        
        cal = caldav_client.find_calendar(calendar_name=calendar_name)
        event_obj = caldav_client.get_event_by_url_or_uid(cal, event_url, uid)
        cal_ics = IcsCalendar.from_ical(ical_utils.get_event_ics_bytes(event_obj))
        
        alarms = []
        for comp in cal_ics.walk('valarm'):
            trigger_prop = comp.get('trigger')
            minutes_before = None
            related = None
            if trigger_prop is not None:
                try:
                    from datetime import timedelta
                    value = getattr(trigger_prop, 'dt', trigger_prop)
                    rel_params = getattr(trigger_prop, 'params', {})
                    related = str(rel_params.get('RELATED', 'START')) if rel_params is not None else 'START'
                    if isinstance(value, timedelta):
                        minutes_before = int(abs(value.total_seconds()) // 60)
                except Exception:
                    pass
            
            alarms.append({
                "uid": str(comp.get('uid')) if comp.get('uid') is not None else None,
                "x_wr_alarmuid": str(comp.get('X-WR-ALARMUID')) if comp.get('X-WR-ALARMUID') is not None else None,
                "minutes_before": minutes_before,
                "related": related,
                "action": str(comp.get('action')) if comp.get('action') is not None else None,
                "description": str(comp.get('description')) if comp.get('description') is not None else None
            })
        
        logger.info(f"✅ list_event_alarms found {len(alarms)} alarms")
        return {
            "success": True,
            "alarms": alarms,
            "count": len(alarms)
        }
        
    except Exception as e:
        logger.error(f"❌ list_event_alarms failed: {type(e).__name__}: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }




if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    host = "0.0.0.0"
    
    logger.info("🚀" + "="*77)
    logger.info(f"🚀 Starting iCloud CalDAV MCP Server")
    logger.info(f"🚀 Server URL: http://{host}:{port}")
    logger.info(f"🚀 MCP Endpoint: http://{host}:{port}/mcp")
    logger.info(f"🚀 Environment: {os.environ.get('ENVIRONMENT', 'development')}")
    logger.info(f"🚀 Logging level: {logger.level}")
    
    # Validate environment variables on startup
    try:
        test_result = caldav_client.test_connection()
        if test_result.get("success"):
            logger.info(f"✓ Environment variables configured for: {test_result.get('email')}")
            logger.info(f"✓ Successfully connected to iCloud CalDAV")
            logger.info(f"✓ Found {test_result.get('calendars_found')} calendar(s)")
        else:
            logger.warning(f"⚠ Warning: {test_result.get('error')}")
            logger.warning("  Server will start but tools may fail until credentials are fixed.")
    except Exception as e:
        logger.warning(f"⚠ Warning: Could not test connection: {e}")
        logger.warning("  Server will start but tools may fail until credentials are fixed.")
    
    logger.info("🚀" + "="*77)

    mcp.run(transport="http", host=host, port=port, stateless_http=True)
