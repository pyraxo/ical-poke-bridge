#!/usr/bin/env python3
"""
iCalendar Utilities Module
Handles iCalendar parsing, creation, and manipulation.
"""
import logging
from datetime import datetime, date, timezone, timedelta
from zoneinfo import ZoneInfo
from typing import List, Dict, Optional
from uuid import uuid4

import caldav
from icalendar import Calendar as IcsCalendar, Event as IcsEvent, Alarm as IcsAlarm

logger = logging.getLogger(__name__)


class ICalUtils:
    """Utilities for iCalendar operations."""
    
    @staticmethod
    def parse_iso_datetime(value: Optional[str], tz: Optional[str] = None) -> Optional[datetime]:
        """Parse ISO datetime string with optional timezone."""
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
    
    @staticmethod
    def dt_to_iso(dt: Optional[object]) -> Optional[str]:
        """Convert datetime/date object to ISO string."""
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
    
    @staticmethod
    def get_event_ics_bytes(event_obj: caldav.Event) -> bytes:
        """Fetch ICS data for an event reliably and return as bytes."""
        data = getattr(event_obj, 'data', None)
        if data is None or data == b'' or data == '':
            try:
                event_obj.load()  # ensure ICS is fetched
                data = getattr(event_obj, 'data', None)
            except Exception:
                pass
        if isinstance(data, str):
            if data.strip().lower() == 'none' or data.strip() == '':
                try:
                    event_obj.load()
                    data = getattr(event_obj, 'data', None)
                except Exception:
                    pass
        if isinstance(data, bytes):
            data_bytes = data
        elif isinstance(data, str):
            data_bytes = data.encode('utf-8', errors='ignore')
        else:
            data_bytes = str(data if data is not None else '').encode('utf-8', errors='ignore')
        # Best-effort sanity check; ICS should contain VCALENDAR header
        if b'BEGIN:VCALENDAR' not in data_bytes:
            try:
                event_obj.load()
                fresh = getattr(event_obj, 'data', None)
                if isinstance(fresh, bytes):
                    data_bytes = fresh
                elif isinstance(fresh, str):
                    data_bytes = fresh.encode('utf-8', errors='ignore')
            except Exception:
                pass
        return data_bytes
    
    @staticmethod
    def parse_event_from_ics(event_obj: caldav.Event) -> Dict[str, Optional[str]]:
        """Parse an event from CalDAV object to standardized dict format."""
        try:
            ics_bytes = ICalUtils.get_event_ics_bytes(event_obj)
            cal_ics = IcsCalendar.from_ical(ics_bytes)
            
            summary = None
            dtstart_val = None
            dtend_val = None
            uid_val = None
            description = None
            location = None
            
            for comp in cal_ics.walk('vevent'):
                if comp.get('summary') is not None and summary is None:
                    summary = str(comp.get('summary'))
                if comp.get('uid') is not None and uid_val is None:
                    uid_val = str(comp.get('uid'))
                if comp.get('dtstart') is not None and dtstart_val is None:
                    dtstart_val = comp.get('dtstart').dt
                if comp.get('dtend') is not None and dtend_val is None:
                    dtend_val = comp.get('dtend').dt
                if comp.get('description') is not None and description is None:
                    description = str(comp.get('description'))
                if comp.get('location') is not None and location is None:
                    location = str(comp.get('location'))
                    
            return {
                "url": str(getattr(event_obj, "url", "")),
                "uid": uid_val,
                "summary": summary,
                "description": description,
                "location": location,
                "start": ICalUtils.dt_to_iso(dtstart_val),
                "end": ICalUtils.dt_to_iso(dtend_val)
            }
        except Exception as e:
            logger.warning(f"Failed to parse event: {e}")
            # Return minimal info on parse failure
            return {
                "url": str(getattr(event_obj, "url", "")),
                "uid": None,
                "summary": None,
                "description": None,
                "location": None,
                "start": None,
                "end": None
            }
    
    @staticmethod
    def create_ics_calendar() -> IcsCalendar:
        """Create a new iCalendar object with standard headers."""
        ics_cal = IcsCalendar()
        ics_cal.add('prodid', '-//iCloud CalDAV MCP//EN')
        ics_cal.add('version', '2.0')
        return ics_cal
    
    @staticmethod
    def create_alarm(minutes_before: int, description: str = 'Reminder', action: str = 'DISPLAY', related: str = 'START') -> IcsAlarm:
        """Create a VALARM component using the exact same pattern that worked in server_old.py."""
        alarm = IcsAlarm()
        alarm.ACTION = action or 'DISPLAY'
        if description:
            alarm.DESCRIPTION = description
        alarm.TRIGGER = timedelta(minutes=-int(minutes_before))
        alarm.TRIGGER_RELATED = related or 'START'
        alarm.uid = str(uuid4())
        alarm.add('X-WR-ALARMUID', alarm.uid, encode=False)
        return alarm
    
    @staticmethod
    def copy_event_properties(original_event: IcsEvent, new_event: IcsEvent) -> None:
        """Copy standard properties from original event to new event."""
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
        
        # Copy dates
        if original_event.get('dtstart'):
            new_event.add('dtstart', original_event.get('dtstart').dt)
        if original_event.get('dtend'):
            new_event.add('dtend', original_event.get('dtend').dt)
            
        # Copy other properties
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
    
    @staticmethod
    def get_sequence_number(original_event: Optional[IcsEvent]) -> int:
        """Get and increment sequence number from original event."""
        if not original_event:
            return 1
        try:
            current_sequence_raw = original_event.get('sequence', 0)
            current_sequence = int(current_sequence_raw)
            return current_sequence + 1
        except Exception:
            return 1
