import pytest
from backend.app.graph.workflow import weather_bot_graph
from backend.app.services.session import session_manager


@pytest.mark.asyncio
async def test_graph_flow_success_path():
    sid = "test-graph-success"
    session_manager.clear(sid)

    initial_state = {
        "session_id": sid,
        "user_query": "Is cycling safe in Bhopal today?",
        "intent": None,
        "location": None,
        "weather_facts": None,
        "advisory": None,
        "matched_sops": [],
        "selected_sop": None,
        "decision_trace": [],
        "error_type": None,
        "error_message": None,
        "final_response": None,
        "is_validated": False,
        "fallback_used": False,
    }

    result = await weather_bot_graph.ainvoke(initial_state)

    assert result["location"] is not None
    assert result["location"].name.lower() == "bhopal"
    assert result["weather_facts"] is not None
    assert result["final_response"] is not None
    assert len(result["final_response"]) > 0
    assert result["is_validated"] is True

    deterministic_decision_exists = (
        result.get("selected_sop") is not None or bool(result.get("decision_trace"))
    )
    assert deterministic_decision_exists or result.get("error_type") == "no_sop"


@pytest.mark.asyncio
async def test_graph_flow_unknown_location_branch():
    sid = "test-graph-unknown-loc"
    session_manager.clear(sid)

    initial_state = {
        "session_id": sid,
        "user_query": "Is cycling safe in AtlantisFakeCityX99 today?",
        "intent": None,
        "location": None,
        "weather_facts": None,
        "advisory": None,
        "matched_sops": [],
        "selected_sop": None,
        "decision_trace": [],
        "error_type": None,
        "error_message": None,
        "final_response": None,
        "is_validated": False,
        "fallback_used": False,
    }

    result = await weather_bot_graph.ainvoke(initial_state)

    assert result["error_type"] == "location_error"
    assert result["weather_facts"] is None
    assert "couldn't resolve the location" in result["final_response"].lower()


@pytest.mark.asyncio
async def test_graph_flow_no_sop_indoor_query_branch():
    sid = "test-graph-indoor"
    session_manager.clear(sid)

    initial_state = {
        "session_id": sid,
        "user_query": "Should I paint my bedroom today?",
        "intent": None,
        "location": None,
        "weather_facts": None,
        "advisory": None,
        "matched_sops": [],
        "selected_sop": None,
        "decision_trace": [],
        "error_type": None,
        "error_message": None,
        "final_response": None,
        "is_validated": False,
        "fallback_used": False,
    }

    result = await weather_bot_graph.ainvoke(initial_state)

    assert result["error_type"] == "no_sop"
    assert result["final_response"] == "I don't have a specific safety guideline for this activity and weather condition, so I can't give you a recommendation."


@pytest.mark.asyncio
async def test_graph_flow_session_follow_up():
    sid = "test-graph-followup"
    session_manager.clear(sid)

    # Turn 1: Establish Bhopal + Cycling
    state_turn1 = {
        "session_id": sid,
        "user_query": "Is cycling safe in Bhopal today?",
        "intent": None,
        "location": None,
        "weather_facts": None,
        "advisory": None,
        "matched_sops": [],
        "selected_sop": None,
        "decision_trace": [],
        "error_type": None,
        "error_message": None,
        "final_response": None,
        "is_validated": False,
        "fallback_used": False,
    }
    res1 = await weather_bot_graph.ainvoke(state_turn1)
    assert res1["location"].name.lower() == "bhopal"

    # Turn 2: Follow-up "What about this evening?" (no location or activity specified)
    state_turn2 = {
        "session_id": sid,
        "user_query": "What about this evening?",
        "intent": None,
        "location": None,
        "weather_facts": None,
        "advisory": None,
        "matched_sops": [],
        "selected_sop": None,
        "decision_trace": [],
        "error_type": None,
        "error_message": None,
        "final_response": None,
        "is_validated": False,
        "fallback_used": False,
    }
    res2 = await weather_bot_graph.ainvoke(state_turn2)

    # Inherited location from Turn 1
    assert res2["location"] is not None
    assert res2["location"].name.lower() == "bhopal"
    # Fresh weather facts were fetched
    assert res2["weather_facts"] is not None
    assert res2["final_response"] is not None
