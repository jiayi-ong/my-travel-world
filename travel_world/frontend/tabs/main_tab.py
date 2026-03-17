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

    _render_origin_destination(client)
    _render_city_details(client)
    st.divider()
    _render_dates_and_budget()
    _render_group_and_style()
    _render_apply_button(client)


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


def _load_cities(client: TravelWorldClient) -> list[dict]:
    """Load city list for the active world; returns [] on failure."""
    world_id = st.session_state.get(state.WORLD_ID_KEY)
    if not world_id:
        return []
    try:
        return client.list_cities(world_id)
    except APIError as e:
        st.warning(f"Could not load city list ({e.message}) — please restart the API server.")
        return []


def _render_origin_destination(client: TravelWorldClient) -> None:
    """Origin and destination selectors, side by side in two columns."""
    st.subheader("Where")
    prefs  = state.get_preferences()
    cities = _load_cities(client)

    col_from, col_to = st.columns(2)

    if cities:
        city_ids   = [c["city_id"] for c in cities]
        city_labels = {c["city_id"]: c["name"] for c in cities}

        with col_from:
            current_origin = prefs.get("origin_city_id", "")
            origin_index   = city_ids.index(current_origin) if current_origin in city_ids else 0
            origin = st.selectbox(
                "Flying from",
                options=city_ids,
                index=origin_index,
                format_func=lambda x: city_labels.get(x, x),
                key="input_origin_city_id",
            )
            if origin != prefs.get("origin_city_id", ""):
                state.update_preference("origin_city_id", origin)

        with col_to:
            dest_list    = prefs.get("destination_city_ids", [])
            current_dest = dest_list[0] if dest_list else ""
            dest_index   = city_ids.index(current_dest) if current_dest in city_ids else (1 if len(city_ids) > 1 else 0)
            destination  = st.selectbox(
                "Flying to",
                options=city_ids,
                index=dest_index,
                format_func=lambda x: city_labels.get(x, x),
                key="input_destination_city_id",
            )
            if destination != current_dest:
                state.update_preference("destination_city_ids", [destination])
                state.update_preference("destination_city_id", destination)
    else:
        with col_from:
            origin = st.text_input(
                "Flying from (City ID)",
                value=prefs.get("origin_city_id", ""),
                placeholder="e.g. city_world_42_0001",
                key="input_origin_city_id",
            )
            if origin != prefs.get("origin_city_id", ""):
                state.update_preference("origin_city_id", origin)
        with col_to:
            dest_list    = prefs.get("destination_city_ids", [])
            dest_value   = dest_list[0] if dest_list else ""
            destination  = st.text_input(
                "Flying to (City ID)",
                value=dest_value,
                placeholder="e.g. city_world_42_0002",
                key="input_destination_city_id",
            )
            current_dest = dest_list[0] if dest_list else ""
            if destination != current_dest:
                state.update_preference("destination_city_ids", [destination] if destination else [])
                state.update_preference("destination_city_id", destination)


def _render_city_details(client: TravelWorldClient) -> None:
    """Independent city explorer — vibe summary + security advisory for any selected city."""
    st.subheader("City Details")
    cities = _load_cities(client)
    if not cities:
        st.caption("No city data available.")
        return

    city_ids    = [c["city_id"] for c in cities]
    city_labels = {c["city_id"]: c["name"] for c in cities}
    city_by_id  = {c["city_id"]: c for c in cities}

    # Default to destination city if one is set
    prefs       = state.get_preferences()
    dest_list   = prefs.get("destination_city_ids", [])
    default_cid = dest_list[0] if dest_list and dest_list[0] in city_ids else city_ids[0]
    default_idx = city_ids.index(default_cid)

    selected_id = st.selectbox(
        "Explore city",
        options=city_ids,
        index=default_idx,
        format_func=lambda x: city_labels.get(x, x),
        key="city_detail_selector",
    )

    city = city_by_id.get(selected_id, {})
    safety_score = city.get("safety_score", 1.0)
    vibe         = city.get("vibe_summary", "")
    advisory     = city.get("travel_advisory", "")
    dominant_cuisines = city.get("dominant_cuisines", [])
    dominant_events   = city.get("dominant_event_categories", [])

    if vibe:
        st.write(vibe)

    col_c, col_e = st.columns(2)
    if dominant_cuisines:
        col_c.caption(f"🍴 **Food scene:** {', '.join(dominant_cuisines)}")
    if dominant_events:
        col_e.caption(f"🎭 **Events:** {', '.join(e.title() for e in dominant_events)}")

    if advisory:
        if safety_score >= 0.75:
            st.info(f"🟢 **Travel Advisory:** {advisory}")
        elif safety_score >= 0.55:
            st.warning(f"🟡 **Travel Advisory:** {advisory}")
        elif safety_score >= 0.35:
            st.warning(f"🟠 **Travel Advisory:** {advisory}")
        else:
            st.error(f"🔴 **Travel Advisory:** {advisory}")


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


