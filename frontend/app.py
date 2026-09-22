"""WeatherBuddy Streamlit frontend.

This file is intentionally limited to presentation and API integration.
No backend logic or policy files are modified.
"""

import os
from datetime import datetime
from html import escape
from pathlib import Path

import httpx
import streamlit as st
import yaml

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
if "sop_panel_open" not in st.session_state:
    st.session_state.sop_panel_open = False


def reset_session():
    st.session_state.session_id = f"web-{datetime.now().timestamp()}"
    st.session_state.result = None
    st.session_state.last_question = ""
    st.session_state.sop_panel_open = False


session_id = st.session_state.session_id

EXAMPLE_PROMPTS = [
    ("🏃", "Can I go running in Bengaluru today?"),
    ("🚴", "Is cycling okay in Bhopal this evening?"),
    ("🧺", "Can we have a picnic in Tokyo today?"),
    ("🧒", "Is the park okay in London today?"),
]


def query_backend(prompt: str):
    current_session_id = st.session_state.get("session_id")
    try:
        response = httpx.post(
            CHAT_ENDPOINT,
            json={"message": prompt, "session_id": current_session_id},
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


def safe_text(value, fallback="Unavailable"):
    if value is None or value == "":
        return fallback
    return str(value)


def format_weather_value(value, suffix=""):
    if value is None:
        return "Unavailable"
    return f"{value}{suffix}"


def get_activity_label(question: str) -> str:
    q = (question or "").lower()
    if any(word in q for word in ["jog", "run", "running"]):
        return "Running"
    if any(word in q for word in ["cycle", "cycling", "bike", "biking"]):
        return "Cycling"
    if any(word in q for word in ["walk", "walking", "hike", "hiking"]):
        return "Walking"
    if any(word in q for word in ["picnic", "park", "playground", "outdoor"]):
        return "Park visit"
    return "Outdoor activity"


def get_status_label(severity):
    normalized = (severity or "").lower()
    mapping = {
        "low": "Guidance available",
        "moderate": "Review guidance",
        "high": "High-risk guidance",
        "severe": "Severe-weather guidance",
        None: "No specific guidance",
        "": "No specific guidance",
    }
    return mapping.get(normalized, "No specific guidance")


def load_sop_catalog():
    yaml_path = Path(__file__).resolve().parent.parent / "backend" / "app" / "policies" / "sops.yaml"
    try:
        with yaml_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        return (data.get("sops") or [])
    except Exception:
        return []


def render_header():
    header_cols = st.columns([3.5, 1.8, 0.8, 0.9])

    with header_cols[0]:
        st.markdown(
            """
            <div class="brand-wrap">
              <div class="brand-mark">cloud_sync</div>
              <span class="brand-name">WeatherBuddy</span>
              <span class="brand-subtitle">Policy-First Weather Advisory Support Bot</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with header_cols[1]:
        st.markdown(
            """
            <div class="status-pill-main">
              <span class="status-dot"></span>
              <span>15 SOPs Active</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with header_cols[2]:
        sop_pressed = st.button("SOPs", key="header_sops", use_container_width=True)
        if sop_pressed:
            st.session_state.sop_panel_open = not st.session_state.get("sop_panel_open", False)

    with header_cols[3]:
        new_session_pressed = st.button("New Session", key="header_new_session", use_container_width=True)
        if new_session_pressed:
            reset_session()
            st.rerun()

    if st.session_state.get("sop_panel_open"):
        sops = load_sop_catalog()
        st.markdown(
            """
            <div class="sop-panel-overlay">
              <div class="sop-panel">
                <div class="sop-panel-header-row">
                  <div class="sop-panel-title">Active Safety Guidelines</div>
                  <div class="sop-panel-copy">15 SOPs currently active</div>
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        close_col, _ = st.columns([1, 6])
        with close_col:
            if st.button("Close", key="sop_close"):
                st.session_state.sop_panel_open = False
                st.rerun()

        sop_grid = st.columns(2)
        for index, sop in enumerate(sops[:15]):
            if not isinstance(sop, dict):
                continue
            column = sop_grid[index % 2]
            with column:
                sop_id = safe_text(sop.get("id"), "Unknown")
                sop_name = safe_text(sop.get("name"), "Unnamed SOP")
                severity = safe_text(sop.get("severity"), "Unknown")
                category = safe_text(sop.get("category"), "General")
                st.markdown(
                    f"""
                    <div class="sop-card">
                      <div class="sop-card-id">{escape(sop_id)}</div>
                      <div class="sop-card-name">{escape(sop_name)}</div>
                      <div class="sop-card-meta">{escape(severity)} · {escape(category)}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    st.markdown("<div class='header-divider'></div>", unsafe_allow_html=True)


def render_hero():
    st.markdown(
        """
        <section class="hero-wrap">
          <div class="ambient-glow"></div>
          <div class="hero-badge">
            <span class="material-symbols-outlined">auto_awesome</span>
            <span>Weather Advisory Assistant</span>
          </div>
          <h1>Know if the weather works for your plans.</h1>
          <p>Ask about an outdoor activity and WeatherBuddy will check live weather against its safety guidelines.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_prompt_form():
    user_input = st.session_state.last_question
    with st.form("weather_prompt_form", clear_on_submit=True):
        input_col, button_col = st.columns([8.2, 1.2], gap="small")
        with input_col:
            user_input = st.text_input(
                "Ask a weather question",
                value=user_input,
                placeholder="Ask about cycling, running, hiking, or family outings...",
                label_visibility="collapsed",
            )
        with button_col:
            submitted = st.form_submit_button("➜", help="Ask", use_container_width=True)

    if submitted and user_input.strip():
        st.session_state.last_question = user_input.strip()
        query_backend(user_input.strip())
        st.rerun()

    st.markdown('<div class="scenario-label">Test Scenarios:</div>', unsafe_allow_html=True)
    st.markdown('<div class="chip-row">', unsafe_allow_html=True)
    prompt_cols = st.columns(len(EXAMPLE_PROMPTS))
    for index, (emoji, prompt) in enumerate(EXAMPLE_PROMPTS):
        compact_prompt = f"{emoji} {prompt}"
        with prompt_cols[index]:
            if st.button(compact_prompt, key=f"chip-{index}", use_container_width=True):
                st.session_state.last_question = prompt
                query_backend(prompt)
                st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)


def render_result():
    result = st.session_state.result
    if not result:
        return

    weather = result.get("weather_facts") or {}
    location = escape(safe_text(weather.get("location"), "Unavailable"))
    time_scope = escape(safe_text(weather.get("time_scope"), "Unavailable"))
    weather_condition = escape(safe_text(weather.get("weather_condition"), "Unavailable"))
    temp = weather.get("temperature_2m")
    precipitation = weather.get("precipitation_probability")
    wind = weather.get("wind_speed_10m")
    severity = str(result.get("severity") or "").lower()
    activity_label = get_activity_label(st.session_state.last_question)

    metric_cards = [
        ("Temperature", "thermostat", format_weather_value(temp, "°C") if temp is not None else "Unavailable", "text-tertiary"),
        ("Conditions", "filter_drama", weather_condition.title() if weather_condition and weather_condition != "Unavailable" else "Unavailable", "text-primary"),
        ("Rain Probability", "water_drop", format_weather_value(precipitation, "%") if precipitation is not None else "Unavailable", "text-primary-container"),
        ("Wind", "air", format_weather_value(wind, " km/h") if wind is not None else "Unavailable", "text-outline"),
    ]

    recommendation = escape((result.get("response") or "No response received."))
    status_text = escape(get_status_label(severity))
    has_policy = bool(result.get("sop_id") or result.get("sop_name"))
    status_label = "NO POLICY APPLICABLE" if not has_policy else (status_text or "GUIDANCE AVAILABLE")
    sop_label = escape(result.get("sop_name") or result.get("sop_id") or "No policy applicable")
    policy_condition = "No matching policy condition returned by the backend."
    trace_values = result.get("decision_trace") or []
    if trace_values:
        policy_condition = "<br>".join(escape(str(item)) for item in trace_values)

    st.markdown(
        f"""
        <section class="result-shell">
          <div class="header-row">
            <div class="location-block">
              <span class="material-symbols-outlined">location_on</span>
              <h2>{location}</h2>
            </div>
            <p>{escape(time_scope.title())} · {escape(activity_label)}</p>
          </div>
          <div class="metrics-grid">
            {''.join(f'''<div class="metric-card"><div class="metric-top"><span class="metric-label">{escape(label)}</span><span class="material-symbols-outlined {cls}">{icon}</span></div><div class="metric-value">{escape(value)}</div></div>''' for label, icon, value, cls in metric_cards)}
          </div>
          <div class="recommendation-card">
            <div class="pill-row">
              <div class="verdict-pill { 'no-policy' if not has_policy else '' }"><span class="material-symbols-outlined">{ 'info' if not has_policy else 'check_circle' }</span><span>{status_label}</span></div>
              <div class="meta-badge"><span class="material-symbols-outlined">verified</span></div>
            </div>
            <p class="recommendation-copy">{recommendation}</p>
            <details class="audit-panel">
              <summary>Why this recommendation?</summary>
              <div class="accordion-panel">
                <div class="detail-grid">
                  <div class="detail-box"><div class="detail-label">Policy Applied</div><div class="detail-value">{sop_label}</div></div>
                  <div class="detail-box"><div class="detail-label">Severity Assessment</div><div class="severity-box"><span class="material-symbols-outlined">check_circle</span><span>{status_text or 'No policy applicable'}</span></div></div>
                  <div class="detail-box wide"><div class="detail-label">Weather Facts</div><div class="detail-value-small">Precipitation: {escape(format_weather_value(precipitation, '%') if precipitation is not None else 'Unavailable')} · Temperature: {escape(format_weather_value(temp, '°C') if temp is not None else 'Unavailable')} · Wind: {escape(format_weather_value(wind, ' km/h') if wind is not None else 'Unavailable')}</div></div>
                  <div class="detail-box wide">
                    <div class="detail-label">Matched Policy Conditions</div>
                    <div class="match-row"><span class="material-symbols-outlined">task_alt</span><span>{policy_condition}</span></div>
                  </div>
                </div>
              </div>
            </details>
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def main():
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@600;700&display=swap');
        @import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200');

        html, body {
            margin: 0;
            padding: 0;
            background: #f9f9fc;
            color: #1a1c1e;
            font-family: "Inter", sans-serif;
        }
        .stApp {
            background: #f9f9fc;
            color: #1a1c1e;
        }
        .main .block-container {
            max-width: 1050px !important;
            padding-top: 0.5rem !important;
            padding-left: 2rem !important;
            padding-right: 2rem !important;
            padding-bottom: 0 !important;
        }
        [data-testid="stHeader"],
        [data-testid="stToolbar"],
        [data-testid="stDecoration"],
        #MainMenu,
        footer {
            display: none !important;
        }
        .stApp > header {
            display: none !important;
        }
        .main .block-container {
            padding-top: 0 !important;
        }
        .app-header {
            position: sticky;
            top: 0;
            z-index: 20;
            width: 100%;
            background: rgba(255,255,255,0.85);
            backdrop-filter: blur(10px);
            border-bottom: 1px solid rgba(91,90,106,0.12);
            box-shadow: 0 1px 8px rgba(0,0,0,0.03);
        }
        .header-inner {
            max-width: 1440px;
            margin: 0 auto;
            height: 56px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0 2rem;
        }
        .brand-wrap {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            min-width: 0;
            padding: 0.25rem 0;
        }
        .brand-mark {
            width: 28px;
            height: 28px;
            border-radius: 8px;
            background: #4f46e5;
            color: white;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 18px;
            font-family: 'Material Symbols Outlined';
            box-shadow: 0 1px 3px rgba(79,70,229,0.25);
        }
        .brand-name {
            font-family: "Plus Jakarta Sans", sans-serif;
            font-size: 18px;
            font-weight: 600;
            color: #1a1c1e;
            letter-spacing: -0.01em;
        }
        .brand-subtitle {
            display: inline-flex;
            align-items: center;
            padding: 2px 8px;
            border-radius: 999px;
            background: rgba(242,243,246,0.9);
            border: 1px solid rgba(119,117,135,0.18);
            color: #464555;
            font-size: 11px;
            line-height: 14px;
            letter-spacing: 0.02em;
            font-weight: 500;
            white-space: nowrap;
        }
        .header-actions {
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }
        .status-pill-main {
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            padding: 0.35rem 0.7rem;
            border-radius: 999px;
            background: rgba(133, 248, 196, 0.28);
            border: 1px solid rgba(0,108,74,0.1);
            color: #005137;
            font-size: 11px;
            font-weight: 600;
        }
        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #006c4a;
            display: inline-block;
            box-shadow: 0 0 0 0 rgba(0,108,74,0.3);
            animation: pulse 1.8s infinite;
        }
        @keyframes pulse {
            0% { box-shadow: 0 0 0 0 rgba(0,108,74,0.3); }
            70% { box-shadow: 0 0 0 6px rgba(0,108,74,0); }
            100% { box-shadow: 0 0 0 0 rgba(0,108,74,0); }
        }
        .stButton > button,
        .stFormSubmitButton > button,
        div[data-testid="stFormSubmitButton"] button {
            border-radius: 12px !important;
            min-height: 52px !important;
            background: linear-gradient(135deg, #4f46e5, #4e49df) !important;
            color: white !important;
            border: 1px solid rgba(79,70,229,0.15) !important;
            font-weight: 600 !important;
            box-shadow: 0 1px 3px rgba(79,70,229,0.15) !important;
        }
        .stButton > button:hover,
        .stFormSubmitButton > button:hover,
        div[data-testid="stFormSubmitButton"] button:hover {
            background: linear-gradient(135deg, #4338ca, #3f3ad8) !important;
            color: white !important;
            border-color: rgba(79,70,229,0.25) !important;
        }
        .stButton > button:focus,
        .stFormSubmitButton > button:focus,
        div[data-testid="stFormSubmitButton"] button:focus {
            box-shadow: 0 0 0 2px rgba(79,70,229,0.35) !important;
            outline: none !important;
            background: linear-gradient(135deg, #4f46e5, #4e49df) !important;
            color: white !important;
            border-color: rgba(79,70,229,0.25) !important;
        }
        .header-button {
            display: inline-flex;
            align-items: center;
            gap: 0.3rem;
            padding: 0.4rem 0.7rem;
            border-radius: 8px;
            border: 1px solid rgba(119,117,135,0.2);
            background: white;
            color: #464555;
            font-size: 12px;
            font-weight: 500;
            cursor: pointer;
        }
        .header-button .material-symbols-outlined {
            font-size: 15px;
        }
        .hero-wrap {
            position: relative;
            text-align: center;
            padding-top: 0.85rem;
            padding-bottom: 1.25rem;
        }
        .ambient-glow {
            position: absolute;
            left: 50%;
            top: 0;
            transform: translateX(-50%);
            width: 420px;
            height: 160px;
            background: linear-gradient(to bottom, rgba(195,192,255,0.35), rgba(195,192,255,0));
            filter: blur(28px);
            pointer-events: none;
            z-index: 0;
        }
        .hero-badge {
            position: relative;
            z-index: 1;
            display: inline-flex;
            align-items: center;
            gap: 0.45rem;
            padding: 0.4rem 0.8rem;
            border-radius: 999px;
            background: rgba(242,243,246,0.9);
            border: 1px solid rgba(79,70,229,0.08);
            color: #4d44e3;
            text-transform: uppercase;
            letter-spacing: 0.18em;
            font-size: 11px;
            font-weight: 600;
        }
        .hero-badge .material-symbols-outlined {
            font-size: 14px;
        }
        .hero-wrap h1 {
            position: relative;
            z-index: 1;
            margin: 0.8rem auto 0;
            max-width: 720px;
            font-family: "Plus Jakarta Sans", sans-serif;
            font-size: 54px;
            line-height: 1.12;
            letter-spacing: -0.03em;
            font-weight: 700;
            color: #1a1c1e;
        }
        .hero-wrap p {
            position: relative;
            z-index: 1;
            margin: 0.7rem auto 0;
            max-width: 620px;
            color: #464555;
            font-size: 16px;
            line-height: 1.5;
        }
        .stForm {
            margin-top: 0.2rem;
            margin-bottom: 0.25rem;
        }
        div[data-testid="stHorizontalBlock"] {
            gap: 0.75rem;
            align-items: stretch !important;
        }
        div[data-testid="stForm"] .stTextInput {
            margin: 0 !important;
        }
        div[data-testid="stForm"] .stTextInput > div > div > input {
            background: rgba(255,255,255,0.96);
            border: 1px solid rgba(119,117,135,0.12);
            border-radius: 12px;
            min-height: 58px !important;
            height: 58px !important;
            box-shadow: 0 1px 5px rgba(0,0,0,0.02);
            padding: 0 1rem;
            color: #1a1c1e;
            font-size: 16px;
            margin: 0 !important;
        }
        .stTextInput > div > div > input::placeholder {
            color: #777587;
        }
        .stButton > button {
            border-radius: 12px;
            min-height: 52px;
            background: linear-gradient(135deg, #4f46e5, #4e49df);
            color: white;
            border: 1px solid rgba(79,70,229,0.15);
            font-weight: 600;
            box-shadow: 0 1px 3px rgba(79,70,229,0.15);
        }
        div[data-testid="stFormSubmitButton"] {
            display: flex !important;
            align-items: stretch !important;
            margin: 0 !important;
        }
        div[data-testid="stFormSubmitButton"] > button {
            width: 58px !important;
            min-width: 58px !important;
            max-width: 58px !important;
            height: 58px !important;
            min-height: 58px !important;
            padding: 0 !important;
            border-radius: 12px !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            font-size: 20px !important;
            line-height: 1 !important;
            background: linear-gradient(135deg, #4f46e5, #4e49df) !important;
            color: white !important;
            border: 1px solid rgba(79,70,229,0.15) !important;
            box-shadow: 0 4px 10px rgba(79,70,229,0.18) !important;
            transition: transform 0.15s ease, box-shadow 0.15s ease, filter 0.15s ease !important;
        }
        div[data-testid="stFormSubmitButton"] > button:hover {
            transform: translateY(-1px);
            box-shadow: 0 6px 14px rgba(79,70,229,0.2) !important;
            filter: brightness(1.03);
        }
        .scenario-label {
            display: block;
            margin-top: 0.35rem;
            margin-bottom: 0.4rem;
            color: #4b5563;
            font-size: 12px;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }
        .chip-row {
            display: flex;
            flex-wrap: wrap;
            justify-content: center;
            gap: 0.55rem;
            margin-top: 0.2rem;
            margin-bottom: 1.4rem;
        }
        .chip-row .stButton > button {
            min-height: 38px !important;
            padding: 0.5rem 0.9rem !important;
            background: rgba(255,255,255,0.96) !important;
            color: #1f2937 !important;
            border: 1px solid rgba(119,117,135,0.18) !important;
            border-radius: 999px !important;
            box-shadow: 0 1px 3px rgba(0,0,0,0.02) !important;
            font-size: 12px !important;
            font-weight: 500 !important;
            line-height: 1.25 !important;
        }
        .chip-row .stButton > button:hover {
            background: rgba(246,247,249,1) !important;
            border-color: rgba(119,117,135,0.25) !important;
            color: #111827 !important;
        }
        .chip-row .stButton > button:focus {
            box-shadow: 0 0 0 2px rgba(79,70,229,0.15) !important;
            border-color: rgba(79,70,229,0.2) !important;
        }
        .sop-panel-overlay {
            position: relative;
            margin-top: 0.5rem;
            margin-bottom: 0.5rem;
            padding: 0;
        }
        .sop-panel {
            background: rgba(255,255,255,0.98);
            border: 1px solid rgba(119,117,135,0.15);
            border-radius: 14px;
            box-shadow: 0 10px 24px rgba(15, 23, 42, 0.06);
            padding: 0.9rem 1rem 0.2rem;
        }
        .sop-panel-header-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.75rem;
            margin-bottom: 0.35rem;
        }
        .sop-panel-title {
            color: #1f2937;
            font-size: 14px;
            font-weight: 700;
            letter-spacing: 0.02em;
        }
        .sop-panel-copy {
            color: #4b5563;
            font-size: 12px;
            line-height: 1.5;
        }
        .sop-card {
            background: rgba(248,249,251,0.9);
            border: 1px solid rgba(119,117,135,0.12);
            border-radius: 8px;
            padding: 0.7rem 0.75rem;
            min-height: 96px;
            margin-bottom: 0.6rem;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.02);
        }
        .sop-card-id {
            color: #4f46e5;
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            margin-bottom: 0.25rem;
        }
        .sop-card-name {
            color: #1f2937;
            font-size: 14px;
            font-weight: 600;
            line-height: 1.35;
            margin-bottom: 0.3rem;
        }
        .sop-card-meta {
            color: #4b5563;
            font-size: 12px;
            line-height: 1.4;
        }
        .header-divider {
            height: 1px;
            background: rgba(91,90,106,0.12);
            margin-top: 0.2rem;
        }
        .result-shell {
            margin-top: 0.4rem;
            width: 100%;
        }
        .header-row {
            display: flex;
            align-items: flex-end;
            justify-content: space-between;
            gap: 1rem;
            margin-bottom: 1rem;
        }
        .location-block {
            display: flex;
            align-items: center;
            gap: 0.45rem;
            color: #1a1c1e;
        }
        .location-block .material-symbols-outlined {
            color: #4d44e3;
            font-size: 22px;
        }
        .location-block h2 {
            margin: 0;
            font-family: "Plus Jakarta Sans", sans-serif;
            font-size: 24px;
            line-height: 32px;
            letter-spacing: -0.02em;
            font-weight: 600;
            color: #1a1c1e;
        }
        .header-row p {
            margin: 0;
            color: #464555;
            font-size: 13px;
            line-height: 18px;
        }
        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 1rem;
        }
        .metric-card {
            background: rgba(255,255,255,0.96);
            border: 1px solid rgba(119,117,135,0.12);
            border-radius: 12px;
            padding: 1rem;
            box-shadow: 0 1px 2px rgba(0,0,0,0.02);
            min-height: 110px;
        }
        .metric-top {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.75rem;
        }
        .metric-label {
            color: #464555;
            font-size: 11px;
            line-height: 16px;
            letter-spacing: 0.02em;
            text-transform: uppercase;
            font-weight: 600;
        }
        .metric-top .material-symbols-outlined {
            font-size: 20px;
        }
        .text-tertiary { color: #934e00; }
        .text-primary { color: #4d44e3; }
        .text-primary-container { color: #4d44e3; }
        .text-outline { color: #777587; }
        .metric-value {
            margin-top: 0.85rem;
            font-family: "Plus Jakarta Sans", sans-serif;
            font-size: 32px;
            line-height: 40px;
            letter-spacing: -0.025em;
            font-weight: 600;
            color: #1a1c1e;
        }
        .recommendation-card {
            position: relative;
            margin-top: 1.1rem;
            background: rgba(255,255,255,0.96);
            border: 1px solid rgba(119,117,135,0.12);
            border-radius: 12px;
            padding: 1rem 1rem 0;
            overflow: hidden;
            box-shadow: 0 1px 2px rgba(0,0,0,0.02);
        }
        .recommendation-card::before {
            content: "";
            position: absolute;
            top: 0;
            right: 0;
            width: 260px;
            height: 260px;
            background: linear-gradient(to bottom left, rgba(133,248,196,0.22), rgba(133,248,196,0));
            pointer-events: none;
        }
        .pill-row {
            position: relative;
            z-index: 1;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.75rem;
            margin-bottom: 0.9rem;
        }
        .verdict-pill {
            display: inline-flex;
            align-items: center;
            gap: 0.45rem;
            padding: 0.35rem 0.75rem;
            border-radius: 999px;
            background: rgba(133,248,196,0.32);
            border: 1px solid rgba(0,108,74,0.08);
            color: #005137;
            font-size: 12px;
            font-weight: 600;
        }
        .verdict-pill.no-policy {
            background: rgba(243,244,246,0.92);
            border-color: rgba(119,117,135,0.2);
            color: #374151;
        }
        .meta-badge {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 24px;
            height: 24px;
            border-radius: 8px;
            background: rgba(242,243,246,0.9);
            color: #464555;
        }
        .recommendation-copy {
            position: relative;
            z-index: 1;
            margin: 0;
            max-width: 880px;
            color: #1a1c1e;
            font-size: 15px;
            line-height: 1.8;
            font-weight: 500;
        }
        .audit-panel {
            position: relative;
            z-index: 1;
            display: block;
            margin-top: 1rem;
            background: rgba(242,243,246,0.5);
            border-top: 1px solid rgba(119,117,135,0.1);
            border-radius: 0 0 12px 12px;
            padding: 0.9rem 1rem 1rem;
        }
        .audit-panel summary {
            display: flex;
            align-items: center;
            gap: 0.35rem;
            color: #4d44e3;
            font-size: 12px;
            font-weight: 600;
            letter-spacing: 0.02em;
            cursor: pointer;
            list-style: none;
        }
        .audit-panel summary::-webkit-details-marker {
            display: none;
        }
        .audit-panel summary::before {
            content: "expand_more";
            font-family: "Material Symbols Outlined";
            font-size: 18px;
            font-weight: 400;
            display: inline-block;
            transform: rotate(-90deg);
        }
        details[open] > summary::before {
            transform: rotate(0deg);
        }
        .accordion-panel {
            display: block;
            margin-top: 0.85rem;
        }
        .detail-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.75rem;
            margin-top: 0.85rem;
        }
        .detail-box {
            background: rgba(255,255,255,0.96);
            border: 1px solid rgba(119,117,135,0.15);
            border-radius: 8px;
            padding: 0.7rem 0.8rem;
        }
        .detail-box.wide {
            grid-column: span 2;
        }
        .detail-label {
            color: #464555;
            font-size: 11px;
            line-height: 14px;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            font-weight: 600;
            margin-bottom: 0.35rem;
        }
        .detail-value {
            color: #1a1c1e;
            font-size: 15px;
            line-height: 20px;
            font-weight: 600;
        }
        .severity-box {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            padding: 0.2rem 0.5rem;
            border-radius: 999px;
            background: rgba(133,248,196,0.28);
            color: #005137;
            font-size: 12px;
            font-weight: 600;
        }
        .detail-value-small,
        .match-row {
            color: #464555;
            font-size: 13px;
            line-height: 18px;
        }
        .match-row {
            display: flex;
            align-items: center;
            gap: 0.4rem;
            color: #006c4a;
            font-weight: 600;
        }
        .match-row .material-symbols-outlined {
            font-size: 16px;
        }
        @media (max-width: 900px) {
            .header-inner {
                padding: 0 1rem;
            }
            .brand-subtitle {
                display: none;
            }
            .metrics-grid {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
            .header-row {
                flex-direction: column;
                align-items: flex-start;
            }
        }
        @media (max-width: 640px) {
            .hero-wrap h1 {
                font-size: 38px;
            }
            .metrics-grid {
                grid-template-columns: 1fr;
            }
            .detail-grid {
                grid-template-columns: 1fr;
            }
            .detail-box.wide {
                grid-column: span 1;
            }
            .header-actions {
                gap: 0.35rem;
            }
            .status-pill-main {
                display: none;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    render_header()
    render_hero()
    render_prompt_form()
    render_result()


if __name__ == "__main__":
    main()
