"""
Hotels tab: search, filter, and book hotels.

Pulls city and dates from session preferences. Provides star rating,
price, and amenity filters in an expander panel.
"""
import streamlit as st
from travel_world.frontend import state
from travel_world.frontend.api_client import TravelWorldClient, APIError
from travel_world.frontend.components.hotel_card import render_hotel_card
from travel_world.frontend.components.back_to_top import render_back_to_top


def render(client: TravelWorldClient) -> None:
    """Render the Hotels tab."""
    st.header("Hotel Search")

    prefs = state.get_preferences()
    check_in = prefs.get("departure_date")
    check_out = prefs.get("return_date")
    dest_list = prefs.get("destination_city_ids", [])
    city_id = dest_list[0] if dest_list else prefs.get("destination_city_id", "")

    if not check_in or not check_out:
        st.info("Please set your travel dates in the Trip Setup tab.")
        return

    if not city_id:
        st.info("Please set a destination city in the Trip Setup tab.")
        return

    with st.expander("Filters", expanded=True):
        _render_filter_panel()

    _render_search_button(client, prefs, city_id, check_in, check_out)
    _render_results(client)


def _render_filter_panel() -> None:
    """Star, price, and amenity filters."""
    col1, col2, col3 = st.columns(3)

    with col1:
        min_stars = st.slider(
            "Min Stars",
            min_value=1,
            max_value=5,
            value=st.session_state.get("tworld_hotel_filter_min_stars", 1),
        )
        st.session_state["tworld_hotel_filter_min_stars"] = min_stars

    with col2:
        max_price = st.number_input(
            "Max price/night ($)",
            min_value=0.0,
            value=float(st.session_state.get("tworld_hotel_filter_max_price", 500.0)),
            step=25.0,
        )
        st.session_state["tworld_hotel_filter_max_price"] = max_price

    with col3:
        amenities = st.multiselect(
            "Required Amenities",
            options=["WIFI", "BREAKFAST", "POOL", "GYM", "PARKING", "SPA", "PET_FRIENDLY"],
            default=st.session_state.get("tworld_hotel_filter_amenities", []),
        )
        st.session_state["tworld_hotel_filter_amenities"] = amenities


def _render_search_button(
    client: TravelWorldClient,
    prefs: dict,
    city_id: str,
    check_in: str,
    check_out: str,
) -> None:
    """Search button triggers hotel search with current filter values."""
    guests = int(prefs.get("group_size", 1))
    max_price = st.session_state.get("tworld_hotel_filter_max_price", None)
    min_stars = st.session_state.get("tworld_hotel_filter_min_stars", None)

    # Auto-search if results are None and preferences are set
    auto_search = st.session_state.get(state.HOTEL_RESULTS_KEY) is None

    if st.button("Search Hotels", type="primary") or auto_search:
        with st.spinner("Searching hotels..."):
            try:
                results = client.search_hotels(
                    city_id=city_id,
                    check_in=str(check_in),
                    check_out=str(check_out),
                    guests=guests,
                    max_price_per_night=max_price if max_price and max_price > 0 else None,
                    min_stars=min_stars if min_stars and min_stars > 1 else None,
                    session_id=state.get_session_id(),
                )
                st.session_state[state.HOTEL_RESULTS_KEY] = results
            except APIError as e:
                st.error(f"Hotel search failed: {e.message}")


def _render_results(client: TravelWorldClient) -> None:
    """Render hotel result cards."""
    results = st.session_state.get(state.HOTEL_RESULTS_KEY)

    if results is None:
        st.info("Click 'Search Hotels' to find available accommodations.")
        return

    hotels = results.get("hotels", []) if isinstance(results, dict) else results

    if not hotels:
        st.warning("No hotels found matching your criteria. Try relaxing the filters.")
        return

    total_found = (
        results.get("total_results", results.get("total_count", len(hotels)))
        if isinstance(results, dict)
        else len(hotels)
    )

    # Apply client-side amenity filter
    required_amenities = st.session_state.get("tworld_hotel_filter_amenities", [])
    if required_amenities:
        hotels = [
            h for h in hotels
            if all(
                a in (h.get("amenities") or [])
                for a in required_amenities
            )
        ]

    st.metric("Hotels Found", len(hotels))
    st.caption(f"{total_found} total matched before amenity filter")

    sort_by = st.selectbox(
        "Sort by",
        ["Price ↑", "Price ↓", "Stars ↑", "Stars ↓", "Rating ↓", "Rating ↑"],
        key="hotel_sort",
    )

    if sort_by == "Price ↑":
        hotels = sorted(hotels, key=lambda h: h.get("price_per_night", 0))
    elif sort_by == "Price ↓":
        hotels = sorted(hotels, key=lambda h: h.get("price_per_night", 0), reverse=True)
    elif sort_by == "Stars ↑":
        hotels = sorted(hotels, key=lambda h: h.get("star_rating", 0))
    elif sort_by == "Stars ↓":
        hotels = sorted(hotels, key=lambda h: h.get("star_rating", 0), reverse=True)
    elif sort_by == "Rating ↓":
        hotels = sorted(hotels, key=lambda h: h.get("average_rating") or 0, reverse=True)
    else:  # "Rating ↑"
        hotels = sorted(hotels, key=lambda h: h.get("average_rating") or 0)

    for hotel in hotels:
        render_hotel_card(
            hotel,
            on_book=lambda h: _book_hotel(client, h),
        )

    render_back_to_top()


def _book_hotel(client: TravelWorldClient, hotel: dict) -> None:
    """Book a hotel and add to trip plan."""
    session_id = state.get_session_id()
    if not session_id:
        st.warning("Start a session in Trip Setup first.")
        return

    prefs = state.get_preferences()
    check_in = str(prefs.get("departure_date", ""))
    check_out = str(prefs.get("return_date", ""))

    try:
        client.book_hotel(
            hotel_id=hotel.get("hotel_id"),
            check_in=check_in,
            check_out=check_out,
            session_id=session_id,
        )
        st.success(f"Booked {hotel.get('name', 'hotel')} successfully!")
        st.cache_data.clear()
        st.rerun()
    except APIError as e:
        st.error(f"Booking failed: {e.message}")
