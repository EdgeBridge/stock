"""Tests for Korean macro event calendar."""

from data.kr_macro_calendar import KRMacroCalendarService, KR_ALL_EVENTS


class TestKRMacroCalendar:
    def test_events_loaded(self):
        # BOK 8 + CPI 12 + GDP 4 + Employment 12 = 36
        assert len(KR_ALL_EVENTS) == 36

    def test_events_sorted(self):
        dates = [e.date for e in KR_ALL_EVENTS]
        assert dates == sorted(dates)

    def test_event_types(self):
        types = {e.event_type for e in KR_ALL_EVENTS}
        assert types == {"BOK", "KR_CPI", "KR_GDP", "KR_JOBS"}

    def test_bok_count(self):
        bok = [e for e in KR_ALL_EVENTS if e.event_type == "BOK"]
        assert len(bok) == 8

    def test_is_event_day_bok(self):
        svc = KRMacroCalendarService()
        events = svc.is_event_day("2026-01-16")
        assert len(events) == 1
        assert events[0].event_type == "BOK"

    def test_is_event_day_none(self):
        svc = KRMacroCalendarService()
        events = svc.is_event_day("2026-06-15")
        assert events == []

    def test_sizing_multiplier_bok(self):
        svc = KRMacroCalendarService()
        assert svc.get_sizing_multiplier("2026-01-16") == 0.0

    def test_sizing_multiplier_cpi(self):
        svc = KRMacroCalendarService()
        assert svc.get_sizing_multiplier("2026-01-07") == 0.5

    def test_sizing_multiplier_normal(self):
        svc = KRMacroCalendarService()
        assert svc.get_sizing_multiplier("2026-06-15") == 1.0

    def test_should_block_buys_bok(self):
        svc = KRMacroCalendarService()
        blocked, reason = svc.should_block_buys("2026-02-27")
        assert blocked is True
        assert "BOK" in reason

    def test_should_block_buys_cpi(self):
        svc = KRMacroCalendarService()
        blocked, _ = svc.should_block_buys("2026-01-07")
        assert blocked is False

    def test_to_dict(self):
        svc = KRMacroCalendarService()
        result = svc.to_dict()
        assert isinstance(result, list)
        for item in result:
            assert "date" in item
            assert "event_type" in item
            assert "description" in item
