"""
Flights tab: search and select flights.

Has its own origin/destination city selectors (independent of Trip Setup)
to support multi-leg trip planning: search A→B, then switch to B→C.
Departure date uses a calendar picker; results can be filtered by cabin
class, direct/connecting, and arrive-by time.
"""
import datetime
import streamlit as st
from travel_world.frontend import state
from travel_world.frontend.api_client import TravelWorldClient, APIError
from travel_world.frontend.components.flight_card import render_flight_card
from travel_world.frontend.components.back_to_top import render_back_to_top


def render(client: TravelWorldClient) -> None:
    """Render the Flights tab."""
    st.header("Flights")

    origin, destination, city_labels = _render_city_selectors(client)

    if not origin or not destination:
        st.info("Select origin and destination cities above.")
        return

    _render_search_form(client, origin, destination)
    _render_results(client, city_labels)


def _render_city_selectors(client: TravelWorldClient) -> tuple[str, str, dict]:
    """
    City From/To selectors, local to this tab.

    Defaults to the global Trip Setup preferences but can be changed
    independently — useful for building multi-leg trips (A→B then B→C).
    """
    prefs = state.get_preferences()
    world_id = st.session_state.get(state.WORLD_ID_KEY)

    cities: list[dict] = []
    if world_id:
        try:
            cities = client.list_cities(world_id)
        except Exception:
            pass

    col1, col2 = st.columns(2)
    city_labels: dict[str, str] = {}

    if cities:
        city_ids = [c["city_id"] for c in cities]
        city_labels = {c["city_id"]: c["name"] for c in cities}

        dest_list = prefs.get("destination_city_ids", [])
        default_origin = (
            st.session_state.get("tworld_flight_origin_local")
            or prefs.get("origin_city_id", city_ids[0] if city_ids else "")
        )
        default_dest = (
            st.session_state.get("tworld_flight_dest_local")
            or (dest_list[0] if dest_list else prefs.get("destination_city_id", ""))
        )

        origin_idx = city_ids.index(default_origin) if default_origin in city_ids else 0
        dest_idx = (
            city_ids.index(default_dest) if default_dest in city_ids
            else (1 if len(city_ids) > 1 else 0)
        )

        origin = col1.selectbox(
            "From",
            city_ids,
            index=origin_idx,
            format_func=lambda x: city_labels.get(x, x),
            key="flight_tab_origin",
        )
        destination = col2.selectbox(
            "To",
            city_ids,
            index=dest_idx,
            format_func=lambda x: city_labels.get(x, x),
            key="flight_tab_dest",
        )
    else:
        dest_list = prefs.get("destination_city_ids", [])
        default_origin = prefs.get("origin_city_id", "")
        default_dest = dest_list[0] if dest_list else prefs.get("destination_city_id", "")

        origin = col1.text_input(
            "From (City ID)",
            value=st.session_state.get("tworld_flight_origin_local", default_origin),
            key="flight_tab_origin",
        )
        destination = col2.text_input(
            "To (City ID)",
            value=st.session_state.get("tworld_flight_dest_local", default_dest),
            key="flight_tab_dest",
        )

    st.session_state["tworld_flight_origin_local"] = origin
    st.session_state["tworld_flight_dest_local"] = destination
    return origin, destination, city_labels


def _render_search_form(
    client: TravelWorldClient,
    origin: str,
    destination: str,
) -> None:
    """Calendar date picker + passengers form; triggers search on submit."""
    prefs = state.get_preferences()

    default_date = prefs.get("departure_date")
    if default_date:
        try:
            default_date = datetime.date.fromisoformat(str(default_date))
        except (ValueError, TypeError):
            default_date = datetime.date.today() + datetime.timedelta(days=14)
    else:
        default_date = datetime.date.today() + datetime.timedelta(days=14)

    with st.form("flight_search_form"):
        col1, col2, col3 = st.columns(3)
        passengers = col1.number_input(
            "Passengers", min_value=1, max_value=9,
            value=int(prefs.get("group_size", 1)),
        )
        departure_date = col2.date_input(
            "Departure Date",
            value=default_date,
            min_value=datetime.date.today(),
        )
        submitted = col3.form_submit_button(
            "Search Flights", type="primary", use_container_width=True
        )

    # Auto-search once when tab loads with no cached results
    auto_search = (
        st.session_state.get(state.FLIGHT_RESULTS_KEY) is None and not submitted
    )

    if submitted or auto_search:
        try:
            with st.spinner("Searching flights..."):
                results = client.search_flights(
                    origin_city_id=origin,
                    destination_city_id=destination,
                    departure_date=str(departure_date),
                    passengers=passengers,
                    cabin_class=None,
                    session_id=state.get_session_id(),
                )
            st.session_state[state.FLIGHT_RESULTS_KEY] = results
        except APIError as e:
            st.error(f"Flight search failed: {e.message}")
            return


def _render_results(client: TravelWorldClient, city_labels: dict) -> None:
    """Render flight result cards with client-side filters."""
    results = st.session_state.get(state.FLIGHT_RESULTS_KEY)

    if results is None:
        st.info("Click 'Search Flights' to load available flights.")
        return

    flights = results.get("flights", []) if isinstance(results, dict) else results

    if not flights:
        st.warning("No flights found for these criteria.")
        return

    total_found = (
        results.get("total_results", results.get("total_count", len(flights)))
        if isinstance(results, dict)
        else len(flights)
    )
    st.caption(f"Found {total_found} flight(s)")

    # Plan indicator
    session_id = state.get_session_id()
    if session_id:
        try:
            plan = client.get_trip_plan(session_id)
            n = sum(1 for it in plan.get("items", []) if it.get("item_type") == "flight")
            if n:
                st.info(f"✈️ {n} flight(s) already in your plan — you can add more.")
        except Exception:
            pass

    # Filter controls
    f1, f2, f3, f4 = st.columns(4)
    cabin_filter = f1.selectbox(
        "Cabin Class",
        ["All Classes", "ECONOMY", "PREMIUM_ECONOMY", "BUSINESS", "FIRST"],
        key="flight_cabin_filter",
    )
    direct_filter = f2.selectbox(
        "Stops",
        ["Any", "Direct only", "Connecting only"],
        key="flight_direct_filter",
    )
    arrive_by = f3.text_input(
        "Arrive by (HH:MM)", value="", placeholder="e.g. 18:00",
        key="flight_arrive_by",
    )
    sort_by = f4.selectbox(
        "Sort by",
        ["Price ↑", "Price ↓", "Departure ↑", "Departure ↓", "Duration ↑"],
        key="flight_sort",
    )

    # Apply filters
    if cabin_filter != "All Classes":
        flights = [f for f in flights if f.get("cabin_class", "").upper() == cabin_filter]

    if direct_filter == "Direct only":
        flights = [f for f in flights if f.get("is_direct", True)]
    elif direct_filter == "Connecting only":
        flights = [f for f in flights if not f.get("is_direct", True)]

    if arrive_by and ":" in arrive_by:
        try:
            h, m = arrive_by.strip().split(":")
            cutoff = datetime.time(int(h), int(m))
            def _ok(f):
                arr = (f.get("arrival_datetime") or "")
                if len(arr) >= 16:
                    try:
                        t = datetime.time(int(arr[11:13]), int(arr[14:16]))
                        return t <= cutoff
                    except (ValueError, IndexError):
                        pass
                return True
            flights = [f for f in flights if _ok(f)]
        except (ValueError, TypeError):
            pass

    # Sort
    if sort_by == "Price ↑":
        flights = sorted(flights, key=lambda f: f.get("price_per_person", 0))
    elif sort_by == "Price ↓":
        flights = sorted(flights, key=lambda f: f.get("price_per_person", 0), reverse=True)
    elif sort_by == "Departure ↑":
        flights = sorted(flights, key=lambda f: f.get("departure_datetime", ""))
    elif sort_by == "Departure ↓":
        flights = sorted(flights, key=lambda f: f.get("departure_datetime", ""), reverse=True)
    else:  # Duration ↑
        flights = sorted(flights, key=lambda f: f.get("duration_min", 0))

    # Collect already-booked edge IDs with counts for badge display
    from collections import Counter
    booked_edge_counts: Counter = Counter()
    if session_id:
        try:
            plan = client.get_trip_plan(session_id)
            for it in plan.get("items", []):
                if it.get("item_type") == "flight":
                    booked_edge_counts[it.get("ref_id", "")] += 1
        except Exception:
            pass

    for flight in flights:
        render_flight_card(
            flight,
            on_select=lambda f: _book_flight(client, f),
            booked_count=booked_edge_counts.get(flight.get("edge_id"), 0),
        )

    render_back_to_top()


def _book_flight(client: TravelWorldClient, flight: dict) -> None:
    """Add selected flight to trip plan with full metadata."""
    session_id = state.get_session_id()
    if not session_id:
        st.warning("Start a session in Trip Setup first before selecting flights.")
        return
    try:
        client.add_trip_item(
            session_id=session_id,
            item={
                "item_type": "flight",
                "ref_id": flight.get("edge_id", flight.get("flight_id", "")),
                "date": (flight.get("departure_datetime", "") or "")[:10],
                "cost": flight.get("total_price", flight.get("price_per_person", 0.0)),
                "metadata": {
                    "airline": flight.get("airline"),
                    "flight_number": flight.get("flight_number"),
                    "origin_city_id": flight.get("origin_city_id"),
                    "destination_city_id": flight.get("destination_city_id"),
                    "departure_datetime": flight.get("departure_datetime"),
                    "arrival_datetime": flight.get("arrival_datetime"),
                    "duration_min": flight.get("duration_min"),
                    "cabin_class": flight.get("cabin_class"),
                    "is_direct": flight.get("is_direct", True),
                    "layover_city_name": flight.get("layover_city_name"),
                },
            },
        )
        st.success(f"Flight {flight.get('flight_number', '')} added to your plan!")
        st.cache_data.clear()
        st.rerun()
    except APIError as e:
        st.error(f"Could not add flight to plan: {e.message}")
