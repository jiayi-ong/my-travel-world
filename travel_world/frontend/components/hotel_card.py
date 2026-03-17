"""
Reusable hotel result card component.

Renders a single hotel as a styled card with name, star rating, district,
amenities, price, availability, reviews, and a book button.
"""
import streamlit as st


# Price multipliers per bed count (1 bed = base, each extra bed adds ~40%)
_BED_PRICE_MULT = {1: 1.0, 2: 1.4, 3: 1.8, 4: 2.2}


def render_hotel_card(hotel: dict, on_book=None, booked_count: int = 0) -> None:
    """
    Render one hotel result as a card.

    Args:
        hotel: HotelResult dict from the API.
        on_book: Callback called with the hotel dict + selected beds when user clicks Book.
        booked_count: Number of times this hotel is already in the plan.
    """
    with st.container(border=True):
        col1, col2, col3 = st.columns([3, 2, 1])

        with col1:
            name = hotel.get("name", "Unknown Hotel")
            star_rating = int(hotel.get("star_rating", hotel.get("stars", 0)) or 0)
            district = hotel.get("district_name", "")
            amenities = hotel.get("amenities", []) or []
            neighborhood_score = hotel.get("neighborhood_score")

            stars_filled = "⭐" * star_rating
            st.markdown(f"**{name}** {stars_filled}")
            if district:
                loc_info = f"📍 {district}"
                if neighborhood_score is not None:
                    loc_info += f"  |  🏙️ Location score: {neighborhood_score:.2f}"
                st.caption(loc_info)
            if amenities:
                amenity_pills = " · ".join(f"`{a}`" for a in amenities[:4])
                st.caption(amenity_pills)
            if hotel.get("airport_shuttle"):
                st.caption("🚌 Airport shuttle")

        with col2:
            base_price = float(hotel.get("price_per_night", 0.0) or 0.0)
            total_cost = hotel.get("total_cost")
            num_nights = hotel.get("num_nights", 1) or 1
            rooms_available = hotel.get("rooms_available")
            avg_rating = hotel.get("average_rating")
            review_count = hotel.get("review_count", 0)

            # Bed selector
            hotel_id = hotel.get("hotel_id", "unknown")
            max_beds = int(hotel.get("num_beds", 1) or 1)
            bed_options = list(range(1, max_beds + 1))
            selected_beds = st.selectbox(
                "Beds",
                options=bed_options,
                index=0,
                format_func=lambda n: f"{n} bed{'s' if n > 1 else ''}",
                key=f"beds_{hotel_id}",
            )
            bed_mult = _BED_PRICE_MULT.get(selected_beds, 1.0 + (selected_beds - 1) * 0.4)
            adj_price = base_price * bed_mult
            adj_total = adj_price * num_nights

            st.markdown(f"**${adj_price:.2f}**/night")
            st.caption(f"Total: **${adj_total:.2f}**")

            if rooms_available is not None:
                if rooms_available < 3:
                    st.warning(f"Only {rooms_available} rooms left!")
                else:
                    st.caption(f"✅ {rooms_available} rooms available")

            if avg_rating is not None:
                rating_val = float(avg_rating)
                color = "🟢" if rating_val >= 4.0 else ("🟡" if rating_val >= 3.0 else "🔴")
                st.caption(f"{color} {rating_val:.1f}/5 ({review_count} reviews)")

        with col3:
            if booked_count > 0:
                st.info(f"Booked ×{booked_count}")
            if st.button(
                "Book again" if booked_count > 0 else "Book",
                key=f"book_hotel_{hotel_id}",
                type="primary",
            ):
                if on_book:
                    enriched = {**hotel, "selected_beds": selected_beds, "adj_price_per_night": adj_price, "adj_total": adj_total}
                    on_book(enriched)

            # Optional availability calendar
            availability = hotel.get("availability_calendar")
            if availability:
                with st.expander("Availability"):
                    for date_str, avail in availability.items():
                        status = "✓" if avail else "✗"
                        st.caption(f"{date_str}: {status}")

        reviews = hotel.get("reviews", [])
        if reviews:
            with st.expander(f"Reviews ({len(reviews)})"):
                for rv in reviews:
                    stars = "⭐" * max(1, round(rv.get("rating", 3)))
                    st.markdown(f"{stars} **{rv.get('reviewer_id', '')}** · {rv.get('date', '')}")
                    st.write(rv.get("text", ""))
