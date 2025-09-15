#!/usr/bin/env python3
import os
from datetime import datetime, date, timezone, timedelta
from typing import List, Dict, Optional
from uuid import uuid4

import caldav
from caldav import DAVClient
from caldav.elements import dav
from icalendar import Calendar as IcsCalendar, Event as IcsEvent

from fastmcp import FastMCP

ICAL_SERVER_URL = "https://caldav.icloud.com"

mcp = FastMCP("iCloud CalDAV MCP Server")


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


def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if value is None or value == "":
        return None
    v = value.strip()
    try:
        # Date-only input (YYYY-MM-DD)
        if len(v) == 10 and v[4] == "-" and v[7] == "-":
            d = date.fromisoformat(v)
            return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
        # Replace trailing Z with +00:00 for fromisoformat compatibility
        if v.endswith("Z"):
            v = v[:-1] + "+00:00"
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        raise ValueError("Invalid ISO datetime. Use YYYY-MM-DD or RFC3339/ISO-8601.")


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


@mcp.tool(description="List the user's iCloud calendars. Provide email and password.")
def list_calendars(email: str, password: str) -> List[Dict[str, str]]:
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
    "List events in a calendar between start and end (ISO). "
    "Specify either calendar_url or calendar_name; if neither is provided, the first calendar is used. "
    "Dates accept YYYY-MM-DD or full ISO-8601; defaults to past 7 days through next 30 days."
))
def list_events(
    email: str,
    password: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    calendar_url: Optional[str] = None,
    calendar_name: Optional[str] = None
) -> List[Dict[str, Optional[str]]]:
    client, principal = _connect(email, password)
    cal = _find_calendar(principal, calendar_url=calendar_url, calendar_name=calendar_name)

    start_dt = _parse_iso_datetime(start) or (datetime.now(timezone.utc) - timedelta(days=7))
    end_dt = _parse_iso_datetime(end) or (datetime.now(timezone.utc) + timedelta(days=30))

    events = cal.date_search(start_dt, end_dt)
    results: List[Dict[str, Optional[str]]] = []
    for ev in events:
        try:
            ics = ev.data  # fetch ICS
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
                "url": str(getattr(ev, "url", "")),
                "uid": uid_val,
                "summary": summary,
                "start": _dt_to_iso(dtstart_val),
                "end": _dt_to_iso(dtend_val)
            })
        except Exception:
            # If parsing fails, still return the URL at least
            results.append({
                "url": str(getattr(ev, "url", "")),
                "uid": None,
                "summary": None,
                "start": None,
                "end": None
            })
    return results


@mcp.tool(description=(
    "Create an event in the specified calendar. Provide ISO datetimes or YYYY-MM-DD for all-day. "
    "Specify either calendar_url or calendar_name; if neither is provided, the first calendar is used."
))
def create_event(
    email: str,
    password: str,
    summary: str,
    start: str,
    end: str,
    calendar_url: Optional[str] = None,
    calendar_name: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
    all_day: bool = False
) -> Dict[str, str]:
    client, principal = _connect(email, password)
    cal = _find_calendar(principal, calendar_url=calendar_url, calendar_name=calendar_name)

    # Determine datetime or date semantics
    start_dt = _parse_iso_datetime(start)
    end_dt = _parse_iso_datetime(end)

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
        evt.add('dtstart', start_dt)
        evt.add('dtend', end_dt)

    ics_cal.add_component(evt)
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


@mcp.tool(description="Delete an event by its CalDAV event URL.")
def delete_event(email: str, password: str, event_url: str) -> Dict[str, str]:
    client, principal = _connect(email, password)
    try:
        ev = caldav.Event(client=client, url=event_url)
        ev.delete()
        return {"status": "deleted", "event_url": event_url}
    except Exception as e:
        raise RuntimeError(f"Failed to delete event: {e}")


@mcp.tool(description="Greet a user by name with a welcome message from the MCP server")
def greet(name: str) -> str:
    return f"Hello, {name}! Welcome to the iCloud CalDAV MCP server."


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

    print(f"Starting FastMCP server on {host}:{port}")

    mcp.run(
        transport="http",
        host=host,
        port=port,
        stateless_http=True
    )
