"""
Map tab: Folium-based multi-modal route visualization.

Shows color-coded polylines per transport mode with tooltips showing
duration, cost, and congestion status.
"""
import streamlit as st
from travel_world.frontend import state
from travel_world.frontend.api_client import TravelWorldClient, APIError
from travel_world.frontend.components.map_builder import build_route_map
from travel_world.frontend.components.route_panel import render_route_comparison


def render(client: TravelWorldClient) -> None:
    """Render the Map tab."""
    st.header("Route Planner")

    col1, col2 = st.columns([1, 2])

    with col1:
        _render_route_controls(client)

    with col2:
        _render_map()

    _render_comparison_table()


def _render_route_controls(client: TravelWorldClient) -> None:
    """Origin, destination, departure time inputs, and compare button."""
    import datetime

    st.subheader("Route Options")

    prefs = state.get_preferences()
    world_id = st.session_state.get(state.WORLD_ID_KEY)

    # Load city list for dropdowns
    cities: list[dict] = []
    if world_id:
        try:
            cities = client.list_cities(world_id)
        except APIError:
            pass

    if cities:
        city_ids = [c["city_id"] for c in cities]
        city_labels = {c["city_id"]: c["name"] for c in cities}

        saved_origin = st.session_state.get(state.MAP_ORIGIN_KEY, prefs.get("origin_city_id", ""))
        origin_index = city_ids.index(saved_origin) if saved_origin in city_ids else 0
        origin_id = st.selectbox(
            "Origin City",
            options=city_ids,
            index=origin_index,
            format_func=lambda x: f"{city_labels.get(x, x)} ({x})",
            key="map_origin_id",
        )

        saved_dest = st.session_state.get(
            state.MAP_DEST_KEY,
            (prefs.get("destination_city_ids") or [prefs.get("destination_city_id", "")])[0],
        )
        dest_index = city_ids.index(saved_dest) if saved_dest in city_ids else (1 if len(city_ids) > 1 else 0)
        dest_id = st.selectbox(
            "Destination City",
            options=city_ids,
            index=dest_index,
            format_func=lambda x: f"{city_labels.get(x, x)} ({x})",
            key="map_dest_id",
        )
    else:
        origin_id = st.text_input(
            "Origin Location ID",
            key="map_origin_id",
            value=st.session_state.get(state.MAP_ORIGIN_KEY, prefs.get("origin_city_id", "")),
            placeholder="e.g. hub_demo_0000",
        )
        dest_id = st.text_input(
            "Destination Location ID",
            key="map_dest_id",
            value=st.session_state.get(
                state.MAP_DEST_KEY,
                (prefs.get("destination_city_ids") or [prefs.get("destination_city_id", "")])[0],
            ),
            placeholder="e.g. hub_demo_0002",
        )

    st.session_state[state.MAP_ORIGIN_KEY] = origin_id
    st.session_state[state.MAP_DEST_KEY] = dest_id

    today = datetime.date.today()
    departure_date = st.date_input("Departure Date", value=today, min_value=today)
    departure_time = st.time_input("Departure Time", value=datetime.time(9, 0))

    departure_dt_str = datetime.datetime.combine(departure_date, departure_time).isoformat()

    optimize_for = st.radio(
        "Optimize for", ["Time", "Cost", "Balanced"], horizontal=True
    )
    # optimize_for is captured for display/future use; routing API receives all modes

    if st.button("Compare Routes", type="primary"):
        if not origin_id or not dest_id:
            st.warning("Please enter both origin and destination location IDs.")
            return
        with st.spinner("Fetching route options..."):
            try:
                results = client.compare_routes(
                    origin_location_id=origin_id,
                    destination_location_id=dest_id,
                    departure_datetime=departure_dt_str,
                )
                st.session_state[state.ROUTE_RESULTS_KEY] = results
            except APIError as e:
                st.error(f"Route comparison failed: {e.message}")


def _render_map() -> None:
    """Render the Folium map with route polylines."""
    try:
        from streamlit_folium import st_folium
    except ImportError:
        st.error(
            "streamlit-folium is not installed. "
            "Install it with: pip install streamlit-folium"
        )
        return

    results = st.session_state.get(state.ROUTE_RESULTS_KEY)

    if results:
        routes = results.get("routes", []) if isinstance(results, dict) else []
    else:
        routes = []

    m = build_route_map(routes)
    st_folium(m, width=None, height=450, use_container_width=True)


def _render_comparison_table() -> None:
    """Render side-by-side route comparison table below the map."""
    results = st.session_state.get(state.ROUTE_RESULTS_KEY)
    if results:
        routes = results.get("routes", []) if isinstance(results, dict) else []
        if routes:
            render_route_comparison(routes)
        else:
            st.info("No route options returned for this origin/destination pair.")
    else:
        st.info("Use the controls above to compare routes between two locations.")
