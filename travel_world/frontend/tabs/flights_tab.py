"""
Flights tab: search and select flights using session preferences.

Auto-populates search from session preferences (origin, destination, departure date).
Allows outbound and return flight selection.
"""
import streamlit as st
from travel_world.frontend import state
from travel_world.frontend.api_client import TravelWorldClient, APIError
from travel_world.frontend.components.flight_card import render_flight_card
from travel_world.frontend.components.back_to_top import render_back_to_top


def render(client: TravelWorldClient) -> None:
    """Render the Flights tab."""
    st.header("Flights")

    prefs = state.get_preferences()
    origin = prefs.get("origin_city_id", "")
    dest_list = prefs.get("destination_city_ids", [])
    destination = dest_list[0] if dest_list else prefs.get("destination_city_id", "")
    departure_date = prefs.get("departure_date")

    if not origin or not destination:
        st.info("Set origin and destination city IDs in Trip Setup tab.")
        return

    _render_search_controls(client, prefs, origin, destination, departure_date)


def _render_search_controls(
    client: TravelWorldClient,
    prefs: dict,
    origin: str,
    destination: str,
    departure_date,
) -> None:
    """Inline search refinement controls inside a form."""
    with st.form("flight_search_form"):
        col1, col2 = st.columns(2)
        passengers = col1.number_input(
            "Passengers", min_value=1, max_value=9, value=int(prefs.get("group_size", 1))
        )
        date_val = col2.text_input(
            "Departure Date (YYYY-MM-DD)", value=str(departure_date) if departure_date else ""
        )
        submitted = st.form_submit_button("Search Flights", type="primary")

    # Auto-search if no cached results and date is available
    auto_search = (
        st.session_state.get(state.FLIGHT_RESULTS_KEY) is None
        and bool(date_val)
        and not submitted
    )

    if submitted or auto_search:
        if not date_val:
            st.warning("Set a departure date in Trip Setup first.")
            return
        try:
            with st.spinner("Searching flights..."):
                results = client.search_flights(
                    origin_city_id=origin,
                    destination_city_id=destination,
                    departure_date=date_val,
                    passengers=passengers,
                    cabin_class=None,
                    session_id=state.get_session_id(),
                )
            st.session_state[state.FLIGHT_RESULTS_KEY] = results
        except APIError as e:
            st.error(f"Flight search failed: {e.message}")
            return

    _render_results(client, prefs)


def _render_results(client: TravelWorldClient, prefs: dict) -> None:
    """Render flight result cards."""
    results = st.session_state.get(state.FLIGHT_RESULTS_KEY)

    if results is None:
        st.info("Click 'Search Flights' to load available flights.")
        return

    flights = results.get("flights", []) if isinstance(results, dict) else results

    if not flights:
        st.warning("No flights found for these criteria. Try adjusting your search parameters.")
        return

    total_found = (
        results.get("total_results", results.get("total_count", len(flights)))
        if isinstance(results, dict)
        else len(flights)
    )
    st.caption(f"Found {total_found} flight(s)")

    # Filter and sort controls (outside the form)
    filter_col, sort_col = st.columns(2)
    cabin_filter = filter_col.selectbox(
        "Cabin Class",
        ["All Classes", "ECONOMY", "PREMIUM_ECONOMY", "BUSINESS", "FIRST"],
        key="flight_cabin_filter",
    )
    sort_by = sort_col.selectbox(
        "Sort by",
        ["Price ↑", "Price ↓", "Departure ↑", "Departure ↓"],
        key="flight_sort",
    )

    # Apply cabin filter client-side
    if cabin_filter != "All Classes":
        flights = [f for f in flights if f.get("cabin_class") == cabin_filter]

    # Apply sort
    if sort_by == "Price ↑":
        flights = sorted(flights, key=lambda f: f.get("price_per_person", 0))
    elif sort_by == "Price ↓":
        flights = sorted(flights, key=lambda f: f.get("price_per_person", 0), reverse=True)
    elif sort_by == "Departure ↑":
        flights = sorted(flights, key=lambda f: f.get("departure_datetime", ""))
    else:  # "Departure ↓"
        flights = sorted(flights, key=lambda f: f.get("departure_datetime", ""), reverse=True)

    for flight in flights:
        render_flight_card(
            flight,
            on_select=lambda f: _book_flight(client, f),
        )

    render_back_to_top()


def _book_flight(client: TravelWorldClient, flight: dict) -> None:
    """Add selected flight to trip plan."""
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
                },
            },
        )
        st.success(f"Flight {flight.get('flight_number', '')} added to your plan!")
        st.cache_data.clear()
        st.rerun()
    except APIError as e:
        st.error(f"Could not add flight to plan: {e.message}")
