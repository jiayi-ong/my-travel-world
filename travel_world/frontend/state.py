"""
Streamlit session state schema and helper functions.

All shared state across tabs lives in st.session_state under the
'tworld_' namespace to avoid collisions with Streamlit's own keys.

Design: Namespace pattern — all travel world state is prefixed with
'tworld_' so it is easy to identify and reset without affecting Streamlit internals.
"""
import streamlit as st
from dataclasses import dataclass, field

# Keys used in st.session_state
SESSION_ID_KEY = "tworld_session_id"
WORLD_ID_KEY = "tworld_world_id"
PREFERENCES_KEY = "tworld_preferences"
TRIP_PLAN_KEY = "tworld_trip_plan"
CHAT_HISTORY_KEY = "tworld_chat_history"
FLIGHT_RESULTS_KEY = "tworld_flight_results"
HOTEL_RESULTS_KEY = "tworld_hotel_results"
EVENT_RESULTS_KEY = "tworld_event_results"
ROUTE_RESULTS_KEY = "tworld_route_results"
MAP_ORIGIN_KEY = "tworld_map_origin"
MAP_DEST_KEY = "tworld_map_dest"
LLM_CONNECTED_KEY = "tworld_llm_connected"

def init_state() -> None:
    """
    Initialize all tworld_ session state keys with defaults if not already set.
    Call this at the top of app.py before rendering any tab.
    """
    defaults = {
        SESSION_ID_KEY: None,
        WORLD_ID_KEY: None,
        PREFERENCES_KEY: {},
        TRIP_PLAN_KEY: {"items": [], "total_cost": 0.0},
        CHAT_HISTORY_KEY: [],
        FLIGHT_RESULTS_KEY: None,
        HOTEL_RESULTS_KEY: None,
        EVENT_RESULTS_KEY: None,
        ROUTE_RESULTS_KEY: None,
        MAP_ORIGIN_KEY: None,
        MAP_DEST_KEY: None,
        LLM_CONNECTED_KEY: False,
    }
    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_value


def clear_search_results() -> None:
    """Clear all cached search results (called when preferences change)."""
    st.session_state[FLIGHT_RESULTS_KEY] = None
    st.session_state[HOTEL_RESULTS_KEY] = None
    st.session_state[EVENT_RESULTS_KEY] = None
    st.session_state[ROUTE_RESULTS_KEY] = None


def update_preference(key: str, value) -> None:
    """Update one field in the preferences dict and clear search results."""
    st.session_state[PREFERENCES_KEY][key] = value
    clear_search_results()


def get_session_id() -> str | None:
    """Return the current session ID, or None if no session is active."""
    return st.session_state.get(SESSION_ID_KEY)


def get_preferences() -> dict:
    """Return current trip preferences dict."""
    return st.session_state.get(PREFERENCES_KEY, {})


def set_trip_plan(plan: dict) -> None:
    """Update the trip plan in session state."""
    st.session_state[TRIP_PLAN_KEY] = plan


def append_chat_message(role: str, content: str) -> None:
    """Append a message to the chat history."""
    import datetime
    message = {
        "role": role,
        "content": content,
        "timestamp": datetime.datetime.now().isoformat(),
    }
    st.session_state[CHAT_HISTORY_KEY].append(message)
