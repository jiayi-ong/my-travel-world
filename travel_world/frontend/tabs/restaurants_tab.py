"""
Restaurants tab: browse and add restaurants to your trip plan.

Restaurants are walk-in or reservation-based dining spots available throughout
the trip. Unlike events, they have no fixed show time — open hours apply.
"""
import streamlit as st
from travel_world.frontend import state
from travel_world.frontend.api_client import TravelWorldClient, APIError
from travel_world.frontend.components.back_to_top import render_back_to_top

_CUISINE_OPTIONS = [
    "Italian", "French", "Japanese", "Chinese", "Mexican", "Indian",
    "Mediterranean", "American", "Thai", "Spanish", "Greek", "Vietnamese",
]

_STARS = {1: "⭐", 2: "⭐⭐", 3: "⭐⭐⭐"}


def _render_city_selector(client: TravelWorldClient, prefs: dict) -> str:
    world_id = st.session_state.get(state.WORLD_ID_KEY)
    cities: list[dict] = []
    if world_id:
        try:
            cities = client.list_cities(world_id)
        except Exception:
            pass

    dest_list = prefs.get("destination_city_ids", [])
    default_city = (
        st.session_state.get("tworld_restaurant_city_local")
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
            key="restaurant_tab_city",
        )
    else:
        city_id = st.text_input(
            "Destination City ID",
            value=default_city,
            key="restaurant_tab_city",
        )

    if not city_id:
        st.info("Please select a destination city.")
        return ""

    st.session_state["tworld_restaurant_city_local"] = city_id
    return city_id


def render(client: TravelWorldClient) -> None:
    """Render the Restaurants tab."""
    st.header("Restaurants")

    prefs = state.get_preferences()
    city_id = _render_city_selector(client, prefs)
    if not city_id:
        return

    _render_filters()
    _render_results(client, prefs, city_id)


def _render_filters() -> None:
    """Cuisine, price, and reservation filters."""
    with st.expander("Filters", expanded=True):
        col1, col2, col3 = st.columns(3)

        with col1:
            cuisine = st.selectbox(
                "Cuisine",
                ["Any"] + _CUISINE_OPTIONS,
                index=0,
                key="restaurant_filter_cuisine",
            )
            st.session_state["tworld_restaurant_filter_cuisine"] = None if cuisine == "Any" else cuisine

        with col2:
            max_spend = st.number_input(
                "Max avg spend/person ($)",
                min_value=0.0,
                value=float(st.session_state.get("tworld_restaurant_filter_max_spend", 200.0)),
                step=10.0,
                key="restaurant_filter_max_spend_input",
            )
            st.session_state["tworld_restaurant_filter_max_spend"] = max_spend

        with col3:
            reservation_filter = st.selectbox(
                "Reservation",
                ["Any", "Walk-in only", "Reservation required"],
                index=0,
                key="restaurant_filter_reservation",
            )
            if reservation_filter == "Walk-in only":
                st.session_state["tworld_restaurant_filter_reservation"] = False
            elif reservation_filter == "Reservation required":
                st.session_state["tworld_restaurant_filter_reservation"] = True
            else:
                st.session_state["tworld_restaurant_filter_reservation"] = None


def _render_results(client: TravelWorldClient, prefs: dict, city_id: str) -> None:
    cuisine = st.session_state.get("tworld_restaurant_filter_cuisine")
    max_spend = st.session_state.get("tworld_restaurant_filter_max_spend", 200.0)
    reservation_required = st.session_state.get("tworld_restaurant_filter_reservation")

    try:
        restaurants = client.search_restaurants(
            city_id=city_id,
            cuisine=cuisine,
            max_avg_spend=max_spend if max_spend and max_spend > 0 else None,
            reservation_required=reservation_required,
            session_id=state.get_session_id(),
        )
    except APIError as e:
        st.error(f"Could not load restaurants: {e.message}")
        return

    if not restaurants:
        st.info("No restaurants match the current filters.")
        return

    st.caption(f"{len(restaurants)} restaurant(s) found")

    sort_by = st.selectbox(
        "Sort by",
        ["Popularity ↓", "Price ↑", "Price ↓", "Rating ↓"],
        key="restaurant_sort",
    )
    if sort_by == "Popularity ↓":
        restaurants = sorted(restaurants, key=lambda r: r.get("popularity_score", 0), reverse=True)
    elif sort_by == "Price ↑":
        restaurants = sorted(restaurants, key=lambda r: r.get("average_spend", 0))
    elif sort_by == "Price ↓":
        restaurants = sorted(restaurants, key=lambda r: r.get("average_spend", 0), reverse=True)
    elif sort_by == "Rating ↓":
        restaurants = sorted(restaurants, key=lambda r: r.get("average_rating") or 0, reverse=True)

    # Booked restaurant counts
    from collections import Counter
    booked_counts: Counter = Counter()
    _sid = state.get_session_id()
    if _sid:
        try:
            _plan = client.get_trip_plan(_sid)
            for it in _plan.get("items", []):
                if it.get("item_type") == "restaurant":
                    booked_counts[it.get("ref_id", "")] += 1
        except Exception:
            pass

    for r in restaurants:
        _render_restaurant_card(client, r, booked_counts)

    render_back_to_top()


def _render_restaurant_card(client: TravelWorldClient, r: dict, booked_counts) -> None:
    restaurant_id = r.get("restaurant_id", "unknown")
    cnt = booked_counts.get(restaurant_id, 0)

    with st.container(border=True):
        col1, col2, col3 = st.columns([3, 2, 1])

        with col1:
            name = r.get("name", "Unknown Restaurant")
            cuisines = ", ".join(r.get("cuisine_types", []))
            district = r.get("district_name", "")
            michelin = r.get("michelin_stars", 0)
            description = r.get("description", "")
            avg_rating = r.get("average_rating")
            review_count = r.get("review_count", 0)

            headline = f"**{name}**"
            if michelin:
                headline += f"  {_STARS.get(michelin, '')} Michelin"
            st.markdown(headline)
            st.caption(f"🍽️ {cuisines}  |  📍 {district}" if district else f"🍽️ {cuisines}")
            if description:
                st.write(description)
            if avg_rating is not None:
                color = "🟢" if avg_rating >= 4.0 else ("🟡" if avg_rating >= 3.0 else "🔴")
                st.caption(f"{color} {avg_rating:.1f}/5  ({review_count} reviews)")

        with col2:
            tier_label = r.get("price_tier_label", "$")
            avg_spend = r.get("average_spend", 0.0)
            reservation_required = r.get("reservation_required", False)
            opening_hours = r.get("opening_hours", {})

            st.markdown(f"**{tier_label}** — avg **${avg_spend:.0f}**/person")
            if reservation_required:
                st.caption("📅 Reservation required")
            else:
                st.caption("🚶 Walk-in welcome")
            if opening_hours:
                # Show first day's hours as representative
                sample_hours = next(
                    (v for v in opening_hours.values() if v), None
                )
                if sample_hours:
                    st.caption(f"🕐 {sample_hours}")

        with col3:
            if cnt > 0:
                st.info(f"In plan ×{cnt}")
            if st.button(
                "Add again" if cnt > 0 else "Add to Plan",
                key=f"add_restaurant_{restaurant_id}",
                type="primary",
            ):
                _add_restaurant(client, r)

        # Reviews expander
        reviews = r.get("reviews", [])
        if reviews:
            with st.expander(f"Reviews ({len(reviews)})"):
                for rv in reviews:
                    stars = "⭐" * max(1, round(rv.get("rating", 3)))
                    st.markdown(f"{stars} **{rv.get('reviewer_id', '')}** · {rv.get('date', '')}")
                    st.write(rv.get("text", ""))


def _add_restaurant(client: TravelWorldClient, r: dict) -> None:
    """Add a restaurant visit to the trip plan."""
    session_id = state.get_session_id()
    if not session_id:
        st.warning("Start a session in Trip Setup first.")
        return

    prefs = state.get_preferences()
    group_size = int(prefs.get("group_size", 1))
    cost = round(float(r.get("average_spend", 0.0)) * group_size, 2)

    try:
        client.add_trip_item(
            session_id=session_id,
            item={
                "item_type": "restaurant",
                "ref_id": r.get("restaurant_id", "unknown"),
                "date": str(prefs.get("departure_date", "")),
                "cost": cost,
                "metadata": {
                    "name": r.get("name"),
                    "cuisine_types": r.get("cuisine_types"),
                    "district_name": r.get("district_name"),
                    "city_id": r.get("city_id"),
                    "average_spend": r.get("average_spend"),
                    "price_tier_label": r.get("price_tier_label"),
                    "reservation_required": r.get("reservation_required"),
                    "michelin_stars": r.get("michelin_stars"),
                },
            },
        )
        st.success(f"Added {r.get('name', 'restaurant')} to your plan!")
        st.cache_data.clear()
        st.rerun()
    except APIError as e:
        st.error(f"Could not add to plan: {e.message}")
