"""
Events tab: browse and book events in the destination city.
"""
import streamlit as st
from travel_world.frontend import state
from travel_world.frontend.api_client import TravelWorldClient, APIError
from travel_world.frontend.components.back_to_top import render_back_to_top

_EVENT_CATEGORIES = [
    "MUSIC", "FOOD", "CULTURE", "SPORTS", "FESTIVAL",
    "EXHIBITION", "THEATER", "COMEDY", "MARKET",
]


def render(client: TravelWorldClient) -> None:
    """Render the Events tab."""
    st.header("Events")

    prefs = state.get_preferences()
    dest_list = prefs.get("destination_city_ids", [])
    city_id = dest_list[0] if dest_list else prefs.get("destination_city_id", "")

    if not city_id:
        st.info("Please set a destination city in the Trip Setup tab to browse events.")
        return

    _render_filters()

    view_mode = st.radio("View", ["List", "Calendar"], horizontal=True)

    if view_mode == "List":
        _render_event_list(client, prefs, city_id)
    else:
        _render_calendar_view(client, prefs, city_id)


def _render_filters() -> None:
    """Category, price, and date-range filters inside a form so changes commit on submit."""
    # Initialise session state defaults
    if "tworld_event_filter_categories" not in st.session_state:
        st.session_state["tworld_event_filter_categories"] = []
    if "tworld_event_filter_any_price" not in st.session_state:
        st.session_state["tworld_event_filter_any_price"] = True
    if "tworld_event_filter_max_price" not in st.session_state:
        st.session_state["tworld_event_filter_max_price"] = 200.0
    if "tworld_event_filter_to_dates" not in st.session_state:
        st.session_state["tworld_event_filter_to_dates"] = False

    with st.form("event_filters_form"):
        col1, col2, col3 = st.columns([3, 1, 1])

        with col1:
            categories = st.multiselect(
                "Categories",
                options=_EVENT_CATEGORIES,
                default=st.session_state["tworld_event_filter_categories"],
            )

        with col2:
            any_price = st.checkbox(
                "Any price",
                value=st.session_state["tworld_event_filter_any_price"],
            )

        with col3:
            max_price = st.number_input(
                "Max price ($)",
                min_value=0.0,
                value=st.session_state["tworld_event_filter_max_price"],
                step=10.0,
                disabled=any_price,
            )

        filter_to_dates = st.checkbox(
            "Show trip dates only",
            value=st.session_state["tworld_event_filter_to_dates"],
            help="When checked, only events within your departure–return window are shown.",
        )

        if st.form_submit_button("Apply Filters"):
            st.session_state["tworld_event_filter_categories"] = categories
            st.session_state["tworld_event_filter_any_price"] = any_price
            st.session_state["tworld_event_filter_max_price"] = max_price
            st.session_state["tworld_event_filter_to_dates"] = filter_to_dates


def _fetch_events(client: TravelWorldClient, prefs: dict, city_id: str) -> list[dict] | None:
    """Fetch events from API, applying single-category filter server-side."""
    filter_to_dates = st.session_state.get("tworld_event_filter_to_dates", False)
    start_date = (str(prefs.get("departure_date", "")) or None) if filter_to_dates else None
    end_date = (str(prefs.get("return_date", "")) or None) if filter_to_dates else None

    categories = st.session_state.get("tworld_event_filter_categories", [])
    category_param = categories[0] if len(categories) == 1 else None

    try:
        events = client.search_events(
            city_id=city_id,
            start_date=start_date,
            end_date=end_date,
            category=category_param,
            session_id=state.get_session_id(),
        )
    except APIError as e:
        st.error(f"Could not load events: {e.message}")
        return None

    # Client-side multi-category filter
    if len(categories) > 1:
        events = [e for e in events if e.get("category", "") in categories]

    # Client-side price filter — skipped when "Any price" is checked
    any_price = st.session_state.get("tworld_event_filter_any_price", True)
    if not any_price:
        max_price = st.session_state.get("tworld_event_filter_max_price", 0.0)
        if max_price and max_price > 0:
            events = [e for e in events if float(e.get("base_ticket_price", 0)) <= max_price]

    return events


def _render_event_list(client: TravelWorldClient, prefs: dict, city_id: str) -> None:
    """List view of all events in the destination city."""
    events = _fetch_events(client, prefs, city_id)
    if events is None:
        return

    if not events:
        st.info("No events match the current filters.")
        return

    st.caption(f"{len(events)} event(s) found")

    sort_by = st.selectbox(
        "Sort by",
        ["Date ↑", "Date ↓", "Price ↑", "Price ↓"],
        key="event_sort",
    )

    if sort_by == "Date ↑":
        events = sorted(events, key=lambda e: e.get("start_datetime") or "")
    elif sort_by == "Date ↓":
        events = sorted(events, key=lambda e: e.get("start_datetime") or "", reverse=True)
    elif sort_by == "Price ↑":
        events = sorted(events, key=lambda e: float(e.get("base_ticket_price") or 0))
    else:  # "Price ↓"
        events = sorted(events, key=lambda e: float(e.get("base_ticket_price") or 0), reverse=True)

    for event in events:
        with st.container(border=True):
            col1, col2, col3 = st.columns([3, 2, 1])

            with col1:
                name = event.get("name", "Unknown Event")
                category = event.get("category", "")
                venue = event.get("venue_name", event.get("venue_id", ""))
                description = event.get("description", "")
                avg_rating = event.get("average_rating")
                rating_str = f"  |  ⭐ {avg_rating:.1f}" if avg_rating is not None else ""
                st.markdown(f"**{name}**")
                st.caption(f"🏷️ {category}  |  📍 {venue}{rating_str}")
                if description:
                    st.caption(description)

            with col2:
                event_date = (event.get("start_datetime") or "N/A")[:10]
                ticket_price = float(event.get("base_ticket_price", event.get("ticket_price", 0.0)))
                tickets_remaining = event.get("tickets_remaining")
                st.markdown(f"📅 **{event_date}**")
                st.markdown(f"🎟️ **${ticket_price:.2f}** / ticket")
                if tickets_remaining is not None:
                    if tickets_remaining <= 10:
                        st.warning(f"Only {tickets_remaining} tickets left!")
                    else:
                        st.caption(f"{tickets_remaining} tickets available")

            with col3:
                event_id = event.get("event_id", "unknown")
                if st.button("Add to Plan", key=f"book_event_{event_id}", type="primary"):
                    _book_event(client, event)

    render_back_to_top()


def _render_calendar_view(client: TravelWorldClient, prefs: dict, city_id: str) -> None:
    """Calendar view grouping events by date."""
    events = _fetch_events(client, prefs, city_id)
    if events is None:
        return

    if not events:
        st.warning("No events found for this period.")
        return

    # Group events by date (API returns start_datetime)
    events_by_date: dict[str, list[dict]] = {}
    for event in events:
        date_key = (event.get("start_datetime") or "Unknown")[:10]
        events_by_date.setdefault(date_key, []).append(event)

    st.markdown("### Calendar View")

    for date_str in sorted(events_by_date.keys()):
        day_events = events_by_date[date_str]
        with st.expander(f"📅 {date_str}  —  {len(day_events)} event(s)", expanded=False):
            for event in day_events:
                name = event.get("name", "Unknown Event")
                venue = event.get("venue_name", event.get("venue_id", ""))
                category = event.get("category", "")
                ticket_price = float(event.get("base_ticket_price", event.get("ticket_price", 0.0)))
                event_id = event.get("event_id", "unknown")

                col1, col2 = st.columns([4, 1])
                col1.markdown(
                    f"**{name}** — {venue}  |  🏷️ {category}  |  🎟️ ${ticket_price:.2f}"
                )
                if col2.button("Book", key=f"cal_book_{event_id}"):
                    _book_event(client, event)


def _book_event(client: TravelWorldClient, event: dict) -> None:
    """Book a single ticket for an event and add to trip plan."""
    session_id = state.get_session_id()
    if not session_id:
        st.warning("Start a session in Trip Setup first.")
        return

    event_id = event.get("event_id", "unknown")
    try:
        client.book_event_ticket(
            event_id=event_id,
            quantity=1,
            session_id=session_id,
        )
        # Also add to the trip plan
        client.add_trip_item(
            session_id=session_id,
            item={
                "item_type": "event",
                "ref_id": event_id,
                "date": (event.get("start_datetime") or "")[:10],
                "cost": float(event.get("base_ticket_price", event.get("ticket_price", 0.0))),
                "metadata": {
                    "name": event.get("name"),
                    "venue": event.get("venue"),
                    "category": event.get("category"),
                },
            },
        )
        st.success(f"Tickets booked for {event.get('name', 'event')}!")
        st.cache_data.clear()
        st.rerun()
    except APIError as e:
        st.error(f"Booking failed: {e.message}")
