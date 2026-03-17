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


def _render_city_selector(client: TravelWorldClient, prefs: dict) -> str:
    """City selector local to hotels tab — defaults to trip prefs but overridable."""
    world_id = st.session_state.get(state.WORLD_ID_KEY)
    cities: list[dict] = []
    if world_id:
        try:
            cities = client.list_cities(world_id)
        except Exception:
            pass

    dest_list = prefs.get("destination_city_ids", [])
    default_city = (
        st.session_state.get("tworld_hotel_city_local")
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
            key="hotel_tab_city",
        )
    else:
        city_id = st.text_input(
            "Destination City ID",
            value=st.session_state.get("tworld_hotel_city_local", default_city),
            key="hotel_tab_city",
        )

    if not city_id:
        st.info("Please select a destination city.")
        return ""

    st.session_state["tworld_hotel_city_local"] = city_id
    return city_id


def render(client: TravelWorldClient) -> None:
    """Render the Hotels tab."""
    st.header("Hotel Search")

    prefs = state.get_preferences()
    check_in = prefs.get("departure_date")
    check_out = prefs.get("return_date")

    if not check_in or not check_out:
        st.info("Please set your travel dates in the Trip Setup tab.")
        return

    city_id = _render_city_selector(client, prefs)
    if not city_id:
        return

    # Custom booking date range (defaults to trip dates, overridable per hotel)
    if "tworld_hotel_checkin" not in st.session_state:
        st.session_state["tworld_hotel_checkin"] = str(check_in)
    if "tworld_hotel_checkout" not in st.session_state:
        st.session_state["tworld_hotel_checkout"] = str(check_out)

    st.subheader("Booking Dates")
    import datetime as _dt
    col_ci, col_co = st.columns(2)

    _ci_val = st.session_state["tworld_hotel_checkin"]
    _co_val = st.session_state["tworld_hotel_checkout"]
    try:
        _ci_date = _dt.date.fromisoformat(str(_ci_val))
    except (ValueError, TypeError):
        _ci_date = _dt.date.today() + _dt.timedelta(days=14)
    try:
        _co_date = _dt.date.fromisoformat(str(_co_val))
    except (ValueError, TypeError):
        _co_date = _ci_date + _dt.timedelta(days=7)

    custom_checkin_dt = col_ci.date_input(
        "Check-in",
        value=_ci_date,
        min_value=_dt.date.today(),
        key="hotel_checkin_input",
    )
    custom_checkout_dt = col_co.date_input(
        "Check-out",
        value=_co_date,
        min_value=custom_checkin_dt + _dt.timedelta(days=1),
        key="hotel_checkout_input",
    )
    custom_checkin = str(custom_checkin_dt)
    custom_checkout = str(custom_checkout_dt)
    st.session_state["tworld_hotel_checkin"] = custom_checkin
    st.session_state["tworld_hotel_checkout"] = custom_checkout

    with st.expander("Filters", expanded=True):
        _render_filter_panel()

    _render_search_button(client, prefs, city_id, custom_checkin, custom_checkout)
    _render_results(client)


def _render_filter_panel() -> None:
    """Star, price, amenity, and beds filters."""
    col1, col2, col3, col4 = st.columns(4)

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

    with col4:
        min_beds = st.selectbox(
            "Min Beds",
            options=[1, 2, 3, 4],
            index=st.session_state.get("tworld_hotel_filter_min_beds", 0),
        )
        st.session_state["tworld_hotel_filter_min_beds"] = [1, 2, 3, 4].index(min_beds)
        st.session_state["tworld_hotel_filter_min_beds_val"] = min_beds


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

    # Apply client-side amenity filter (normalize case: API returns lowercase, UI uses uppercase)
    required_amenities = st.session_state.get("tworld_hotel_filter_amenities", [])
    if required_amenities:
        hotels = [
            h for h in hotels
            if all(
                a.lower() in [x.lower() for x in (h.get("amenities") or [])]
                for a in required_amenities
            )
        ]

    # Apply client-side beds filter
    min_beds_val = st.session_state.get("tworld_hotel_filter_min_beds_val", 1)
    if min_beds_val and min_beds_val > 1:
        hotels = [h for h in hotels if int(h.get("num_beds") or 1) >= min_beds_val]

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

    # Collect already-booked hotel IDs with counts for badge display
    from collections import Counter
    booked_hotel_counts: Counter = Counter()
    _sid = state.get_session_id()
    if _sid:
        try:
            _plan = client.get_trip_plan(_sid)
            for it in _plan.get("items", []):
                if it.get("item_type") == "hotel":
                    booked_hotel_counts[it.get("ref_id", "")] += 1
        except Exception:
            pass

    for hotel in hotels:
        render_hotel_card(
            hotel,
            on_book=lambda h: _book_hotel(client, h),
            booked_count=booked_hotel_counts.get(hotel.get("hotel_id"), 0),
        )

    render_back_to_top()


def _book_hotel(client: TravelWorldClient, hotel: dict) -> None:
    """Book a hotel and add to trip plan."""
    session_id = state.get_session_id()
    if not session_id:
        st.warning("Start a session in Trip Setup first.")
        return

    prefs = state.get_preferences()
    check_in = st.session_state.get(
        "tworld_hotel_checkin", str(prefs.get("departure_date", ""))
    )
    check_out = st.session_state.get(
        "tworld_hotel_checkout", str(prefs.get("return_date", ""))
    )

    selected_beds = hotel.get("selected_beds", 1)
    adj_total = hotel.get("adj_total") or float(hotel.get("total_cost") or hotel.get("price_per_night", 0.0))

    try:
        client.book_hotel(
            hotel_id=hotel.get("hotel_id"),
            check_in=check_in,
            check_out=check_out,
            session_id=session_id,
        )
        # Record in trip plan with bed selection and adjusted cost
        client.add_trip_item(
            session_id=session_id,
            item={
                "item_type": "hotel",
                "ref_id": hotel.get("hotel_id", ""),
                "date": check_in,
                "cost": adj_total,
                "metadata": {
                    "name": hotel.get("name"),
                    "city_id": hotel.get("city_id"),
                    "check_in": check_in,
                    "check_out": check_out,
                    "star_rating": hotel.get("star_rating"),
                    "check_in_time": hotel.get("check_in_time", "13:00"),
                    "num_beds": selected_beds,
                },
            },
        )
        bed_str = f"{selected_beds} bed{'s' if selected_beds > 1 else ''}"
        st.success(f"Booked {hotel.get('name', 'hotel')} ({bed_str}) successfully!")
        st.cache_data.clear()
        st.rerun()
    except APIError as e:
        st.error(f"Booking failed: {e.message}")
