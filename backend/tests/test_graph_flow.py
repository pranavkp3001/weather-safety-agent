import pytest
from backend.app.graph.workflow import weather_bot_graph
from backend.app.main import ChatRequest, chat
from backend.app.llm.client import MockLLMClient
from backend.app.policies.models import SOPMatch
from backend.app.services.session import session_manager
from backend.app.services.weather import WeatherFacts


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
    assert "No specific policy applies" in result["final_response"]
    assert "WeatherBuddy doesn't currently have a safety policy" in result["final_response"]


@pytest.mark.asyncio
async def test_chat_structured_sop_output_and_clean_user_response():
    sid = "test-chat-structured-sop"
    session_manager.clear(sid)

    response = await chat(ChatRequest(message="Can I go walking in Delhi today?", session_id=sid))

    assert response.sop_id == "SOP-WALK-001"
    assert response.severity == "moderate"
    assert "SOP-WALK-001" not in response.response
    assert "moderate" not in response.response.lower()
    assert "30" in response.response or "walking" in response.response.lower()
    assert "\u00b0C" in response.response or "C" in response.response


@pytest.mark.asyncio
async def test_chat_evening_follow_up_uses_time_scope_without_internal_metadata():
    sid = "test-chat-evening-followup"
    session_manager.clear(sid)

    await chat(ChatRequest(message="Can I go walking in Delhi today?", session_id=sid))
    response = await chat(ChatRequest(message="What about this evening?", session_id=sid))

    assert "evening" in response.response.lower()
    assert "SOP-WALK-001" not in response.response
    assert "moderate" not in response.response.lower()
    assert response.sop_id == "SOP-WALK-001"
    assert response.severity == "moderate"
    assert "policy range" not in response.response.lower()
    assert "same guideline" not in response.response.lower()
    assert "this evening" in response.response.lower()
    assert "cooler" in response.response.lower() or "later" in response.response.lower()


@pytest.mark.asyncio
async def test_chat_response_excludes_internal_policy_metadata_and_language():
    sid = "test-chat-no-policy-metadata"
    session_manager.clear(sid)

    response = await chat(ChatRequest(message="Can I go walking in Delhi today?", session_id=sid))

    lower = response.response.lower()
    assert response.sop_id == "SOP-WALK-001"
    assert response.severity == "moderate"
    assert "based on:" not in lower
    assert "sop-" not in lower
    assert "moderate" not in lower
    assert "severe" not in lower
    assert "severity" not in lower
    assert "policy range" not in lower
    assert "same guideline" not in lower
    assert "decision trace" not in lower


@pytest.mark.asyncio
async def test_chat_night_follow_up_uses_requested_time_scope_without_daytime_phrase():
    sid = "test-chat-night-followup"
    session_manager.clear(sid)

    await chat(ChatRequest(message="Can I go walking in Delhi today?", session_id=sid))
    response = await chat(ChatRequest(message="What about this night?", session_id=sid))

    lower = response.response.lower()
    assert "night" in lower
    assert "hottest part of the day" not in lower
    assert response.sop_id == "SOP-WALK-001"
    assert response.severity == "moderate"
    assert "SOP-" not in response.response
    assert "moderate" not in response.response.lower()


@pytest.mark.asyncio
async def test_extract_intent_normalizes_child_park_and_picnic():
    client = __import__("backend.app.llm.client", fromlist=["MockLLMClient"]).MockLLMClient()

    park_intent = await client.extract_intent("Would it be okay to take my daughter to the park in London?")
    assert park_intent.activity == "park_visit"
    assert park_intent.category == "recreation"
    assert park_intent.user_group == "child"
    assert park_intent.location == "London"

    picnic_intent = await client.extract_intent("picnic in Queenstown today?")
    assert picnic_intent.activity == "picnic"
    assert picnic_intent.category in {"recreation", "home_and_leisure"}
    assert picnic_intent.user_group == "general"
    assert picnic_intent.location == "Queenstown"
    assert picnic_intent.time_reference == "today"


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


@pytest.mark.asyncio
async def test_response_uses_running_guidance_not_picnic_or_photography_writing():
    client = MockLLMClient()
    facts = WeatherFacts(
        location="Delhi",
        latitude=28.61,
        longitude=77.21,
        timestamp="2026-09-23T12:00:00",
        temperature_2m=31.5,
        wind_speed_10m=8.0,
        wind_gusts_10m=12.0,
        precipitation=0.0,
        precipitation_probability=5.0,
        uv_index=7.0,
        weather_code=1,
        weather_condition="clear",
        time_scope="today",
    )
    selected_sop = SOPMatch(
        sop_id="SOP-RUN-001",
        name="Running in Elevated Heat",
        category="Running",
        severity="severe",
        priority=110,
        guidance=(
            "Elevated heat conditions are a significant risk for running. MediBuddy SOP-RUN-001 recommends:\n"
            "1. Strongly consider postponing outdoor running\n"
            "2. If running, do so only during early morning or late evening\n"
            "3. Run slower and shorten the route"
        ),
        reasons=[],
        composite_score=None,
        is_exact_activity_match=True,
    )

    response = await client.compose_response("Can I go running in Delhi today?", facts, selected_sop)
    lower = response.lower()
    assert "running" in lower
    assert "postponing outdoor running" in lower or "early morning" in lower
    assert "picnic" not in lower
    assert "photograph" not in lower
    assert "keep the session steady" not in lower


@pytest.mark.asyncio
async def test_response_uses_child_park_guidance_for_park_visit():
    client = MockLLMClient()
    facts = WeatherFacts(
        location="London",
        latitude=51.5,
        longitude=-0.12,
        timestamp="2026-09-23T13:00:00",
        temperature_2m=26.0,
        wind_speed_10m=10.0,
        wind_gusts_10m=15.0,
        precipitation=0.0,
        precipitation_probability=10.0,
        uv_index=6.0,
        weather_code=1,
        weather_condition="clear",
        time_scope="today",
    )
    selected_sop = SOPMatch(
        sop_id="SOP-LEISURE-001",
        name="Park Visit in Warm Weather for Children",
        category="Leisure",
        severity="moderate",
        priority=80,
        guidance=(
            "Warm conditions are making a park visit less comfortable for children. MediBuddy SOP-LEISURE-001 recommends:\n"
            "1. Keep any park time short and stick to shaded areas\n"
            "2. Encourage frequent water breaks and a cool-down in shade\n"
            "3. Use hats, sunscreen, and lightweight clothing"
        ),
        reasons=[],
        composite_score=None,
        is_exact_activity_match=True,
    )

    response = await client.compose_response("Can my child go to the park in London today?", facts, selected_sop)
    lower = response.lower()
    assert "park" in lower or "children" in lower
    assert "shaded areas" in lower
    assert "water breaks" in lower or "cool-down" in lower
    assert "picnic" not in lower
    assert "photograph" not in lower


@pytest.mark.asyncio
async def test_response_uses_photography_guidance_if_sop_matches():
    client = MockLLMClient()
    facts = WeatherFacts(
        location="Pune",
        latitude=18.52,
        longitude=73.86,
        timestamp="2026-09-23T09:00:00",
        temperature_2m=27.0,
        wind_speed_10m=5.0,
        wind_gusts_10m=8.0,
        precipitation=0.0,
        precipitation_probability=0.0,
        uv_index=5.0,
        weather_code=1,
        weather_condition="clear",
        time_scope="today",
    )
    selected_sop = SOPMatch(
        sop_id="SOP-BASE-LEISURE-001",
        name="General Outdoor Leisure Baseline",
        category="Leisure",
        severity="low",
        priority=28,
        guidance=(
            "Current conditions fall within WeatherBuddy's normal outdoor-leisure guidance. This range is considered routine for a low-risk park, picnic, or outdoor leisure outing.\n"
            "1. Keep a comfortable pace and stay hydrated\n"
            "2. Use shade or a cooler window if the outing runs long\n"
            "3. Continue monitoring the forecast if conditions begin to worsen"
        ),
        reasons=[],
        composite_score=None,
        is_exact_activity_match=True,
    )

    response = await client.compose_response("Can I take photos outside in Pune today?", facts, selected_sop)
    lower = response.lower()
    assert "outdoor leisure" in lower or "keep a comfortable pace" in lower or "shade" in lower
    assert "running" not in lower
    assert "picnic" not in lower or "outdoor leisure" in lower


@pytest.mark.asyncio
async def test_response_uses_picnic_guidance_if_sop_matches():
    client = MockLLMClient()
    facts = WeatherFacts(
        location="Bhopal",
        latitude=23.25,
        longitude=77.42,
        timestamp="2026-09-23T15:00:00",
        temperature_2m=29.0,
        wind_speed_10m=7.0,
        wind_gusts_10m=10.0,
        precipitation=0.0,
        precipitation_probability=8.0,
        uv_index=5.0,
        weather_code=1,
        weather_condition="clear",
        time_scope="today",
    )
    selected_sop = SOPMatch(
        sop_id="SOP-BASE-LEISURE-001",
        name="General Outdoor Leisure Baseline",
        category="Leisure",
        severity="low",
        priority=28,
        guidance=(
            "Current conditions fall within WeatherBuddy's normal outdoor-leisure guidance. This range is considered routine for a low-risk park, picnic, or outdoor leisure outing.\n"
            "1. Keep a comfortable pace and stay hydrated\n"
            "2. Use shade or a cooler window if the outing runs long\n"
            "3. Continue monitoring the forecast if conditions begin to worsen"
        ),
        reasons=[],
        composite_score=None,
        is_exact_activity_match=True,
    )

    response = await client.compose_response("Can I have a picnic in Bhopal today?", facts, selected_sop)
    lower = response.lower()
    assert "picnic" in lower or "outdoor leisure" in lower
    assert "shade" in lower or "comfortable pace" in lower
    assert "running" not in lower
    assert "photography" not in lower


@pytest.mark.asyncio
async def test_multiple_guidance_sentences_are_punctuated_and_spaced():
    client = MockLLMClient()
    facts = WeatherFacts(
        location="Bhopal",
        latitude=23.25,
        longitude=77.42,
        timestamp="2026-09-23T15:00:00",
        temperature_2m=29.0,
        wind_speed_10m=7.0,
        wind_gusts_10m=10.0,
        precipitation=0.0,
        precipitation_probability=8.0,
        uv_index=5.0,
        weather_code=1,
        weather_condition="clear",
        time_scope="today",
    )
    selected_sop = SOPMatch(
        sop_id="SOP-BASE-EX-001",
        name="General Outdoor Exercise Baseline",
        category="General Outdoor Exercise",
        severity="low",
        priority=30,
        guidance=(
            "Current conditions fall within WeatherBuddy's normal outdoor-exercise guidance. This is a low-risk baseline range for active outdoor exercise.\n"
            "1. Maintain a steady pace and stay well hydrated\n"
            "2. Favor the cooler parts of the day when the session is longer"
        ),
        reasons=[],
        composite_score=None,
        is_exact_activity_match=True,
    )

    response = await client.compose_response("Can I go cycling in Bhopal today?", facts, selected_sop)
    assert "well hydrated. Favor the cooler parts of the day when the session is longer." in response
    assert "well hydrated Favor the cooler" not in response


@pytest.mark.asyncio
async def test_no_sop_response_does_not_receive_generic_outdoor_exercise_advice():
    client = MockLLMClient()
    facts = WeatherFacts(
        location="Bengaluru",
        latitude=12.97,
        longitude=77.59,
        timestamp="2026-09-23T11:00:00",
        temperature_2m=24.0,
        wind_speed_10m=9.0,
        wind_gusts_10m=12.0,
        precipitation=0.0,
        precipitation_probability=0.0,
        uv_index=4.0,
        weather_code=0,
        weather_condition="clear",
        time_scope="today",
    )

    response = await client.compose_response("Should I paint my bedroom walls today?", facts, selected_sop=None, no_sop=True)
    lower = response.lower()
    assert "no specific policy applies" in lower
    assert "keep the session steady" not in lower
    assert "avoid pushing too hard" not in lower
    assert "running" not in lower
    assert "cycling" not in lower
