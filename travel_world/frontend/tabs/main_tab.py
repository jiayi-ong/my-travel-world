"""
Trip Setup tab: the control panel for all other tabs.

Responsibilities:
    - World selection and session initialization
    - Trip parameter inputs (dates, budget, origin, destination, group size, style)
    - Live trip plan cost summary panel (always visible)
    - "Apply" button syncs preferences to backend session
"""
import streamlit as st
from travel_world.frontend import state
from travel_world.frontend.api_client import TravelWorldClient, APIError


def render(client: TravelWorldClient) -> None:
    """Render the Trip Setup tab."""
    st.header("Trip Setup")
    _render_world_selector(client)
    _render_session_panel(client)
    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        _render_origin_destination(client)
    with col2:
        _render_dates_and_budget()

    _render_group_and_style()
    _render_apply_button(client)
    st.divider()
    _render_trip_plan_summary(client)


def _render_world_selector(client: TravelWorldClient) -> None:
    """Dropdown to select which world instance to use."""
    try:
        worlds = client.list_worlds()
    except APIError as e:
        st.error(f"Could not load worlds: {e.message}")
        return

    if not worlds:
        st.info("No worlds generated yet. Run: python scripts/generate_world.py --seed 42")
        return

    options = {w["world_id"]: w for w in worlds}
    current_world = st.session_state.get(state.WORLD_ID_KEY)
    default_index = (
        list(options.keys()).index(current_world)
        if current_world in options
        else 0
    )

    selected = st.selectbox(
        "World Instance",
        options=list(options.keys()),
        index=default_index,
        format_func=lambda x: f"{x} (seed: {options[x].get('seed', '?')})",
        help="Select which generated world to explore.",
    )

    if selected != st.session_state.get(state.WORLD_ID_KEY):
        try:
            client.load_world(selected)
        except APIError:
            pass  # world may already be loaded; continue
        st.session_state[state.WORLD_ID_KEY] = selected
        st.session_state[state.SESSION_ID_KEY] = None
        state.clear_search_results()


def _render_session_panel(client: TravelWorldClient) -> None:
    """Initialize or display current session ID."""
    world_id = st.session_state.get(state.WORLD_ID_KEY)
    if not world_id:
        st.warning("Select a world first")
        return

    session_id = state.get_session_id()
    if not session_id:
        if st.button("Start Session", type="primary"):
            try:
                new_session_id = client.create_session(world_id)
                st.session_state[state.SESSION_ID_KEY] = new_session_id
                st.success(f"Session started: {new_session_id}")
                st.rerun()
            except APIError as e:
                st.error(f"Could not create session: {e.message}")
    else:
        col1, col2 = st.columns([3, 1])
        with col1:
            st.caption(f"Session active: `{session_id[:8]}...`")
        with col2:
            if st.button("New Session"):
                st.session_state[state.SESSION_ID_KEY] = None
                state.clear_search_results()
                st.rerun()


def _render_origin_destination(client: TravelWorldClient) -> None:
    """Origin city and destination city selectors (dropdown populated from active world)."""
    st.subheader("Where")
    prefs = state.get_preferences()
    world_id = st.session_state.get(state.WORLD_ID_KEY)

    # Load city list for selectbox
    cities: list[dict] = []
    if world_id:
        try:
            cities = client.list_cities(world_id)
        except APIError as e:
            st.warning(f"Could not load city list ({e.message}) — please restart the API server.")

    if cities:
        city_ids = [c["city_id"] for c in cities]
        city_labels = {c["city_id"]: c["name"] for c in cities}

        current_origin = prefs.get("origin_city_id", "")
        origin_index = city_ids.index(current_origin) if current_origin in city_ids else 0
        origin = st.selectbox(
            "Origin City",
            options=city_ids,
            index=origin_index,
            format_func=lambda x: f"{city_labels.get(x, x)} ({x})",
            key="input_origin_city_id",
        )
        if origin != prefs.get("origin_city_id", ""):
            state.update_preference("origin_city_id", origin)

        dest_list = prefs.get("destination_city_ids", [])
        current_dest = dest_list[0] if dest_list else ""
        dest_index = city_ids.index(current_dest) if current_dest in city_ids else (1 if len(city_ids) > 1 else 0)
        destination = st.selectbox(
            "Destination City",
            options=city_ids,
            index=dest_index,
            format_func=lambda x: f"{city_labels.get(x, x)} ({x})",
            key="input_destination_city_id",
        )
        if destination != current_dest:
            state.update_preference("destination_city_ids", [destination])
            state.update_preference("destination_city_id", destination)
    else:
        # Fallback to text inputs if city list unavailable
        origin = st.text_input(
            "Origin City ID",
            value=prefs.get("origin_city_id", ""),
            placeholder="e.g. city_world_42_0001",
            key="input_origin_city_id",
        )
        if origin != prefs.get("origin_city_id", ""):
            state.update_preference("origin_city_id", origin)

        dest_list = prefs.get("destination_city_ids", [])
        dest_value = dest_list[0] if dest_list else ""
        destination = st.text_input(
            "Destination City ID",
            value=dest_value,
            placeholder="e.g. city_world_42_0002",
            key="input_destination_city_id",
        )
        current_dest = dest_list[0] if dest_list else ""
        if destination != current_dest:
            state.update_preference("destination_city_ids", [destination] if destination else [])
            state.update_preference("destination_city_id", destination)


def _render_dates_and_budget() -> None:
    """Date pickers and budget input."""
    import datetime

    st.subheader("When & Budget")
    prefs = state.get_preferences()

    today = datetime.date.today()
    default_depart = prefs.get("departure_date")
    if default_depart:
        try:
            default_depart = datetime.date.fromisoformat(str(default_depart))
        except (ValueError, TypeError):
            default_depart = today + datetime.timedelta(days=14)
    else:
        default_depart = today + datetime.timedelta(days=14)

    depart = st.date_input(
        "Departure Date",
        value=default_depart,
        min_value=today,
    )
    if str(depart) != str(prefs.get("departure_date", "")):
        state.update_preference("departure_date", str(depart))

    default_return = prefs.get("return_date")
    if default_return:
        try:
            default_return = datetime.date.fromisoformat(str(default_return))
        except (ValueError, TypeError):
            default_return = depart + datetime.timedelta(days=7)
    else:
        default_return = depart + datetime.timedelta(days=7)

    ret = st.date_input(
        "Return Date",
        value=default_return,
        min_value=depart,
    )
    if str(ret) != str(prefs.get("return_date", "")):
        state.update_preference("return_date", str(ret))

    budget = st.number_input(
        "Total Budget ($)",
        min_value=0.0,
        value=float(prefs.get("budget_total") or 2000.0),
        step=100.0,
    )
    if budget != prefs.get("budget_total"):
        state.update_preference("budget_total", budget)


def _render_group_and_style() -> None:
    """Group size stepper and travel style/pace selectors."""
    prefs = state.get_preferences()

    col1, col2, col3 = st.columns(3)

    with col1:
        group_size = st.number_input(
            "Group Size",
            min_value=1,
            max_value=20,
            value=int(prefs.get("group_size", 1)),
        )
        if group_size != prefs.get("group_size"):
            state.update_preference("group_size", group_size)

    with col2:
        style_options = ["BUDGET", "COMFORT", "LUXURY"]
        current_style = prefs.get("travel_style", "COMFORT")
        style_index = (
            style_options.index(current_style)
            if current_style in style_options
            else 1
        )
        travel_style = st.selectbox("Travel Style", style_options, index=style_index)
        if travel_style != prefs.get("travel_style"):
            state.update_preference("travel_style", travel_style)

    with col3:
        pace_options = ["RELAXED", "MODERATE", "PACKED"]
        current_pace = prefs.get("pace", "MODERATE")
        pace_index = (
            pace_options.index(current_pace)
            if current_pace in pace_options
            else 1
        )
        pace = st.selectbox("Pace", pace_options, index=pace_index)
        if pace != prefs.get("pace"):
            state.update_preference("pace", pace)


def _render_apply_button(client: TravelWorldClient) -> None:
    """Sync current UI preferences to backend session."""
    if st.button("Apply Preferences", type="primary"):
        session_id = state.get_session_id()
        if not session_id:
            st.warning("Please start a session first")
            return
        try:
            client.update_preferences(session_id, state.get_preferences())
            st.success("Preferences saved!")
            state.clear_search_results()
            st.cache_data.clear()
        except APIError as e:
            st.error(f"Failed: {e.message}")


def _render_trip_plan_summary(client: TravelWorldClient) -> None:
    """Live cost summary: total spent, remaining budget, breakdown by category."""
    st.subheader("Trip Plan Summary")

    session_id = state.get_session_id()
    if not session_id:
        st.info("Start a session to see your trip plan")
        return

    try:
        summary = client.get_trip_plan_summary(session_id)
    except APIError as e:
        st.warning(f"Could not load trip plan: {e.message}")
        return
    except Exception:
        st.warning("Could not load trip plan")
        return

    total_cost = summary.get("total_cost", 0.0)
    budget_total = state.get_preferences().get("budget_total")
    budget_rem = (
        float(budget_total) - float(total_cost) if budget_total is not None else None
    )
    item_count = summary.get("item_count", len(summary.get("items", [])))

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Cost", f"${total_cost:.2f}")
    if budget_rem is not None:
        col2.metric("Budget Remaining", f"${budget_rem:.2f}", delta=None)
    else:
        col2.metric("Budget Remaining", "No budget set", delta=None)
    col3.metric("Items", item_count)

    # Category breakdown if available
    breakdown = summary.get("breakdown", {})
    if breakdown:
        st.markdown("**Breakdown by category:**")
        try:
            import pandas as pd
            breakdown_data = [
                {"Category": cat.title(), "Cost ($)": f"${amount:.2f}"}
                for cat, amount in breakdown.items()
            ]
            st.dataframe(pd.DataFrame(breakdown_data), use_container_width=True, hide_index=True)
        except ImportError:
            for cat, amount in breakdown.items():
                st.caption(f"{cat.title()}: ${amount:.2f}")
