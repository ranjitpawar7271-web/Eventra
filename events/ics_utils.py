"""'Export to Google Calendar' (Module 10): a standard .ics file plus a
direct Google Calendar 'add event' URL. No Google API/OAuth dependency —
Google Calendar (and Outlook, Apple Calendar, etc.) all accept a plain
RFC 5545 .ics file, and Google separately accepts a pre-filled URL with
no auth at all. Both are generated here with the standard library only,
matching the module plan's explicit note that no external dependency is
needed for a basic "add to calendar" link.
"""

import datetime
from urllib.parse import urlencode

from django.utils import timezone


def _escape_ics_text(value):
    """RFC 5545 §3.3.11: backslash, semicolon, comma, and newline are
    the only characters that need escaping in TEXT values."""
    return (
        value.replace('\\', '\\\\')
        .replace(';', '\\;')
        .replace(',', '\\,')
        .replace('\n', '\\n')
    )


def _to_utc_stamp(dt):
    """RFC 5545 floating/UTC DATE-TIME format: YYYYMMDDTHHMMSSZ."""
    return timezone.localtime(dt, datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def build_ics_bytes(event):
    """A minimal, valid single-VEVENT .ics file for one Event. Uses CRLF
    line endings per RFC 5545 §3.1 — several calendar clients reject
    files that only use \\n."""
    lines = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:-//Eventra//Event Export//EN',
        'CALSCALE:GREGORIAN',
        'BEGIN:VEVENT',
        f'UID:event-{event.id}@eventra',
        f'DTSTAMP:{_to_utc_stamp(timezone.now())}',
        f'DTSTART:{_to_utc_stamp(event.start_date)}',
        f'DTEND:{_to_utc_stamp(event.end_date)}',
        f'SUMMARY:{_escape_ics_text(event.title)}',
        f'DESCRIPTION:{_escape_ics_text(event.description)}',
        f'LOCATION:{_escape_ics_text(event.location)}',
        'END:VEVENT',
        'END:VCALENDAR',
    ]
    return ('\r\n'.join(lines) + '\r\n').encode('utf-8')


def build_google_calendar_url(event):
    """A direct 'add to Google Calendar' link — no API key, no OAuth,
    just a pre-filled URL Google's own calendar UI accepts."""
    dates = f"{_to_utc_stamp(event.start_date)}/{_to_utc_stamp(event.end_date)}"
    params = {
        'action': 'TEMPLATE',
        'text': event.title,
        'dates': dates,
        'details': event.description,
        'location': event.location,
    }
    return 'https://calendar.google.com/calendar/render?' + urlencode(params)
