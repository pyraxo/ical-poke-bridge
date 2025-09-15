#!/usr/bin/env python3
"""
CalDAV Client Module
Handles all CalDAV operations for iCloud calendar integration.
"""
import os
import logging
from datetime import datetime, date, timezone, timedelta
from zoneinfo import ZoneInfo
from typing import List, Dict, Optional, Tuple
from urllib.parse import urlparse, unquote

import caldav
from caldav import DAVClient
from caldav.elements import dav

logger = logging.getLogger(__name__)

ICAL_SERVER_URL = "https://caldav.icloud.com"


class CalDAVClient:
    """CalDAV client for iCloud calendar operations."""
    
    def __init__(self):
        self.email = None
        self.password = None
        self.client = None
        self.principal = None
        
    def _get_credentials(self) -> Tuple[str, str]:
        """Get iCloud credentials from environment variables."""
        email = os.environ.get("ICLOUD_EMAIL")
        password = os.environ.get("ICLOUD_PASSWORD")
        
        if not email or not password:
            raise ValueError(
                "iCloud credentials not found in environment variables. "
                "Please set ICLOUD_EMAIL and ICLOUD_PASSWORD environment variables."
            )
        return email, password
    
    def connect(self) -> bool:
        """Establish connection to iCloud CalDAV server."""
        try:
            self.email, self.password = self._get_credentials()
            self.client = DAVClient(url=ICAL_SERVER_URL, username=self.email, password=self.password)
            self.principal = self.client.principal()
            # Test connection
            _ = self.principal.calendars()
            logger.info(f"✓ Successfully connected to iCloud CalDAV for {self.email}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to connect to iCloud CalDAV: {e}")
            return False
    
    def get_calendars(self) -> List[Dict[str, str]]:
        """Get list of all calendars."""
        if not self.principal:
            raise ValueError("Not connected to CalDAV server")
            
        try:
            calendars = self.principal.calendars()
            results = []
            for cal in calendars:
                results.append({
                    "name": self._get_calendar_display_name(cal),
                    "url": str(getattr(cal, "url", ""))
                })
            return results
        except Exception as e:
            logger.error(f"❌ Failed to get calendars: {e}")
            raise
    
    def _get_calendar_display_name(self, cal: caldav.Calendar) -> str:
        """Best-effort retrieval of a calendar's display name."""
        try:
            if getattr(cal, "name", None):
                return cal.name
        except Exception:
            pass
        try:
            props = cal.get_properties([dav.DisplayName()])
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
    
    def find_calendar(self, calendar_url: Optional[str] = None, calendar_name: Optional[str] = None) -> caldav.Calendar:
        """Find a calendar by URL or name."""
        if not self.principal:
            raise ValueError("Not connected to CalDAV server")
            
        calendars = self.principal.calendars()
        
        if calendar_url:
            for cal in calendars:
                try:
                    if str(cal.url) == calendar_url:
                        return cal
                except Exception:
                    pass
            raise ValueError("Calendar with the provided URL was not found.")
            
        if calendar_name:
            name_lower = calendar_name.strip().lower()
            for cal in calendars:
                if self._get_calendar_display_name(cal).strip().lower() == name_lower:
                    return cal
            raise ValueError("Calendar with the provided name was not found.")
            
        # Default to the first calendar if present
        if calendars:
            return calendars[0]
        raise ValueError("No calendars found for this account.")
    
    def get_event_by_url_or_uid(self, cal: caldav.Calendar, event_url: Optional[str] = None, uid: Optional[str] = None) -> caldav.Event:
        """Get an event by URL or UID."""
        # Prefer UID when available
        if uid:
            try:
                return cal.event_by_uid(uid)
            except Exception:
                pass
                
        # Derive UID from URL for iCloud (filename is UID)
        if event_url:
            uid_guess = self._uid_from_event_url(event_url)
            if uid_guess:
                try:
                    return cal.event_by_uid(uid_guess)
                except Exception:
                    pass
            # Fallback: attempt constructing by absolute URL
            try:
                return caldav.Event(client=self.client, url=event_url)
            except Exception:
                pass
                
        raise ValueError("Event not found by URL or UID.")
    
    def _uid_from_event_url(self, event_url: Optional[str]) -> Optional[str]:
        """Extract UID from iCloud event URL."""
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
    
    def test_connection(self) -> Dict[str, str]:
        """Test the CalDAV connection."""
        try:
            if not self.connect():
                return {
                    "success": False,
                    "error": "Failed to establish connection"
                }
                
            calendars = self.get_calendars()
            return {
                "success": True,
                "email": self.email,
                "calendars_found": len(calendars),
                "server_url": ICAL_SERVER_URL
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
