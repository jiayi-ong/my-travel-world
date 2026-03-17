"""
Reusable hotel result card component.

Renders a single hotel as a styled card with name, star rating, district,
amenities, price, availability, reviews, and a book button.
"""
import streamlit as st


def render_hotel_card(hotel: dict, on_book=None) -> None:
    """
    Render one hotel result as a card.

    Args:
        hotel: HotelResult dict from the API.
        on_book: Callback called with the hotel dict when user clicks Book.
    """
    with st.container(border=True):
        col1, col2, col3 = st.columns([3, 2, 1])

        with col1:
            name = hotel.get("name", "Unknown Hotel")
            # Support both "star_rating" and "stars" field names
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

        with col2:
            price_per_night = float(hotel.get("price_per_night", 0.0) or 0.0)
            total_cost = hotel.get("total_cost")
            rooms_available = hotel.get("rooms_available")
            avg_rating = hotel.get("average_rating")
            review_count = hotel.get("review_count", 0)

            st.markdown(f"**${price_per_night:.2f}**/night")
            if total_cost is not None:
                st.caption(f"Total: **${float(total_cost):.2f}**")

            if rooms_available is not None:
                if rooms_available < 3:
                    st.warning(f"Only {rooms_available} rooms left!")
                else:
                    st.caption(f"✅ {rooms_available} rooms available")

            if avg_rating is not None:
                rating_val = float(avg_rating)
                if rating_val >= 4.0:
                    color = "🟢"
                elif rating_val >= 3.0:
                    color = "🟡"
                else:
                    color = "🔴"
                st.caption(f"{color} {rating_val:.1f}/5 ({review_count} reviews)")

        with col3:
            hotel_id = hotel.get("hotel_id", "unknown")
            if st.button(
                "Book",
                key=f"book_hotel_{hotel_id}",
                type="primary",
            ):
                if on_book:
                    on_book(hotel)

            # Optional availability calendar
            availability = hotel.get("availability_calendar")
            if availability:
                with st.expander("Availability"):
                    for date_str, avail in availability.items():
                        status = "✓" if avail else "✗"
                        st.caption(f"{date_str}: {status}")
