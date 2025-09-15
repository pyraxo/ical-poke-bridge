#!/usr/bin/env python3
import os
from datetime import datetime, date, timezone, timedelta
from zoneinfo import ZoneInfo
from typing import List, Dict, Optional
from uuid import uuid4
from urllib.parse import urlparse, unquote

import caldav
from caldav import DAVClient
from caldav.elements import dav
from icalendar import Calendar as IcsCalendar, Event as IcsEvent, Alarm as IcsAlarm

from fastmcp import FastMCP

ICAL_SERVER_URL = "https://caldav.icloud.com"

mcp = FastMCP("iCloud CalDAV MCP Server")

# Environment variable configuration
ICLOUD_EMAIL = os.environ.get("ICLOUD_EMAIL")
ICLOUD_PASSWORD = os.environ.get("ICLOUD_PASSWORD")

def _get_env_credentials() -> tuple[str, str]:
    """Get iCloud credentials from environment variables."""
    if not ICLOUD_EMAIL or not ICLOUD_PASSWORD:
        raise ValueError(
            "iCloud credentials not found in environment variables. "
            "Please set ICLOUD_EMAIL and ICLOUD_PASSWORD environment variables."
        )
    return ICLOUD_EMAIL, ICLOUD_PASSWORD


def _connect(email: str, password: str) -> tuple[DAVClient, object]:
    """Create a CalDAV client and return (client, principal)."""
    client = DAVClient(url=ICAL_SERVER_URL, username=email, password=password)
    principal = client.principal()
    # Perform a lightweight call to ensure auth works
    _ = principal.calendars()  # may raise AuthorizationError if invalid
    return client, principal


def _calendar_display_name(cal: caldav.Calendar) -> str:
    """Best-effort retrieval of a calendar's display name."""
    try:
        if getattr(cal, "name", None):
            return cal.name  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        props = cal.get_properties([dav.DisplayName()])  # type: ignore[arg-type]
        if isinstance(props, dict):
            for key, val in props.items():
                key_tag = getattr(key, "tag", str(key))
                if isinstance(key_tag, str) and key_tag.endswith("}displayname"):
                    return str(val)
    except Exception:
        pass
    try:
        return str(cal.url)
    except Exception:
        return "Unnamed Calendar"


def _parse_iso_datetime(value: Optional[str], tz: Optional[str] = None) -> Optional[datetime]:
    if value is None or value == "":
        return None
    v = value.strip()
    try:
        # Date-only input (YYYY-MM-DD)
        if len(v) == 10 and v[4] == "-" and v[7] == "-":
            d = date.fromisoformat(v)
            if tz:
                return datetime(d.year, d.month, d.day, tzinfo=ZoneInfo(tz))
            else:
                return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
        
        # Replace trailing Z with +00:00 for fromisoformat compatibility
        if v.endswith("Z"):
            v = v[:-1] + "+00:00"
        
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            if tz:
                dt = dt.replace(tzinfo=ZoneInfo(tz))
            else:
                dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        raise ValueError(f"Invalid ISO datetime '{value}'. Use YYYY-MM-DD or RFC3339/ISO-8601 format.")


def _dt_to_iso(dt: Optional[object]) -> Optional[str]:
    if dt is None:
        return None
    # icalendar may give a date or datetime
    if isinstance(dt, date) and not isinstance(dt, datetime):
        return date(dt.year, dt.month, dt.day).isoformat()
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    # Fallback string
    return str(dt)


def _find_calendar(principal: object, *, calendar_url: Optional[str], calendar_name: Optional[str]) -> caldav.Calendar:
    calendars = principal.calendars()
    if calendar_url:
        for c in calendars:
            try:
                if str(c.url) == calendar_url:
                    return c
            except Exception:
                pass
        raise ValueError("Calendar with the provided URL was not found.")
    if calendar_name:
        name_lower = calendar_name.strip().lower()
        for c in calendars:
            if _calendar_display_name(c).strip().lower() == name_lower:
                return c
        raise ValueError("Calendar with the provided name was not found.")
    # Default to the first calendar if present
    if calendars:
        return calendars[0]
    raise ValueError("No calendars found for this account.")


def _uid_from_event_url(event_url: Optional[str]) -> Optional[str]:
    if not event_url:
        return None
    try:
        path = urlparse(event_url).path
        filename = path.rsplit('/', 1)[-1]
        if filename.lower().endswith('.ics'):
            base = filename[:-4]
        else:
            base = filename
        return unquote(base)
    except Exception:
        return None


def _get_event_by_url_or_uid(client: DAVClient, cal: caldav.Calendar, event_url: Optional[str], uid: Optional[str]) -> caldav.Event:
    # Prefer UID when available
    if uid:
        try:
            return cal.event_by_uid(uid)  # type: ignore[attr-defined]
        except Exception:
            pass
    # Derive UID from URL for iCloud (filename is UID)
    if event_url:
        uid_guess = _uid_from_event_url(event_url)
        if uid_guess:
            try:
                return cal.event_by_uid(uid_guess)  # type: ignore[attr-defined]
            except Exception:
                pass
        # Fallback: attempt constructing by absolute URL (may fail on some servers)
        try:
            return caldav.Event(client=client, url=event_url)
        except Exception:
            pass
    raise ValueError("Event not found by URL or UID.")

 



@mcp.tool(description="List your iCloud calendars using environment variables (ICLOUD_EMAIL, ICLOUD_PASSWORD).")
def list_my_calendars() -> List[Dict[str, str]]:
    """List calendars using credentials from environment variables."""
    email, password = _get_env_credentials()
    client, principal = _connect(email, password)
    calendars = principal.calendars()
    results: List[Dict[str, str]] = []
    for cal in calendars:
        results.append({
            "name": _calendar_display_name(cal),
            "url": str(getattr(cal, "url", ""))
        })
    return results


@mcp.tool(description=(
    "List events from your iCloud calendars using environment variables. "
    "If no calendar_name is specified, searches ALL calendars. "
    "Dates accept YYYY-MM-DD or full ISO-8601; defaults to past 7 days through next 30 days. "
    "Optional timezone_name parameter for date filtering (defaults to UTC if not provided)."
))
def list_my_events(
    start: Optional[str] = None,
    end: Optional[str] = None,
    calendar_name: Optional[str] = None,
    timezone_name: Optional[str] = None,
    limit: Optional[int] = None
) -> List[Dict[str, Optional[str]]]:
    """List events using credentials from environment variables."""
    email, password = _get_env_credentials()
    
    if calendar_name:
        # Search specific calendar
        client, principal = _connect(email, password)
        start_dt = _parse_iso_datetime(start, timezone_name) or (datetime.now(timezone.utc) - timedelta(days=7))
        end_dt = _parse_iso_datetime(end, timezone_name) or (datetime.now(timezone.utc) + timedelta(days=30))
        cal = _find_calendar(principal, calendar_url=None, calendar_name=calendar_name)
        events = cal.date_search(start_dt, end_dt)
        results: List[Dict[str, Optional[str]]] = []
        for ev in events:
            try:
                ics = ev.data
                cal_ics = IcsCalendar.from_ical(ics)
                summary = None
                dtstart_val = None
                dtend_val = None
                uid_val = None
                for comp in cal_ics.walk('vevent'):
                    if comp.get('summary') is not None and summary is None:
                        summary = str(comp.get('summary'))
                    if comp.get('uid') is not None and uid_val is None:
                        uid_val = str(comp.get('uid'))
                    if comp.get('dtstart') is not None and dtstart_val is None:
                        dtstart_val = comp.get('dtstart').dt
                    if comp.get('dtend') is not None and dtend_val is None:
                        dtend_val = comp.get('dtend').dt
                results.append({
                    "calendar_name": calendar_name,
                    "url": str(getattr(ev, "url", "")),
                    "uid": uid_val,
                    "summary": summary,
                    "start": _dt_to_iso(dtstart_val),
                    "end": _dt_to_iso(dtend_val)
                })
            except Exception:
                # If parsing fails, still return the URL at least
                results.append({
                    "calendar_name": calendar_name,
                    "url": str(getattr(ev, "url", "")),
                    "uid": None,
                    "summary": None,
                    "start": None,
                    "end": None
                })
        # sort by start
        results.sort(key=lambda e: (e.get("start") or "", e.get("summary") or ""))
        if limit is not None:
            results = results[:max(0, int(limit))]
        return results
    else:
        # Search all calendars
        client, principal = _connect(email, password)
        calendars = principal.calendars()
        
        start_dt = _parse_iso_datetime(start, timezone_name) or (datetime.now(timezone.utc) - timedelta(days=7))
        end_dt = _parse_iso_datetime(end, timezone_name) or (datetime.now(timezone.utc) + timedelta(days=30))
        
        all_events: List[Dict[str, Optional[str]]] = []
        
        for cal in calendars:
            cal_name = _calendar_display_name(cal)
            try:
                events = cal.date_search(start_dt, end_dt)
                for ev in events:
                    try:
                        ics = ev.data
                        cal_ics = IcsCalendar.from_ical(ics)
                        summary = None
                        dtstart_val = None
                        dtend_val = None
                        uid_val = None
                        for comp in cal_ics.walk('vevent'):
                            if comp.get('summary') is not None and summary is None:
                                summary = str(comp.get('summary'))
                            if comp.get('uid') is not None and uid_val is None:
                                uid_val = str(comp.get('uid'))
                            if comp.get('dtstart') is not None and dtstart_val is None:
                                dtstart_val = comp.get('dtstart').dt
                            if comp.get('dtend') is not None and dtend_val is None:
                                dtend_val = comp.get('dtend').dt
                        all_events.append({
                            "calendar_name": cal_name,
                            "url": str(getattr(ev, "url", "")),
                            "uid": uid_val,
                            "summary": summary,
                            "start": _dt_to_iso(dtstart_val),
                            "end": _dt_to_iso(dtend_val)
                        })
                    except Exception:
                        # If parsing fails, still return the URL at least
                        all_events.append({
                            "calendar_name": cal_name,
                            "url": str(getattr(ev, "url", "")),
                            "uid": None,
                            "summary": None,
                            "start": None,
                            "end": None
                        })
            except Exception:
                # Skip calendars that can't be searched
                continue
        
        # sort by start
        all_events.sort(key=lambda e: (e.get("start") or "", e.get("summary") or ""))
        if limit is not None:
            all_events = all_events[:max(0, int(limit))]
        return all_events


@mcp.tool(description=(
    "Create an event in your iCloud calendar using environment variables. "
    "Provide ISO datetimes or YYYY-MM-DD for all-day. "
    "If no calendar_name is provided, uses the first calendar. "
    "Supports recurrence rules (RRULE) and alarms (alarm_minutes_before). "
    "Optional timezone_name parameter for event times (defaults to UTC if not provided)."
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
    alarm_minutes_before: Optional[int] = None
) -> Dict[str, str]:
    """Create an event using credentials from environment variables."""
    email, password = _get_env_credentials()
    client, principal = _connect(email, password)
    cal = _find_calendar(principal, calendar_url=None, calendar_name=calendar_name)

    # Determine datetime or date semantics
    start_dt = _parse_iso_datetime(start, timezone_name)
    end_dt = _parse_iso_datetime(end, timezone_name)

    if all_day:
        if len(start.strip()) != 10 or len(end.strip()) != 10:
            raise ValueError("For all_day events, start and end must be YYYY-MM-DD.")
        start_date = date.fromisoformat(start.strip())
        end_date = date.fromisoformat(end.strip())
    else:
        if start_dt is None or end_dt is None:
            raise ValueError("Start and end must be valid ISO-8601 datetimes.")

    ics_cal = IcsCalendar()
    ics_cal.add('prodid', '-//iCloud CalDAV MCP//EN')
    ics_cal.add('version', '2.0')

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
        # Ensure timezone-aware datetime for icalendar
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)
        evt.add('dtstart', start_dt)
        evt.add('dtend', end_dt)

    if rrule:
        evt.add('rrule', rrule)

    # Add alarm if requested
    if alarm_minutes_before is not None and alarm_minutes_before >= 0:
        alarm = IcsAlarm()
        # Use property API to avoid type validator issues
        alarm.ACTION = 'DISPLAY'
        alarm.DESCRIPTION = 'Reminder'
        alarm.TRIGGER = timedelta(minutes=-int(alarm_minutes_before))
        alarm.TRIGGER_RELATED = 'START'
        # RFC 9074 UID on VALARM + Apple-compatible X-WR-ALARMUID
        alarm.uid = str(uuid4())
        alarm.add('X-WR-ALARMUID', alarm.uid, encode=False)
        evt.add_component(alarm)

    ics_cal.add_component(evt)
    # Ensure VTIMEZONE components exist for any TZIDs used
    try:
        ics_cal.add_missing_timezones()
    except Exception:
        pass
    ics_text = ics_cal.to_ical().decode('utf-8')

    try:
        created = cal.add_event(ics_text)
        # Try to extract URL if available
        event_url = None
        try:
            event_url = str(getattr(created, 'url', None)) if created is not None else None
        except Exception:
            event_url = None
        return {
            "status": "created",
            "event_url": event_url or ""
        }
    except Exception as e:
        raise RuntimeError(f"Failed to create event: {e}")


@mcp.tool(description="Delete an event by its CalDAV event URL using environment variables.")
def delete_my_event(event_url: str) -> Dict[str, str]:
    """Delete an event using credentials from environment variables."""
    email, password = _get_env_credentials()
    client, principal = _connect(email, password)
    try:
        ev = caldav.Event(client=client, url=event_url)
        ev.delete()
        return {"status": "deleted", "event_url": event_url}
    except Exception as e:
        raise RuntimeError(f"Failed to delete event: {e}")


@mcp.tool(description=(
    "Update an existing event by URL or UID. You can change summary, start/end, "
    "description, location, and add/change RRULE. When passing alarm_minutes_before, "
    "this tool MERGES by adding a new VALARM and preserves existing alarms; it does not "
    "replace or remove alarms. Use dedicated alarm tools to list/add/replace/remove alarms. "
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
) -> Dict[str, str]:
    email, password = _get_env_credentials()
    client, principal = _connect(email, password)
    cal = _find_calendar(principal, calendar_url=None, calendar_name=calendar_name)

    if not event_url and not uid:
        raise ValueError("Provide either event_url or uid to identify the event to update.")

    # Locate the event (prefer UID; derive UID from URL if needed)
    event_obj = _get_event_by_url_or_uid(client, cal, event_url, uid)

    # Get the original event data to extract key information
    original_ics = event_obj.data
    if isinstance(original_ics, bytes):
        original_ics = original_ics.decode('utf-8')
    
    # Parse the original event to get existing properties
    try:
        original_cal = IcsCalendar.from_ical(original_ics)
        original_event = None
        for comp in original_cal.walk('vevent'):
            original_event = comp
            break
    except Exception:
        # If parsing fails, create a new event with minimal info
        original_event = None
    
    # Create a new event with updated properties
    new_cal = IcsCalendar()
    new_cal.add('prodid', '-//iCloud CalDAV MCP//EN')
    new_cal.add('version', '2.0')
    
    new_event = IcsEvent()
    
    # Copy existing properties or use defaults
    if original_event:
        # Copy existing UID
        if original_event.get('uid'):
            new_event.add('uid', str(original_event.get('uid')))
        else:
            new_event.add('uid', f"{uuid4()}@icloud-caldav-mcp")
        
        # Copy existing DTSTAMP or create new one
        if original_event.get('dtstamp'):
            new_event.add('dtstamp', original_event.get('dtstamp').dt)
        else:
            new_event.add('dtstamp', datetime.now(timezone.utc))
        
        # Copy existing DTSTART/DTEND or use provided values
        if start is not None:
            new_start = _parse_iso_datetime(start, timezone_name)
            if new_start:
                new_event.add('dtstart', new_start)
        elif original_event.get('dtstart'):
            new_event.add('dtstart', original_event.get('dtstart').dt)
        
        if end is not None:
            new_end = _parse_iso_datetime(end, timezone_name)
            if new_end:
                new_event.add('dtend', new_end)
        elif original_event.get('dtend'):
            new_event.add('dtend', original_event.get('dtend').dt)
        
        # Copy existing RRULE or use provided value
        if rrule is not None:
            new_event.add('rrule', rrule)
        elif original_event.get('rrule'):
            new_event.add('rrule', str(original_event.get('rrule')))
        
        # Increment SEQUENCE (cast defensively)
        try:
            current_sequence_raw = original_event.get('sequence', 0)
            current_sequence = int(current_sequence_raw)
        except Exception:
            current_sequence = 0
        new_event.add('sequence', current_sequence + 1)
    else:
        # Create new event with defaults
        new_event.add('uid', f"{uuid4()}@icloud-caldav-mcp")
        new_event.add('dtstamp', datetime.now(timezone.utc))
        if start is not None:
            new_start = _parse_iso_datetime(start, timezone_name)
            if new_start:
                new_event.add('dtstart', new_start)
        if end is not None:
            new_end = _parse_iso_datetime(end, timezone_name)
            if new_end:
                new_event.add('dtend', new_end)
        if rrule is not None:
            new_event.add('rrule', rrule)
        new_event.add('sequence', 1)
    
    # Set updated properties
    if summary is not None:
        new_event.add('summary', summary)
    elif original_event and original_event.get('summary'):
        new_event.add('summary', str(original_event.get('summary')))
    
    if description is not None:
        new_event.add('description', description)
    elif original_event and original_event.get('description'):
        # Handle description field more carefully
        desc_value = original_event.get('description')
        if hasattr(desc_value, 'to_ical'):
            new_event.add('description', desc_value.to_ical().decode('utf-8'))
        else:
            new_event.add('description', str(desc_value))
    
    if location is not None:
        new_event.add('location', location)
    elif original_event and original_event.get('location'):
        # Handle location field more carefully
        loc_value = original_event.get('location')
        if hasattr(loc_value, 'to_ical'):
            new_event.add('location', loc_value.to_ical().decode('utf-8'))
        else:
            new_event.add('location', str(loc_value))
    
    # Alarms
    if alarm_minutes_before is not None and alarm_minutes_before >= 0:
        # Add a new alarm but DO NOT remove existing alarms
        alarm = IcsAlarm()
        alarm.ACTION = 'DISPLAY'
        alarm.DESCRIPTION = 'Reminder'
        alarm.TRIGGER = timedelta(minutes=-int(alarm_minutes_before))
        alarm.TRIGGER_RELATED = 'START'
        alarm.uid = str(uuid4())
        alarm.add('X-WR-ALARMUID', alarm.uid, encode=False)
        new_event.add_component(alarm)
        # Preserve any existing alarms as well
        if original_event is not None:
            for a in original_event.walk('valarm'):
                try:
                    cloned = IcsAlarm.from_ical(a.to_ical())
                    new_event.add_component(cloned)
                except Exception:
                    new_event.add_component(a)
    else:
        # No new alarm requested: preserve all existing alarms
        if original_event is not None:
            for a in original_event.walk('valarm'):
                try:
                    cloned = IcsAlarm.from_ical(a.to_ical())
                    new_event.add_component(cloned)
                except Exception:
                    new_event.add_component(a)
    
    new_cal.add_component(new_event)
    
    # Replace the event
    # Ensure VTIMEZONE presence similar to create flow
    try:
        new_cal.add_missing_timezones()
    except Exception:
        pass
    new_ics_text = new_cal.to_ical().decode('utf-8')
    event_obj.data = new_ics_text
    try:
        # Save the event by setting the data directly
        event_obj.data = new_ics_text
        # Try to save, but don't rely on the return value
        try:
            event_obj.save()
        except Exception as save_error:
            # If save fails, try alternative approach
            pass
        return {"status": "updated", "event_url": event_url or ""}
    except Exception as e:
        raise RuntimeError(f"Failed to update event: {e}")


@mcp.tool(description=(
    "List VALARMs for an event by URL or UID. Returns alarm UID, Apple X-WR-ALARMUID, "
    "trigger (normalized minutes_before when relative), RELATED, ACTION, and DESCRIPTION."
))
def list_event_alarms(
    event_url: Optional[str] = None,
    uid: Optional[str] = None,
    calendar_name: Optional[str] = None
) -> List[Dict[str, Optional[str]]]:
    email, password = _get_env_credentials()
    client, principal = _connect(email, password)
    cal = _find_calendar(principal, calendar_url=None, calendar_name=calendar_name)

    if not event_url and not uid:
        raise ValueError("Provide either event_url or uid to identify the event.")

    event_obj = _get_event_by_url_or_uid(client, cal, event_url, uid)

    ics_data = event_obj.data
    ics_bytes = ics_data if isinstance(ics_data, bytes) else str(ics_data).encode('utf-8')
    cal_ics = IcsCalendar.from_ical(ics_bytes)

    results: List[Dict[str, Optional[str]]] = []
    for comp in cal_ics.walk('valarm'):
        trigger_prop = comp.get('trigger')
        minutes_before: Optional[str] = None
        related: Optional[str] = None
        if trigger_prop is not None:
            try:
                # icalendar returns vDDDTypes; .dt may be timedelta or datetime
                value = getattr(trigger_prop, 'dt', trigger_prop)
                rel_params = getattr(trigger_prop, 'params', {})
                related = str(rel_params.get('RELATED', 'START')) if rel_params is not None else 'START'
                if isinstance(value, timedelta):
                    minutes_before = str(int(abs(value.total_seconds()) // 60))
                else:
                    minutes_before = None
            except Exception:
                minutes_before = None
        results.append({
            "uid": str(comp.get('uid')) if comp.get('uid') is not None else None,
            "x_wr_alarmuid": str(comp.get('X-WR-ALARMUID')) if comp.get('X-WR-ALARMUID') is not None else None,
            "minutes_before": minutes_before,
            "related": related,
            "action": str(comp.get('action')) if comp.get('action') is not None else None,
            "description": str(comp.get('description')) if comp.get('description') is not None else None
        })
    return results


@mcp.tool(description=(
    "Add a VALARM to an event by URL or UID. Idempotent when dedupe_by_trigger is true: "
    "if an alarm with the same minutes_before exists, no new alarm is added."
))
def add_event_alarm(
    event_url: Optional[str] = None,
    uid: Optional[str] = None,
    minutes_before: int = 15,
    calendar_name: Optional[str] = None,
    description: Optional[str] = 'Reminder',
    action: str = 'DISPLAY',
    related: str = 'START',
    dedupe_by_trigger: bool = True
) -> Dict[str, str]:
    email, password = _get_env_credentials()
    client, principal = _connect(email, password)
    cal = _find_calendar(principal, calendar_url=None, calendar_name=calendar_name)

    if not event_url and not uid:
        raise ValueError("Provide either event_url or uid to identify the event.")

    event_obj = _get_event_by_url_or_uid(client, cal, event_url, uid)

    original_ics = event_obj.data
    ics_bytes = original_ics if isinstance(original_ics, bytes) else str(original_ics).encode('utf-8')

    try:
        original_cal = IcsCalendar.from_ical(ics_bytes)
        original_event = None
        for comp in original_cal.walk('vevent'):
            original_event = comp
            break
    except Exception:
        original_event = None

    if original_event is None:
        raise ValueError("Unable to parse original event for alarm add.")

    # Check duplicates by trigger minutes if requested
    if dedupe_by_trigger:
        for a in original_event.walk('valarm'):
            trig = a.get('trigger')
            if trig is None:
                continue
            try:
                value = getattr(trig, 'dt', trig)
                if isinstance(value, timedelta):
                    existing_minutes = int(abs(value.total_seconds()) // 60)
                    if existing_minutes == int(minutes_before):
                        return {"status": "skipped", "reason": "duplicate_trigger", "event_url": event_url or ""}
            except Exception:
                pass

    new_cal = IcsCalendar()
    new_cal.add('prodid', '-//iCloud CalDAV MCP//EN')
    new_cal.add('version', '2.0')

    new_event = IcsEvent()

    # Copy core fields
    if original_event.get('uid'):
        new_event.add('uid', str(original_event.get('uid')))
    else:
        new_event.add('uid', f"{uuid4()}@icloud-caldav-mcp")

    if original_event.get('dtstamp'):
        new_event.add('dtstamp', original_event.get('dtstamp').dt)
    else:
        new_event.add('dtstamp', datetime.now(timezone.utc))

    if original_event.get('dtstart'):
        new_event.add('dtstart', original_event.get('dtstart').dt)
    if original_event.get('dtend'):
        new_event.add('dtend', original_event.get('dtend').dt)
    if original_event.get('rrule'):
        new_event.add('rrule', str(original_event.get('rrule')))
    if original_event.get('summary'):
        new_event.add('summary', str(original_event.get('summary')))
    if original_event.get('description'):
        desc_value = original_event.get('description')
        if hasattr(desc_value, 'to_ical'):
            new_event.add('description', desc_value.to_ical().decode('utf-8'))
        else:
            new_event.add('description', str(desc_value))
    if original_event.get('location'):
        loc_value = original_event.get('location')
        if hasattr(loc_value, 'to_ical'):
            new_event.add('location', loc_value.to_ical().decode('utf-8'))
        else:
            new_event.add('location', str(loc_value))

    # Increment sequence
    try:
        current_sequence_raw = original_event.get('sequence', 0)
        current_sequence = int(current_sequence_raw)
    except Exception:
        current_sequence = 0
    new_event.add('sequence', current_sequence + 1)

    # Preserve existing alarms
    for a in original_event.walk('valarm'):
        try:
            cloned = IcsAlarm.from_ical(a.to_ical())
            new_event.add_component(cloned)
        except Exception:
            new_event.add_component(a)

    # Add the new alarm
    alarm = IcsAlarm()
    alarm.ACTION = action or 'DISPLAY'
    if description:
        alarm.DESCRIPTION = description
    alarm.TRIGGER = timedelta(minutes=-int(minutes_before))
    alarm.TRIGGER_RELATED = related or 'START'
    alarm.uid = str(uuid4())
    alarm.add('X-WR-ALARMUID', alarm.uid, encode=False)
    new_event.add_component(alarm)

    new_cal.add_component(new_event)
    try:
        new_cal.add_missing_timezones()
    except Exception:
        pass
    new_ics_text = new_cal.to_ical().decode('utf-8')
    event_obj.data = new_ics_text
    try:
        event_obj.save()
    except Exception:
        pass
    return {"status": "added", "event_url": event_url or ""}


@mcp.tool(description=(
    "Replace a matching VALARM on an event. Match by minutes_before (default) or by alarm UID. "
    "Adds the new alarm, removes the matched one, preserves others."
))
def replace_event_alarm(
    event_url: Optional[str] = None,
    uid: Optional[str] = None,
    calendar_name: Optional[str] = None,
    match_by: str = 'minutes',
    minutes_before: Optional[int] = None,
    alarm_uid: Optional[str] = None,
    new_minutes_before: int = 15,
    description: Optional[str] = 'Reminder',
    action: str = 'DISPLAY',
    related: str = 'START'
) -> Dict[str, str]:
    email, password = _get_env_credentials()
    client, principal = _connect(email, password)
    cal = _find_calendar(principal, calendar_url=None, calendar_name=calendar_name)

    if not event_url and not uid:
        raise ValueError("Provide either event_url or uid to identify the event.")

    event_obj = _get_event_by_url_or_uid(client, cal, event_url, uid)

    original_ics = event_obj.data
    ics_bytes = original_ics if isinstance(original_ics, bytes) else str(original_ics).encode('utf-8')

    try:
        original_cal = IcsCalendar.from_ical(ics_bytes)
        original_event = None
        for comp in original_cal.walk('vevent'):
            original_event = comp
            break
    except Exception:
        original_event = None

    if original_event is None:
        raise ValueError("Unable to parse original event for alarm replacement.")

    # Build new event
    new_cal = IcsCalendar()
    new_cal.add('prodid', '-//iCloud CalDAV MCP//EN')
    new_cal.add('version', '2.0')
    new_event = IcsEvent()

    if original_event.get('uid'):
        new_event.add('uid', str(original_event.get('uid')))
    else:
        new_event.add('uid', f"{uuid4()}@icloud-caldav-mcp")

    if original_event.get('dtstamp'):
        new_event.add('dtstamp', original_event.get('dtstamp').dt)
    else:
        new_event.add('dtstamp', datetime.now(timezone.utc))
    if original_event.get('dtstart'):
        new_event.add('dtstart', original_event.get('dtstart').dt)
    if original_event.get('dtend'):
        new_event.add('dtend', original_event.get('dtend').dt)
    if original_event.get('rrule'):
        new_event.add('rrule', str(original_event.get('rrule')))
    if original_event.get('summary'):
        new_event.add('summary', str(original_event.get('summary')))
    if original_event.get('description'):
        desc_value = original_event.get('description')
        if hasattr(desc_value, 'to_ical'):
            new_event.add('description', desc_value.to_ical().decode('utf-8'))
        else:
            new_event.add('description', str(desc_value))
    if original_event.get('location'):
        loc_value = original_event.get('location')
        if hasattr(loc_value, 'to_ical'):
            new_event.add('location', loc_value.to_ical().decode('utf-8'))
        else:
            new_event.add('location', str(loc_value))

    try:
        current_sequence_raw = original_event.get('sequence', 0)
        current_sequence = int(current_sequence_raw)
    except Exception:
        current_sequence = 0
    new_event.add('sequence', current_sequence + 1)

    # Copy only alarms that do NOT match the selection criteria
    for a in original_event.walk('valarm'):
        keep = True
        if match_by == 'uid' and alarm_uid:
            if str(a.get('uid')) == alarm_uid or str(a.get('X-WR-ALARMUID')) == alarm_uid:
                keep = False
        elif match_by == 'minutes' and minutes_before is not None:
            trig = a.get('trigger')
            if trig is not None:
                try:
                    value = getattr(trig, 'dt', trig)
                    if isinstance(value, timedelta):
                        existing_minutes = int(abs(value.total_seconds()) // 60)
                        if existing_minutes == int(minutes_before):
                            keep = False
                except Exception:
                    pass
        if keep:
            try:
                cloned = IcsAlarm.from_ical(a.to_ical())
                new_event.add_component(cloned)
            except Exception:
                new_event.add_component(a)

    # Add the replacement alarm
    new_alarm = IcsAlarm()
    new_alarm.ACTION = action or 'DISPLAY'
    if description:
        new_alarm.DESCRIPTION = description
    new_alarm.TRIGGER = timedelta(minutes=-int(new_minutes_before))
    new_alarm.TRIGGER_RELATED = related or 'START'
    new_alarm.uid = str(uuid4())
    new_alarm.add('X-WR-ALARMUID', new_alarm.uid, encode=False)
    new_event.add_component(new_alarm)

    new_cal.add_component(new_event)
    try:
        new_cal.add_missing_timezones()
    except Exception:
        pass
    new_ics_text = new_cal.to_ical().decode('utf-8')
    event_obj.data = new_ics_text
    try:
        event_obj.save()
    except Exception:
        pass
    return {"status": "replaced", "event_url": event_url or ""}


@mcp.tool(description=(
    "Remove VALARM(s) from an event. Match by minutes_before, by alarm UID, or remove all."
))
def remove_event_alarm(
    event_url: Optional[str] = None,
    uid: Optional[str] = None,
    calendar_name: Optional[str] = None,
    match_by: str = 'minutes',
    minutes_before: Optional[int] = None,
    alarm_uid: Optional[str] = None
) -> Dict[str, str]:
    email, password = _get_env_credentials()
    client, principal = _connect(email, password)
    cal = _find_calendar(principal, calendar_url=None, calendar_name=calendar_name)

    if not event_url and not uid:
        raise ValueError("Provide either event_url or uid to identify the event.")

    event_obj = _get_event_by_url_or_uid(client, cal, event_url, uid)

    original_ics = event_obj.data
    ics_bytes = original_ics if isinstance(original_ics, bytes) else str(original_ics).encode('utf-8')

    try:
        original_cal = IcsCalendar.from_ical(ics_bytes)
        original_event = None
        for comp in original_cal.walk('vevent'):
            original_event = comp
            break
    except Exception:
        original_event = None

    if original_event is None:
        raise ValueError("Unable to parse original event for alarm removal.")

    new_cal = IcsCalendar()
    new_cal.add('prodid', '-//iCloud CalDAV MCP//EN')
    new_cal.add('version', '2.0')
    new_event = IcsEvent()

    if original_event.get('uid'):
        new_event.add('uid', str(original_event.get('uid')))
    else:
        new_event.add('uid', f"{uuid4()}@icloud-caldav-mcp")
    if original_event.get('dtstamp'):
        new_event.add('dtstamp', original_event.get('dtstamp').dt)
    else:
        new_event.add('dtstamp', datetime.now(timezone.utc))
    if original_event.get('dtstart'):
        new_event.add('dtstart', original_event.get('dtstart').dt)
    if original_event.get('dtend'):
        new_event.add('dtend', original_event.get('dtend').dt)
    if original_event.get('rrule'):
        new_event.add('rrule', str(original_event.get('rrule')))
    if original_event.get('summary'):
        new_event.add('summary', str(original_event.get('summary')))
    if original_event.get('description'):
        desc_value = original_event.get('description')
        if hasattr(desc_value, 'to_ical'):
            new_event.add('description', desc_value.to_ical().decode('utf-8'))
        else:
            new_event.add('description', str(desc_value))
    if original_event.get('location'):
        loc_value = original_event.get('location')
        if hasattr(loc_value, 'to_ical'):
            new_event.add('location', loc_value.to_ical().decode('utf-8'))
        else:
            new_event.add('location', str(loc_value))

    try:
        current_sequence_raw = original_event.get('sequence', 0)
        current_sequence = int(current_sequence_raw)
    except Exception:
        current_sequence = 0
    new_event.add('sequence', current_sequence + 1)

    removed_count = 0
    for a in original_event.walk('valarm'):
        remove = False
        if match_by == 'all':
            remove = True
        elif match_by == 'uid' and alarm_uid:
            if str(a.get('uid')) == alarm_uid or str(a.get('X-WR-ALARMUID')) == alarm_uid:
                remove = True
        elif match_by == 'minutes' and minutes_before is not None:
            trig = a.get('trigger')
            if trig is not None:
                try:
                    value = getattr(trig, 'dt', trig)
                    if isinstance(value, timedelta):
                        existing_minutes = int(abs(value.total_seconds()) // 60)
                        if existing_minutes == int(minutes_before):
                            remove = True
                except Exception:
                    pass
        if remove:
            removed_count += 1
            continue
        # keep it
        try:
            cloned = IcsAlarm.from_ical(a.to_ical())
            new_event.add_component(cloned)
        except Exception:
            new_event.add_component(a)

    new_cal.add_component(new_event)
    try:
        new_cal.add_missing_timezones()
    except Exception:
        pass
    new_ics_text = new_cal.to_ical().decode('utf-8')
    event_obj.data = new_ics_text
    try:
        event_obj.save()
    except Exception:
        pass
    return {"status": "removed", "removed": str(removed_count), "event_url": event_url or ""}
@mcp.tool(description="Check the connection status to iCloud CalDAV using environment variables.")
def get_connection_status() -> Dict[str, str]:
    """Test the iCloud CalDAV connection using environment variables."""
    try:
        email, password = _get_env_credentials()
        client, principal = _connect(email, password)
        calendars = principal.calendars()
        return {
            "status": "connected",
            "email": email,
            "calendars_found": str(len(calendars)),
            "server_url": ICAL_SERVER_URL
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "server_url": ICAL_SERVER_URL
        }


@mcp.tool(description="Greet a user by name with a welcome message from the MCP server")
def greet(name: str) -> str:
    return f"Hello, {name}! Welcome to the iCloud Poke CalDAV MCP server."


@mcp.tool(description="Get information about the MCP server including name, version, environment, and Python version")
def get_server_info() -> dict:
    return {
        "server_name": "iCloud CalDAV MCP Server",
        "version": "1.0.0",
        "environment": os.environ.get("ENVIRONMENT", "development"),
        "python_version": os.sys.version.split()[0]
    }


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    host = "0.0.0.0"
    
    print(f"Starting iCloud CalDAV MCP Server on {host}:{port}")
    
    # Validate environment variables on startup
    try:
        email, password = _get_env_credentials()
        print(f"✓ Environment variables configured for: {email}")
        
        # Test connection on startup
        try:
            client, principal = _connect(email, password)
            calendars = principal.calendars()
            print(f"✓ Successfully connected to iCloud CalDAV")
            print(f"✓ Found {len(calendars)} calendar(s)")
        except Exception as e:
            print(f"⚠ Warning: Could not connect to iCloud CalDAV: {e}")
            print("  Server will start but tools may fail until credentials are fixed.")
    except ValueError as e:
        print(f"⚠ Warning: {e}")
        print("  Server will start but simplified tools (list_my_*, create_my_*, etc.) will not work.")
        print("  You can still use the original tools with explicit email/password parameters.")
    
    mcp.run(
        transport="http",
        host=host,
        port=port,
        stateless_http=True
    )
