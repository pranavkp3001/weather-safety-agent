"""
MediBuddy Weather-Advisory Support Bot - Streamlit Frontend

Sends all chat messages to the FastAPI backend via POST /chat.
No safety, SOP, or weather logic lives here.
"""

import os
from datetime import datetime

import httpx
import streamlit as st

# ─── Configuration ────────────────────────────────────────────────────────────
# Override with env var MEDIBUDDY_BACKEND_URL if needed.
BACKEND_URL = os.environ.get("MEDIBUDDY_BACKEND_URL", "http://127.0.0.1:8000")
CHAT_ENDPOINT = f"{BACKEND_URL}/chat"
HEALTH_ENDPOINT = f"{BACKEND_URL}/health"
REQUEST_TIMEOUT = 60  # seconds – weather fetch + LangGraph can take a moment

# ─── Page setup ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="MediBuddy Weather Advisory", layout="wide")
st.title("MediBuddy Weather-Advisory Support Bot")

# ─── Session state ────────────────────────────────────────────────────────────
if "session_id" not in st.session_state:
    st.session_state.session_id = f"web-{datetime.now().timestamp()}"
    st.session_state.messages = []

session_id: str = st.session_state.session_id

# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("About MediBuddy")
    st.markdown("""
MediBuddy provides weather-based safety advisories using:
- **Live weather data** from Open-Meteo API
- **Deterministic SOPs** (Standard Operating Procedures)
- **Session memory** for follow-up questions

Example questions:
- "Is cycling safe in Bhopal today?"
- "Can I take kids to the park in Pune?"
- "What about this evening instead?"
""")

    if st.button("Clear Chat History"):
        st.session_state.messages = []
        # Ask backend to drop the session context too (best-effort)
        try:
            httpx.delete(f"{BACKEND_URL}/session/{session_id}", timeout=5)
        except Exception:
            pass
        st.rerun()

    with st.expander("Settings"):
        show_trace = st.checkbox("Show decision trace", value=False)
        show_facts = st.checkbox("Show weather facts", value=False)

    st.caption(f"Backend: {BACKEND_URL}")
    st.caption(f"Session: {session_id}")

# ─── Chat history ─────────────────────────────────────────────────────────────
for msg in st.session_state.messages:
    if msg["role"] == "user":
        st.chat_message("user").write(msg["content"])
    else:
        with st.chat_message("assistant"):
            st.write(msg["content"])
            if show_trace and msg.get("trace"):
                with st.expander("Decision Trace"):
                    for line in msg["trace"]:
                        st.text(line)
            if show_facts and msg.get("weather_facts"):
                with st.expander("Weather Facts"):
                    st.json(msg["weather_facts"])
            if msg.get("sop_id"):
                st.caption(
                    f"Based on: {msg['sop_id']}"
                    + (f" ({msg['severity']})" if msg.get("severity") else "")
                )

# ─── Input ────────────────────────────────────────────────────────────────────
user_input = st.chat_input("What would you like to know about outdoor activities?")

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})

    with st.spinner("Checking weather and safety policy..."):
        try:
            resp = httpx.post(
                CHAT_ENDPOINT,
                json={"message": user_input, "session_id": session_id},
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()

            assistant_msg = {
                "role": "assistant",
                "content": data.get("response", "No response received."),
                "trace": data.get("decision_trace", []),
                "weather_facts": data.get("weather_facts"),
                "sop_id": data.get("sop_id"),
                "severity": data.get("severity"),
            }

        except httpx.ConnectError:
            assistant_msg = {
                "role": "assistant",
                "content": (
                    f"Cannot connect to the MediBuddy backend at {BACKEND_URL}. "
                    "Please start the FastAPI server with:\n\n"
                    "```\nuvicorn backend.app.main:app --port 8000\n```"
                ),
            }
        except httpx.TimeoutException:
            assistant_msg = {
                "role": "assistant",
                "content": "The backend took too long to respond. Please try again.",
            }
        except httpx.HTTPStatusError as exc:
            assistant_msg = {
                "role": "assistant",
                "content": f"Backend returned an error ({exc.response.status_code}). Please try again.",
            }
        except Exception as exc:
            assistant_msg = {
                "role": "assistant",
                "content": f"Unexpected error: {exc}",
            }

    st.session_state.messages.append(assistant_msg)
    st.rerun()
