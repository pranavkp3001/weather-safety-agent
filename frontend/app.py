"""WeatherBuddy Streamlit frontend.

This file is intentionally limited to presentation and API integration.
No backend logic or policy files are modified.
"""

import os
from datetime import datetime

import httpx
import streamlit as st

BACKEND_URL = os.environ.get("MEDIBUDDY_BACKEND_URL", "http://127.0.0.1:8000")
CHAT_ENDPOINT = f"{BACKEND_URL}/chat"
REQUEST_TIMEOUT = 60

st.set_page_config(page_title="WeatherBuddy", page_icon="☁️", layout="wide")

if "session_id" not in st.session_state:
    st.session_state.session_id = f"web-{datetime.now().timestamp()}"
if "result" not in st.session_state:
    st.session_state.result = None
if "last_question" not in st.session_state:
    st.session_state.last_question = ""

session_id = st.session_state.session_id

EXAMPLE_PROMPTS = [
    "Can I go jogging in Bengaluru today?",
    "Is it safe for a child to visit the park in London?",
    "Can I go cycling in Bhopal during a thunderstorm?",
    "Can I have a picnic?",
]


def query_backend(prompt: str):
    try:
        response = httpx.post(
            CHAT_ENDPOINT,
            json={"message": prompt, "session_id": session_id},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        st.session_state.result = response.json()
    except Exception as exc:
        st.session_state.result = {
            "response": f"The backend is unavailable right now. Please try again. ({exc})",
            "sop_id": None,
            "sop_name": None,
            "severity": None,
            "error_type": "backend_error",
            "fallback_used": False,
            "decision_trace": [],
            "weather_facts": None,
        }


def render_header():
    left, center, right = st.columns([2.8, 2.8, 2.6])

    with left:
        st.markdown(
            """
            <div class="header-brand">
              <div class="brand-icon">W</div>
              <div class="brand-copy">
                <div class="brand-name">WeatherBuddy</div>
                <div class="brand-subtitle">Policy-First Weather Advisory Support Bot</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with center:
        st.empty()

    with right:
        action_cols = st.columns([1.2, 1.0, 1.15])
        with action_cols[0]:
            st.markdown("<div class='top-pill'>15 SOPs Active</div>", unsafe_allow_html=True)
        with action_cols[1]:
            if st.button("SOPs", key="sops-btn", use_container_width=True):
                st.session_state.last_question = ""
                st.rerun()
        with action_cols[2]:
            if st.button("New Session", key="new-session-btn", use_container_width=True):
                st.session_state.session_id = f"web-{datetime.now().timestamp()}"
                st.session_state.result = None
                st.session_state.last_question = ""
                st.rerun()


def render_hero():
    st.markdown(
        """
        <div class="hero-block">
          <div class="eyebrow">WEATHER ADVISORY ASSISTANT</div>
          <h1>Know if the weather works for your plans.</h1>
          <p>Ask about an outdoor activity and WeatherBuddy will check live weather against its safety guidelines.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_prompt_form():
    with st.form("weather_prompt_form", clear_on_submit=True):
        input_col, button_col = st.columns([7, 1.15])
        with input_col:
            user_input = st.text_input(
                "Ask a weather question",
                value=st.session_state.last_question,
                placeholder="Can I take my daughter to the park in London?",
                label_visibility="collapsed",
            )
        with button_col:
            submitted = st.form_submit_button("Ask", use_container_width=True)

    if submitted and user_input.strip():
        st.session_state.last_question = user_input.strip()
        query_backend(user_input.strip())
        st.rerun()

    chip_cols = st.columns(len(EXAMPLE_PROMPTS))
    for index, prompt in enumerate(EXAMPLE_PROMPTS):
        with chip_cols[index]:
            if st.button(prompt, key=f"chip-{index}", use_container_width=True):
                st.session_state.last_question = prompt
                query_backend(prompt)
                st.rerun()


def render_result():
    result = st.session_state.result
    if not result:
        return

    weather = result.get("weather_facts") or {}
    location = weather.get("location") or "Location"
    time_scope = weather.get("time_scope") or "today"
    condition = weather.get("weather_condition") or "Cloudy"
    temp = weather.get("temperature_2m")
    rain = weather.get("precipitation_probability")
    wind = weather.get("wind_speed_10m")
    severity = str(result.get("severity") or "low").lower()

    state_palette = {
        "low": {"bg": "#EAF8EE", "text": "#17663A"},
        "moderate": {"bg": "#FFF5D6", "text": "#8A5E00"},
        "high": {"bg": "#FFE7D4", "text": "#9A4B1E"},
        "severe": {"bg": "#FDE7E7", "text": "#9D1C32"},
    }
    palette = state_palette.get(severity, {"bg": "#EEF2FF", "text": "#374151"})

    metric_data = [
        ("Temperature", f"{temp}°C" if temp is not None else "—"),
        ("Conditions", str(condition).title()),
        ("Rain probability", f"{rain}%" if rain is not None else "—"),
        ("Wind", f"{wind} km/h" if wind is not None else "—"),
    ]

    st.markdown(
        f"""
        <div class="result-top-row">
          <div class="location-wrap"><span class="pin">📍</span><span>{location}</span></div>
          <div class="time-label">{str(time_scope).title()} · {st.session_state.last_question or 'Outdoors'}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    cards = st.columns(4)
    for index, (label, value) in enumerate(metric_data):
        with cards[index]:
            st.markdown(
                f"<div class='metric-card'><div class='metric-label'>{label}</div><div class='metric-value'>{value}</div></div>",
                unsafe_allow_html=True,
            )

    recommendation = result.get("response") or "No response received."
    status_text = "✓ Conditions look comfortable" if severity == "low" else "⚠️ Review conditions before going out"
    st.markdown(
        f"""
        <div class="recommendation-box">
          <div class="status-pill" style="background:{palette['bg']}; color:{palette['text']};">{status_text}</div>
          <div class="recommendation-copy">{recommendation}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.expander("Why this recommendation?", expanded=False):
        st.write(f"Selected SOP / policy: {result.get('sop_name') or result.get('sop_id') or 'N/A'}")
        st.write(f"Severity: {result.get('severity') or 'N/A'}")
        st.write("Weather facts:")
        st.json(weather)
        decision_trace = result.get("decision_trace") or []
        if decision_trace:
            st.write("Matched conditions:")
            for item in decision_trace:
                st.write(f"- {item}")


def main():
    render_header()
    render_hero()
    render_prompt_form()
    render_result()


st.markdown(
    """
    <style>
    .stApp {
        background: #f4f1ee;
        color: #1f2937;
    }
    .main .block-container {
        max-width: 1020px;
        padding-top: 0.8rem;
        padding-bottom: 1.25rem;
    }
    .header-container {
        border-bottom: 1px solid rgba(17, 24, 39, 0.08);
    }
    .header-brand {
        display: flex;
        align-items: center;
        gap: 10px;
        min-height: 60px;
    }
    .brand-icon {
        width: 22px;
        height: 22px;
        border-radius: 7px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: linear-gradient(135deg, #5a47d7, #7b5cf2);
        color: white;
        font-size: 0.72rem;
        font-weight: 700;
    }
    .brand-copy {
        display: flex;
        flex-direction: column;
        line-height: 1.15;
    }
    .brand-name {
        font-size: 1.05rem;
        font-weight: 700;
        color: #1f2937;
    }
    .brand-subtitle {
        font-size: 0.64rem;
        color: #6b7280;
    }
    .top-pill {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        padding: 0.38rem 0.8rem;
        border-radius: 999px;
        background: #EAF7EE;
        color: #0B7B45;
        border: 1px solid rgba(11, 123, 69, 0.08);
        font-size: 0.7rem;
        font-weight: 700;
        margin: 0.2rem 0 0.55rem auto;
    }
    .stButton > button {
        background: white;
        color: #1f2937;
        border: 1px solid rgba(17, 24, 39, 0.12);
        border-radius: 10px;
        font-weight: 500;
        min-height: 30px;
        padding: 0.35rem 0.8rem;
        box-shadow: 0 1px 0 rgba(17,24,39,0.02);
    }
    .stButton > button:focus,
    .stButton > button:hover {
        border-color: rgba(79, 70, 229, 0.2);
        box-shadow: none;
    }
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #4f46e5, #5c4ee7);
        color: white;
        border: 1px solid rgba(79, 70, 229, 0.25);
    }
    .hero-block {
        margin: 1.1rem auto 0.8rem;
        text-align: center;
        max-width: 760px;
    }
    .eyebrow {
        font-size: 0.68rem;
        letter-spacing: 0.18em;
        color: #6257d8;
        font-weight: 700;
        margin-bottom: 0.55rem;
    }
    .hero-block h1 {
        margin: 0;
        font-size: clamp(1.9rem, 2.7vw, 2.8rem);
        line-height: 1.12;
        letter-spacing: -0.05em;
        color: #1f2937;
        font-weight: 700;
    }
    .hero-block p {
        margin: 0.65rem auto 0;
        max-width: 620px;
        color: #4b5563;
        font-size: 1rem;
        line-height: 1.5;
    }
    .stForm {
        margin-top: 0.2rem;
        padding: 0.35rem 0 0.2rem;
    }
    .stTextInput > div > div > input {
        background: rgba(255,255,255,0.95);
        border: 1px solid rgba(17,24,39,0.12);
        border-radius: 14px;
        color: #1f2937;
        min-height: 52px;
        padding: 0 1rem;
        box-shadow: 0 1px 0 rgba(17, 24, 39, 0.02);
    }
    .stTextInput > div > div > input::placeholder {
        color: #6b7280;
    }
    .stForm button {
        background: linear-gradient(135deg, #4f46e5, #544ce6);
        color: white;
        font-weight: 600;
        border: 1px solid rgba(79, 70, 229, 0.2);
        border-radius: 12px;
        min-height: 52px;
    }
    .chip-button {
        margin-top: 0.4rem;
    }
    .result-top-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
        margin-top: 1.2rem;
        margin-bottom: 0.6rem;
        padding: 0 0.05rem;
    }
    .location-wrap {
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
        font-size: 1.05rem;
        font-weight: 700;
        color: #111827;
    }
    .pin {
        font-size: 1rem;
    }
    .time-label {
        color: #6b7280;
        font-size: 0.76rem;
        text-transform: none;
    }
    .metric-card {
        min-height: 102px;
        background: rgba(255,255,255,0.84);
        border: 1px solid rgba(17,24,39,0.08);
        border-radius: 16px;
        padding: 0.8rem 0.8rem 0.7rem;
        box-shadow: 0 1px 0 rgba(17,24,39,0.02);
    }
    .metric-label {
        color: #6b7280;
        font-size: 0.64rem;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        margin-bottom: 0.5rem;
    }
    .metric-value {
        color: #111827;
        font-size: 1.1rem;
        font-weight: 700;
        line-height: 1.35;
    }
    .recommendation-box {
        margin-top: 1.1rem;
        background: rgba(236, 249, 240, 0.73);
        border: 1px solid rgba(34, 197, 94, 0.15);
        border-radius: 18px;
        padding: 0.9rem 1rem 1rem;
    }
    .status-pill {
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
        border-radius: 999px;
        padding: 0.38rem 0.7rem;
        font-size: 0.68rem;
        font-weight: 700;
        letter-spacing: 0.02em;
        margin-bottom: 0.7rem;
    }
    .recommendation-copy {
        color: #1f2937;
        font-size: 1.02rem;
        line-height: 1.7;
    }
    .stExpander {
        margin-top: 0.8rem;
        border: 1px solid rgba(17,24,39,0.08);
        border-radius: 14px;
        background: rgba(255,255,255,0.7);
    }
    .stExpander summary {
        font-weight: 600;
        color: #374151;
    }
    @media (max-width: 950px) {
        .result-top-row { flex-direction: column; align-items: flex-start; }
        .hero-block { margin-top: 0.7rem; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


main()
