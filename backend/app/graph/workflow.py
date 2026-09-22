from typing import Literal
from langgraph.graph import StateGraph, START, END
from backend.app.graph.state import AgentState
from backend.app.graph.nodes import (
    parse_intent_node,
    resolve_session_context_node,
    handle_location_error_node,
    fetch_weather_node,
    handle_weather_error_node,
    match_sops_node,
    handle_no_sop_node,
    compose_response_node,
    validate_response_node
)


def route_after_context(state: AgentState) -> Literal["handle_location_error", "handle_no_sop", "fetch_weather"]:
    err = state.get("error_type")
    if err == "location_error":
        return "handle_location_error"
    elif err == "no_sop":
        return "handle_no_sop"
    return "fetch_weather"


def route_after_weather(state: AgentState) -> Literal["handle_weather_error", "match_sops"]:
    if state.get("error_type") == "weather_error" or state.get("weather_facts") is None:
        return "handle_weather_error"
    return "match_sops"


def route_after_sops(state: AgentState) -> Literal["handle_no_sop", "compose_response"]:
    if state.get("error_type") == "no_sop" or state.get("selected_sop") is None:
        return "handle_no_sop"
    return "compose_response"


def build_weather_bot_graph():
    builder = StateGraph(AgentState)

    # 1. Add All Graph Nodes
    builder.add_node("parse_intent", parse_intent_node)
    builder.add_node("resolve_session_context", resolve_session_context_node)
    builder.add_node("handle_location_error", handle_location_error_node)
    builder.add_node("fetch_weather", fetch_weather_node)
    builder.add_node("handle_weather_error", handle_weather_error_node)
    builder.add_node("match_sops", match_sops_node)
    builder.add_node("handle_no_sop", handle_no_sop_node)
    builder.add_node("compose_response", compose_response_node)
    builder.add_node("validate_response", validate_response_node)

    # 2. Add Fixed and Conditional Edges
    builder.add_edge(START, "parse_intent")
    builder.add_edge("parse_intent", "resolve_session_context")

    builder.add_conditional_edges(
        "resolve_session_context",
        route_after_context,
        {
            "handle_location_error": "handle_location_error",
            "handle_no_sop": "handle_no_sop",
            "fetch_weather": "fetch_weather"
        }
    )

    builder.add_conditional_edges(
        "fetch_weather",
        route_after_weather,
        {
            "handle_weather_error": "handle_weather_error",
            "match_sops": "match_sops"
        }
    )

    builder.add_conditional_edges(
        "match_sops",
        route_after_sops,
        {
            "handle_no_sop": "handle_no_sop",
            "compose_response": "compose_response"
        }
    )

    builder.add_edge("compose_response", "validate_response")
    builder.add_edge("validate_response", END)

    # Terminal error leaves
    builder.add_edge("handle_location_error", END)
    builder.add_edge("handle_weather_error", END)
    builder.add_edge("handle_no_sop", END)

    return builder.compile()


# Compiled singleton graph
weather_bot_graph = build_weather_bot_graph()
