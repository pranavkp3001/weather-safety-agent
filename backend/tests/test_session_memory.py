import pytest
from backend.app.services.session import SessionManager
from backend.app.services.geocoding import LocationInfo


def test_session_creation_and_isolation():
    manager = SessionManager()
    s1 = manager.get_or_create("session-1")
    s2 = manager.get_or_create("session-2")

    assert s1.session_id == "session-1"
    assert s2.session_id == "session-2"
    assert s1 is not s2

    loc = LocationInfo(name="Bhopal", latitude=23.25, longitude=77.41)
    manager.update_context("session-1", location=loc, activity="cycling")

    # Session 1 has location & activity
    assert manager.get("session-1").location.name == "Bhopal"
    assert manager.get("session-1").activity == "cycling"

    # Session 2 remains empty
    assert manager.get("session-2").location is None
    assert manager.get("session-2").activity is None


def test_session_follow_up_context():
    manager = SessionManager()
    sid = "user-123"

    # Turn 1: "Is cycling safe in Bhopal today?"
    loc = LocationInfo(name="Bhopal", latitude=23.25, longitude=77.41)
    manager.update_context(sid, location=loc, activity="cycling", time_reference="today")

    ctx1 = manager.get(sid)
    assert ctx1.location.name == "Bhopal"
    assert ctx1.activity == "cycling"
    assert ctx1.time_reference == "today"

    # Turn 2: "What about this evening?" (activity and location omitted)
    manager.update_context(sid, time_reference="this evening")

    ctx2 = manager.get(sid)
    # Location and activity preserved from Turn 1
    assert ctx2.location.name == "Bhopal"
    assert ctx2.activity == "cycling"
    # Time reference updated to new turn
    assert ctx2.time_reference == "this evening"


def test_weather_facts_never_stored_in_session():
    manager = SessionManager()
    sid = "test-noweather"
    ctx = manager.get_or_create(sid)

    # Session model must not have weather_facts or cached weather fields
    assert not hasattr(ctx, "weather_facts")
    assert not hasattr(ctx, "weather")
    assert not hasattr(ctx, "temperature_2m")
