"""Korean macro event calendar — BOK rate decisions, CPI, GDP, employment.

Hardcoded 2026 calendar. No API calls needed.
Used by KR evaluation loop to reduce sizing on high-volatility event days.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from data.macro_calendar import MacroEvent


# 2026 Bank of Korea Monetary Policy Board meetings (금융통화위원회)
# BOK typically meets 8 times/year, decisions at 11:00 KST
_BOK_2026 = [
    ("2026-01-16", "BOK Rate Decision (Jan)"),
    ("2026-02-27", "BOK Rate Decision (Feb)"),
    ("2026-04-10", "BOK Rate Decision (Apr)"),
    ("2026-05-29", "BOK Rate Decision (May)"),
    ("2026-07-10", "BOK Rate Decision (Jul)"),
    ("2026-08-28", "BOK Rate Decision (Aug)"),
    ("2026-10-16", "BOK Rate Decision (Oct)"),
    ("2026-11-27", "BOK Rate Decision (Nov)"),
]

# 2026 Korean CPI release dates (통계청, typically 1st week of month)
_KR_CPI_2026 = [
    ("2026-01-07", "KR CPI (Dec 2025)"),
    ("2026-02-04", "KR CPI (Jan 2026)"),
    ("2026-03-04", "KR CPI (Feb 2026)"),
    ("2026-04-01", "KR CPI (Mar 2026)"),
    ("2026-05-06", "KR CPI (Apr 2026)"),
    ("2026-06-03", "KR CPI (May 2026)"),
    ("2026-07-01", "KR CPI (Jun 2026)"),
    ("2026-08-05", "KR CPI (Jul 2026)"),
    ("2026-09-02", "KR CPI (Aug 2026)"),
    ("2026-10-07", "KR CPI (Sep 2026)"),
    ("2026-11-04", "KR CPI (Oct 2026)"),
    ("2026-12-02", "KR CPI (Nov 2026)"),
]

# 2026 Korean GDP release dates (한국은행, quarterly advance estimate)
_KR_GDP_2026 = [
    ("2026-01-22", "KR GDP Q4 2025 (Advance)"),
    ("2026-04-23", "KR GDP Q1 2026 (Advance)"),
    ("2026-07-23", "KR GDP Q2 2026 (Advance)"),
    ("2026-10-22", "KR GDP Q3 2026 (Advance)"),
]

# 2026 Korean Employment data (통계청, typically mid-month)
_KR_EMPLOYMENT_2026 = [
    ("2026-01-14", "KR Employment (Dec 2025)"),
    ("2026-02-12", "KR Employment (Jan 2026)"),
    ("2026-03-11", "KR Employment (Feb 2026)"),
    ("2026-04-15", "KR Employment (Mar 2026)"),
    ("2026-05-13", "KR Employment (Apr 2026)"),
    ("2026-06-10", "KR Employment (May 2026)"),
    ("2026-07-15", "KR Employment (Jun 2026)"),
    ("2026-08-12", "KR Employment (Jul 2026)"),
    ("2026-09-16", "KR Employment (Aug 2026)"),
    ("2026-10-14", "KR Employment (Sep 2026)"),
    ("2026-11-12", "KR Employment (Oct 2026)"),
    ("2026-12-10", "KR Employment (Nov 2026)"),
]


def _build_kr_events() -> list[MacroEvent]:
    events = []
    for d, desc in _BOK_2026:
        events.append(MacroEvent(date=d, event_type="BOK", description=desc))
    for d, desc in _KR_CPI_2026:
        events.append(MacroEvent(date=d, event_type="KR_CPI", description=desc))
    for d, desc in _KR_GDP_2026:
        events.append(MacroEvent(date=d, event_type="KR_GDP", description=desc))
    for d, desc in _KR_EMPLOYMENT_2026:
        events.append(MacroEvent(date=d, event_type="KR_JOBS", description=desc))
    events.sort(key=lambda e: e.date)
    return events


KR_ALL_EVENTS = _build_kr_events()


class KRMacroCalendarService:
    """Hardcoded Korean macro event calendar for KR trading logic."""

    # Sizing multipliers per event type
    bok_sizing_mult: float = 0.0   # block new buys on BOK rate decision
    kr_cpi_sizing_mult: float = 0.5
    kr_gdp_sizing_mult: float = 0.5
    kr_jobs_sizing_mult: float = 0.7

    def is_event_day(self, target: str | None = None) -> list[MacroEvent]:
        d = target or date.today().isoformat()
        return [e for e in KR_ALL_EVENTS if e.date == d]

    def get_sizing_multiplier(self, target: str | None = None) -> float:
        events = self.is_event_day(target)
        if not events:
            return 1.0
        mult = 1.0
        for e in events:
            if e.event_type == "BOK":
                mult = min(mult, self.bok_sizing_mult)
            elif e.event_type == "KR_CPI":
                mult = min(mult, self.kr_cpi_sizing_mult)
            elif e.event_type == "KR_GDP":
                mult = min(mult, self.kr_gdp_sizing_mult)
            elif e.event_type == "KR_JOBS":
                mult = min(mult, self.kr_jobs_sizing_mult)
        return mult

    def should_block_buys(self, target: str | None = None) -> tuple[bool, str]:
        events = self.is_event_day(target)
        for e in events:
            if e.event_type == "BOK":
                return True, e.description
        return False, ""

    def get_upcoming(self, days_ahead: int = 7) -> list[MacroEvent]:
        today = date.today()
        end = today + timedelta(days=days_ahead)
        return [
            e for e in KR_ALL_EVENTS
            if today.isoformat() <= e.date <= end.isoformat()
        ]

    def to_dict(self) -> list[dict]:
        upcoming = self.get_upcoming(days_ahead=14)
        return [
            {"date": e.date, "event_type": e.event_type, "description": e.description}
            for e in upcoming
        ]
