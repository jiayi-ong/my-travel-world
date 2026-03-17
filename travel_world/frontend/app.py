"""
Streamlit application entry point.

Run with:
    streamlit run travel_world/frontend/app.py

Tab layout:
    Trip Setup | Flights | Hotels | Events | Map | AI Assistant
"""
import streamlit as st
from travel_world.frontend.state import init_state
from travel_world.frontend.api_client import TravelWorldClient
from travel_world.frontend.tabs import main_tab, flights_tab, hotels_tab, events_tab, map_tab, llm_tab

def main():
    """
    Render the full multi-tab Streamlit application.

    Initialization (runs on every Streamlit re-render):
        1. Configure page (title, layout, icon).
        2. Initialize session state defaults.
        3. Instantiate API client (cached in session state to reuse connection).
        4. Render tab router.
    """
    st.set_page_config(page_title="Travel World", layout="wide", page_icon="✈️")
    init_state()

    if "tworld_api_client" not in st.session_state:
        st.session_state["tworld_api_client"] = TravelWorldClient()

    client = st.session_state["tworld_api_client"]

    st.title("Travel World Simulator")

    tabs = st.tabs(["Trip Setup", "Flights", "Hotels", "Events", "Map", "AI Assistant"])

    with tabs[0]:
        main_tab.render(client)
    with tabs[1]:
        flights_tab.render(client)
    with tabs[2]:
        hotels_tab.render(client)
    with tabs[3]:
        events_tab.render(client)
    with tabs[4]:
        map_tab.render(client)
    with tabs[5]:
        llm_tab.render(client)

if __name__ == "__main__":
    main()
