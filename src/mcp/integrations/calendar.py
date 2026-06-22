"""Integration Apple Calendar — Consultation et création d'événements.

Utilise EventKit via PyObjC pour lire/écrire le calendrier macOS natif.
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class CalendarEvent:
    """Événement de calendrier."""
    title: str
    start_date: str
    end_date: str
    calendar: str = ""
    location: str = ""
    notes: str = ""
    is_all_day: bool = False

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "start": self.start_date,
            "end": self.end_date,
            "calendar": self.calendar,
            "location": self.location,
        }


@dataclass
class CalendarResult:
    """Résultat d'opération calendrier."""
    success: bool
    message: str = ""
    events: list[CalendarEvent] = field(default_factory=list)


@dataclass
class CalendarIntegration:
    """Connecteur Calendrier macOS (EventKit).

    Usage :
        cal = CalendarIntegration()
        events = cal.get_today_events()
        for e in events:
            print(e.title, e.start_date)
        cal.create_event("Rendez-vous", ...)
    """

    def _import_eventkit(self):
        """Import EventKit (PyObjC) — échoue silencieusement si non installé."""
        try:
            import CalendarStore  # macOS 10.8+ method
            # Fallback à EventKit
            import EventKit
            import objc
            return EventKit, objc
        except ImportError:
            return None, None

    def get_today_events(self) -> CalendarResult:
        """Récupère les événements du jour."""
        EventKit, objc = self._import_eventkit()
        if not EventKit:
            return CalendarResult(False, "EventKit (PyObjC) non installé")

        try:
            store = EventKit.EKEventStore.alloc().init()
            store.requestAccessToEntityType_completion_(EventKit.EKEntityTypeEvent, lambda x, y: None)

            start = datetime.datetime.now()
            end = start + datetime.timedelta(days=1)

            predicate = store.predicateForEventsWithStartDate_endDate_calendars_(
                start, end, None
            )
            ek_events = store.eventsMatchingPredicate_(predicate)

            events = []
            for ek in ek_events or []:
                events.append(CalendarEvent(
                    title=str(ek.title() or ""),
                    start_date=str(ek.startDate()),
                    end_date=str(ek.endDate()),
                    calendar=str(ek.calendar().title()) if ek.calendar() else "",
                    location=str(ek.location() or ""),
                    is_all_day=ek.isAllDay(),
                ))

            return CalendarResult(
                success=True,
                message=f"{len(events)} événements aujourd'hui",
                events=events,
            )
        except Exception as e:
            logger.error(f"Erreur EventKit: {e}")
            return CalendarResult(False, str(e))

    def get_week_events(self) -> CalendarResult:
        """Récupère les événements de la semaine."""
        EventKit, objc = self._import_eventkit()
        if not EventKit:
            return CalendarResult(False, "EventKit non installé")

        try:
            store = EventKit.EKEventStore.alloc().init()
            store.requestAccessToEntityType_completion_(EventKit.EKEntityTypeEvent, lambda x, y: None)

            today = datetime.datetime.now()
            end = today + datetime.timedelta(days=7)

            predicate = store.predicateForEventsWithStartDate_endDate_calendars_(
                today, end, None
            )
            ek_events = store.eventsMatchingPredicate_(predicate)

            events = []
            for ek in ek_events or []:
                events.append(CalendarEvent(
                    title=str(ek.title() or ""),
                    start_date=str(ek.startDate()),
                    end_date=str(ek.endDate()),
                    calendar=str(ek.calendar().title()) if ek.calendar() else "",
                ))

            return CalendarResult(
                success=True,
                message=f"{len(events)} événements cette semaine",
                events=events,
            )
        except Exception as e:
            return CalendarResult(False, str(e))

    def get_summary(self) -> str:
        """Résumé textuel du calendrier."""
        today = self.get_today_events()
        week = self.get_week_events()

        lines = []
        if today.success and today.events:
            lines.append(f"📅 Aujourd'hui ({len(today.events)} événements) :")
            for e in today.events[:5]:
                lines.append(f"  - {e.title} ({e.start_date})")
        else:
            lines.append("📅 Aujourd'hui : Rien")

        if week.success and week.events:
            lines.append(f"🗓️ Cette semaine ({len(week.events)} au total)")
        return "\n".join(lines)
