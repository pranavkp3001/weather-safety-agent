"""
MediBuddy Weather-Advisory Support Bot - Streamlit Frontend
"""

import streamlit as st
import asyncio
import json
from datetime import datetime
from backend.app.graph.workflow import weather_bot_graph
from backend.app.services.session import session_manager

st.set_page_config(page_title="MediBuddy Weather Advisory", layout="wide")
st.title("🌦️ MediBuddy Weather-Advisory Support Bot")

# Initialize session state
if "session_id" not in st.session_state:
    st.session_state.session_id = f"web-session-{datetime.now().timestamp()}"
    st.session_state.messages = []

session_id = st.session_state.session_id

# Sidebar with info
with st.sidebar:
    st.header("About MediBuddy")
    st.markdown("""
    MediBuddy provides weather-based safety advisories using:
    - **Live weather data** from Open-Meteo API
    - **Deterministic SOPs** (Standard Operating Procedures)
    - **Session memory** for follow-up questions
    
    Ask questions like:
    - "Is cycling safe in Bhopal today?"
    - "Can I take kids to the park?"
    - "What about this evening instead?"
    """)
    
    if st.button("🔄 Clear Chat History"):
        st.session_state.messages = []
        session_manager.clear(session_id)
        st.rerun()
    
    with st.expander("ℹ️ Settings"):
        show_trace = st.checkbox("Show decision trace", value=False)
        show_facts = st.checkbox("Show weather facts", value=False)

# Display chat history
st.subheader("Conversation")
chat_container = st.container()

with chat_container:
    for msg in st.session_state.messages:
        if msg["role"] == "user":
            st.chat_message("user").write(msg["content"])
        else:
            with st.chat_message("assistant"):
                st.write(msg["content"])
                if show_trace and "trace" in msg:
                    with st.expander("📋 Decision Trace"):
                        for line in msg["trace"]:
                            st.text(line)
                if show_facts and "weather_facts" in msg:
                    with st.expander("🌡️ Weather Facts"):
                        st.json(msg["weather_facts"])
                if "sop_id" in msg:
                    st.caption(f"📌 Based on: {msg['sop_id']} ({msg.get('severity', 'N/A')})")

# Input form
st.subheader("Ask a Question")
user_input = st.chat_input("What would you like to know about outdoor activities?")

if user_input:
    # Add user message to history
    st.session_state.messages.append({"role": "user", "content": user_input})
    
    # Create initial state for workflow
    initial_state = {
        "session_id": session_id,
        "user_query": user_input,
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
    
    # Run workflow
    with st.spinner("Analyzing weather and safety..."):
        try:
            # Run async workflow in sync context
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(weather_bot_graph.ainvoke(initial_state))
            loop.close()
            
            # Extract response and metadata
            final_response = result.get("final_response", "No response generated")
            
            assistant_msg = {
                "role": "assistant",
                "content": final_response,
                "trace": result.get("decision_trace", []),
                "weather_facts": result.get("weather_facts", {}),
            }
            
            if result.get("selected_sop"):
                sop = result["selected_sop"]
                assistant_msg["sop_id"] = sop.sop_id
                assistant_msg["severity"] = sop.severity
            
            st.session_state.messages.append(assistant_msg)
            st.rerun()
            
        except Exception as e:
            st.error(f"Error processing request: {str(e)}")
            st.session_state.messages.append({
                "role": "assistant",
                "content": f"Sorry, I encountered an error: {str(e)}"
            })

st.markdown("---")
st.caption(f"Session ID: {session_id}")
st.caption("MediBuddy - Weather-based safety decisions powered by deterministic SOPs")
