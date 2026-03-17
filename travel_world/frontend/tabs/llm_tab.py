"""
AI Assistant tab: LLM chat interface.

This tab provides the UI surface for an external LLM travel planner project.
No LLM logic lives here — just the chat display, message input, and
session context export.

The external LLM project connects by:
    1. Reading the session_id displayed in this tab (or from the URL parameter).
    2. Calling GET /session/{session_id} to bootstrap from user preferences.
    3. Calling POST /session/{session_id}/chat_message to post assistant replies.
    4. This tab polls GET /session/{session_id}/llm_status to show connection status.
"""
import streamlit as st
from travel_world.frontend import state
from travel_world.frontend.api_client import TravelWorldClient, APIError


def render(client: TravelWorldClient) -> None:
    """Render the AI Assistant tab."""
    st.header("AI Travel Assistant")

    session_id = state.get_session_id()
    if not session_id:
        st.info("Start a session in Trip Setup to use the AI Assistant.")
        return

    _render_connection_status(client, session_id)
    _render_session_context_export(session_id)
    st.divider()
    _render_chat_history()
    _render_message_input(client, session_id)


def _render_connection_status(client: TravelWorldClient, session_id: str) -> None:
    """Poll and display LLM connection status indicator."""
    try:
        status = client.poll_llm_status(session_id)
        llm_connected = status.get("llm_connected", False)
        if llm_connected:
            last_active = status.get("last_message_at", "")
            msg = "LLM Agent Connected"
            if last_active:
                msg += f" (last active: {last_active})"
            st.success(f"🤖 {msg}")
        else:
            st.warning(
                "🤖 LLM Agent Not Connected — waiting for an agent to join this session."
            )
    except APIError as e:
        st.warning(f"Could not check LLM status: {e.message}")


def _render_session_context_export(session_id: str) -> None:
    """Display session ID and bootstrap URL for the LLM agent."""
    with st.expander("Session Context (share with your LLM agent)", expanded=False):
        st.caption("Session ID:")
        st.code(session_id, language=None)
        st.caption("Bootstrap URL:")
        context_url = f"http://localhost:8000/session/{session_id}"
        st.code(context_url, language=None)
        st.caption(
            "Your LLM agent can call this URL to read the current session state "
            "(preferences, trip plan, chat history) before responding."
        )


def _render_chat_history() -> None:
    """Display all messages in the chat history."""
    history = st.session_state.get(state.CHAT_HISTORY_KEY, [])

    if not history:
        st.caption("No messages yet. Start the conversation below.")
        return

    for message in history:
        role = message.get("role", "user")
        content = message.get("content", "")
        timestamp = message.get("timestamp", "")
        with st.chat_message(role):
            st.markdown(content)
            if timestamp:
                st.caption(timestamp)


def _render_message_input(client: TravelWorldClient, session_id: str) -> None:
    """User message input and send button."""
    if prompt := st.chat_input("Ask your travel assistant..."):
        state.append_chat_message("user", prompt)
        try:
            client.post_chat_message(session_id, "user", prompt)
        except APIError as e:
            st.error(f"Could not send message: {e.message}")
        st.rerun()
