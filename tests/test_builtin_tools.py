import json

import pytest

from jarvis.tools import builtin


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(builtin, "DATA_DIR", tmp_path)
    monkeypatch.setattr(builtin, "NOTES_FILE", tmp_path / "notes.json")
    monkeypatch.setattr(builtin, "REMINDERS_FILE", tmp_path / "reminders.json")
    yield


def test_calculate_basic_arithmetic():
    assert builtin.calculate("2 + 3 * 4") == "14"


def test_calculate_rejects_non_arithmetic():
    with pytest.raises(ValueError):
        builtin.calculate("__import__('os').system('echo hi')")


def test_get_current_date_is_iso_format():
    date_str = builtin.get_current_date()
    assert len(date_str) == 10 and date_str.count("-") == 2


def test_notes_round_trip():
    assert builtin.list_notes() == "There are no saved notes."
    builtin.take_note("buy milk")
    builtin.take_note("call mom")
    listing = builtin.list_notes()
    assert "1. buy milk" in listing
    assert "2. call mom" in listing
    assert json.loads(builtin.NOTES_FILE.read_text()) == ["buy milk", "call mom"]


def test_reminders_round_trip():
    assert builtin.list_reminders() == "There are no saved reminders."
    builtin.set_reminder("dentist", "tomorrow at 9am")
    listing = builtin.list_reminders()
    assert "tomorrow at 9am: dentist" in listing


def test_get_weather_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENWEATHER_API_KEY", raising=False)
    result = builtin.get_weather("London")
    assert "openweather_api_key" in result.lower()
