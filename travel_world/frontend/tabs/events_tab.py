"""
Events tab: browse and book events in the destination city.
"""
import datetime
import streamlit as st
from travel_world.frontend import state
from travel_world.frontend.api_client import TravelWorldClient, APIError
from travel_world.frontend.components.back_to_top import render_back_to_top

_EVENT_CATEGORIES = [
    "MUSIC", "FOOD", "CULTURE", "SPORTS", "FESTIVAL",
    "EXHIBITION", "THEATER", "COMEDY", "MARKET", "ATTRACTION",
]


def _render_city_selector(client, prefs: dict) -> str:
    """City selector local to events tab."""
    from travel_world.frontend import state as _state
    world_id = st.session_state.get(_state.WORLD_ID_KEY)
    cities: list[dict] = []
    if world_id:
        try:
            cities = client.list_cities(world_id)
        except Exception:
            pass

    dest_list = prefs.get("destination_city_ids", [])
    default_city = (
        st.session_state.get("tworld_event_city_local")
        or (dest_list[0] if dest_list else prefs.get("destination_city_id", ""))
    )

    if cities:
        city_ids = [c["city_id"] for c in cities]
        city_labels = {c["city_id"]: c["name"] for c in cities}
        idx = city_ids.index(default_city) if default_city in city_ids else 0
        city_id = st.selectbox(
            "Destination City",
            city_ids,
            index=idx,
            format_func=lambda x: city_labels.get(x, x),
            key="event_tab_city",
        )
    else:
        city_id = st.text_input(
            "Destination City ID",
            value=st.session_state.get("tworld_event_city_local", default_city),
            key="event_tab_city",
        )

    if not city_id:
        st.info("Please select a destination city.")
        return ""

    st.session_state["tworld_event_city_local"] = city_id
    return city_id


def render(client: TravelWorldClient) -> None:
    """Render the Events tab."""
    st.header("Events")

    prefs = state.get_preferences()
    city_id = _render_city_selector(client, prefs)
    if not city_id:
        return

    _render_filters(prefs)

    view_mode = st.radio("View", ["List", "Calendar"], horizontal=True)

    if view_mode == "List":
        _render_event_list(client, prefs, city_id)
    else:
        _render_calendar_view(client, prefs, city_id)


def _render_filters(prefs: dict) -> None:
    """Category, price, and date-range filters inside a form so changes commit on submit."""
    # Initialise session state defaults
    if "tworld_event_filter_categories" not in st.session_state:
        st.session_state["tworld_event_filter_categories"] = []
    if "tworld_event_filter_any_price" not in st.session_state:
        st.session_state["tworld_event_filter_any_price"] = True
    if "tworld_event_filter_max_price" not in st.session_state:
        st.session_state["tworld_event_filter_max_price"] = 200.0
    # Default date range from trip prefs
    _today = datetime.date.today()
    _dep = prefs.get("departure_date")
    _ret = prefs.get("return_date")
    try:
        _default_start = datetime.date.fromisoformat(str(_dep)) if _dep else _today
    except (ValueError, TypeError):
        _default_start = _today
    try:
        _default_end = datetime.date.fromisoformat(str(_ret)) if _ret else _today + datetime.timedelta(days=14)
    except (ValueError, TypeError):
        _default_end = _today + datetime.timedelta(days=14)

    if "tworld_event_filter_start_date" not in st.session_state:
        st.session_state["tworld_event_filter_start_date"] = _default_start
    if "tworld_event_filter_end_date" not in st.session_state:
        st.session_state["tworld_event_filter_end_date"] = _default_end

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

        date_col1, date_col2 = st.columns(2)
        _start_val = st.session_state["tworld_event_filter_start_date"]
        _end_val = st.session_state["tworld_event_filter_end_date"]
        if not isinstance(_start_val, datetime.date):
            try:
                _start_val = datetime.date.fromisoformat(str(_start_val))
            except (ValueError, TypeError):
                _start_val = _default_start
        if not isinstance(_end_val, datetime.date):
            try:
                _end_val = datetime.date.fromisoformat(str(_end_val))
            except (ValueError, TypeError):
                _end_val = _default_end

        filter_start = date_col1.date_input(
            "From date",
            value=_start_val,
            key="event_filter_start_input",
        )
        filter_end = date_col2.date_input(
            "To date",
            value=_end_val,
            key="event_filter_end_input",
        )

        if st.form_submit_button("Apply Filters"):
            st.session_state["tworld_event_filter_categories"] = categories
            st.session_state["tworld_event_filter_any_price"] = any_price
            st.session_state["tworld_event_filter_max_price"] = max_price
            st.session_state["tworld_event_filter_start_date"] = filter_start
            st.session_state["tworld_event_filter_end_date"] = filter_end


def _fetch_events(client: TravelWorldClient, prefs: dict, city_id: str) -> list[dict] | None:
    """Fetch events from API, applying single-category filter server-side."""
    _sd = st.session_state.get("tworld_event_filter_start_date")
    _ed = st.session_state.get("tworld_event_filter_end_date")
    start_date = str(_sd) if _sd else None
    end_date = str(_ed) if _ed else None

    categories = st.session_state.get("tworld_event_filter_categories", [])
    category_param = categories[0].lower() if len(categories) == 1 else None

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

    # Client-side multi-category filter (API returns lowercase, UI uses uppercase)
    if len(categories) > 1:
        cats_lower = {c.lower() for c in categories}
        events = [e for e in events if e.get("category", "").lower() in cats_lower]

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

    # Collect booked event IDs with counts for badge display
    from collections import Counter
    booked_event_counts: Counter = Counter()
    _sid = state.get_session_id()
    if _sid:
        try:
            _plan = client.get_trip_plan(_sid)
            for it in _plan.get("items", []):
                if it.get("item_type") == "event":
                    booked_event_counts[it.get("ref_id", "")] += 1
        except Exception:
            pass

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
                    st.write(description)

            with col2:
                _sdt = event.get("start_datetime") or "N/A"
                _edt = event.get("end_datetime") or ""
                event_date = _sdt[:10]
                start_time = _sdt[11:16] if len(_sdt) >= 16 else ""
                end_time = _edt[11:16] if len(_edt) >= 16 else ""
                ticket_price = float(event.get("base_ticket_price", event.get("ticket_price", 0.0)))
                tickets_remaining = event.get("tickets_remaining")
                is_all_day = event.get("is_all_day_entry", False)
                if is_all_day and start_time and end_time:
                    time_str = f"  🕐 {start_time}–{end_time} (all-day entry)"
                elif start_time and end_time:
                    time_str = f"  🕐 {start_time}–{end_time}"
                elif start_time:
                    time_str = f"  🕐 {start_time}"
                else:
                    time_str = ""
                st.markdown(f"📅 **{event_date}**{time_str}")
                if ticket_price > 0:
                    st.markdown(f"🎟️ **${ticket_price:.2f}** / ticket")
                else:
                    st.markdown("🆓 **Free entry**")
                if tickets_remaining is not None:
                    if tickets_remaining <= 10:
                        st.warning(f"Only {tickets_remaining} tickets left!")
                    else:
                        st.caption(f"{tickets_remaining} tickets available")

            with col3:
                event_id = event.get("event_id", "unknown")
                cnt = booked_event_counts.get(event_id, 0)
                requires_booking = event.get("requires_booking", True)
                if cnt > 0:
                    st.info(f"In plan ×{cnt}")
                if requires_booking:
                    if st.button(
                        "Add again" if cnt > 0 else "Add to Plan",
                        key=f"book_event_{event_id}",
                        type="primary",
                    ):
                        _book_event(client, event)
                else:
                    st.caption("🆓 Free entry")
                    if st.button(
                        "Add to Plan" if cnt == 0 else "Add again",
                        key=f"book_event_{event_id}",
                    ):
                        _add_free_attraction(client, event)

            reviews = event.get("reviews", [])
            if reviews:
                with st.expander(f"Reviews ({len(reviews)})"):
                    for rv in reviews:
                        stars = "⭐" * max(1, round(rv.get("rating", 3)))
                        st.markdown(f"{stars} **{rv.get('reviewer_id', '')}** · {rv.get('date', '')}")
                        st.write(rv.get("text", ""))

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

                _sdt_cal = event.get("start_datetime") or ""
                _edt_cal = event.get("end_datetime") or ""
                start_time_cal = _sdt_cal[11:16] if len(_sdt_cal) >= 16 else ""
                end_time_cal = _edt_cal[11:16] if len(_edt_cal) >= 16 else ""
                is_all_day_cal = event.get("is_all_day_entry", False)
                if is_all_day_cal and start_time_cal and end_time_cal:
                    time_label = f"  🕐 {start_time_cal}–{end_time_cal} (all-day)"
                elif start_time_cal and end_time_cal:
                    time_label = f"  🕐 {start_time_cal}–{end_time_cal}"
                elif start_time_cal:
                    time_label = f"  🕐 {start_time_cal}"
                else:
                    time_label = ""
                requires_booking_cal = event.get("requires_booking", True)
                price_label = f"🎟️ ${ticket_price:.2f}" if ticket_price > 0 else "🆓 Free"
                col1, col2 = st.columns([4, 1])
                col1.markdown(
                    f"**{name}**{time_label} — {venue}  |  🏷️ {category}  |  {price_label}"
                )
                if requires_booking_cal:
                    if col2.button("Book", key=f"cal_book_{event_id}"):
                        _book_event(client, event)
                else:
                    if col2.button("Add", key=f"cal_book_{event_id}"):
                        _add_free_attraction(client, event)


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
                    "venue": event.get("venue_name", event.get("venue")),
                    "category": event.get("category"),
                    "city_id": event.get("city_id"),
                    "description": event.get("description", ""),
                    "start_datetime": event.get("start_datetime"),
                    "end_datetime": event.get("end_datetime"),
                    "is_all_day_entry": event.get("is_all_day_entry", False),
                    "requires_booking": event.get("requires_booking", True),
                },
            },
        )
        st.success(f"Tickets booked for {event.get('name', 'event')}!")
        st.cache_data.clear()
        st.rerun()
    except APIError as e:
        st.error(f"Booking failed: {e.message}")


def _add_free_attraction(client: TravelWorldClient, event: dict) -> None:
    """Add a free-entry attraction to the trip plan (no ticket booking needed)."""
    session_id = state.get_session_id()
    if not session_id:
        st.warning("Start a session in Trip Setup first.")
        return

    try:
        client.add_trip_item(
            session_id=session_id,
            item={
                "item_type": "event",
                "ref_id": event.get("event_id", "unknown"),
                "date": (event.get("start_datetime") or "")[:10],
                "cost": 0.0,
                "metadata": {
                    "name": event.get("name"),
                    "venue": event.get("venue_name", event.get("venue")),
                    "category": event.get("category"),
                    "city_id": event.get("city_id"),
                    "description": event.get("description", ""),
                    "start_datetime": event.get("start_datetime"),
                    "end_datetime": event.get("end_datetime"),
                    "is_all_day_entry": event.get("is_all_day_entry", True),
                    "requires_booking": False,
                },
            },
        )
        st.success(f"Added {event.get('name', 'attraction')} to your plan!")
        st.cache_data.clear()
        st.rerun()
    except APIError as e:
        st.error(f"Could not add to plan: {e.message}")
