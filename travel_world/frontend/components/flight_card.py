"""
Reusable flight result card component.

Renders a single flight as a styled card with airline, times, duration,
price, delay estimate, baggage info, seats remaining, and a select button.
"""
import streamlit as st


def render_flight_card(flight: dict, on_select=None, booked_count: int = 0) -> None:
    """
    Render one flight result as a card.

    Args:
        flight: FlightResult dict from the API.
        on_select: Callback called with the flight dict when user clicks Select.
        booked_count: Number of times this flight is already in the plan.
    """
    with st.container(border=True):
        col1, col2, col3, col4 = st.columns([2, 3, 2, 1])

        with col1:
            airline = flight.get("airline", "Unknown Airline")
            flight_number = flight.get("flight_number", "N/A")
            st.markdown(f"**✈️ {airline}**")
            st.caption(f"Flight {flight_number}")

        with col2:
            dep = (flight.get("departure_datetime", "") or "")[:16].replace("T", " ")
            arr = (flight.get("arrival_datetime", "") or "")[:16].replace("T", " ")
            duration_min = int(flight.get("duration_min", 0) or 0)
            hours, mins = divmod(duration_min, 60)
            duration_str = f"{hours}h {mins}m" if hours else f"{mins}m"
            cabin = flight.get("cabin_class", "ECONOMY")
            is_direct = flight.get("is_direct", True)
            st.markdown(f"🛫 `{dep}` → 🛬 `{arr}`")
            if is_direct:
                st.caption(f"Duration: {duration_str} | {cabin} | Direct")
            else:
                layover_city = flight.get("layover_city_name", "")
                layover_min = int(flight.get("layover_duration_min", 0) or 0)
                st.caption(f"Duration: {duration_str} | {cabin} | Via {layover_city} ({layover_min}m layover)")

        with col3:
            price_per_person = float(flight.get("price_per_person", 0.0) or 0.0)
            total_price = float(flight.get("total_price", price_per_person) or price_per_person)
            st.markdown(f"**${price_per_person:.2f}**/person")
            st.caption(f"Total: **${total_price:.2f}**")

            expected_delay = int(flight.get("expected_delay_min", 0) or 0)
            if expected_delay > 30:
                st.warning(f"Avg delay: {expected_delay} min")

            baggage_included = flight.get("baggage_included", False)
            baggage_label = "Baggage included" if baggage_included else "No baggage"
            baggage_icon = "✅" if baggage_included else "❌"
            st.caption(f"{baggage_icon} {baggage_label}")

        with col4:
            seats = int(flight.get("seats_available", flight.get("seats_remaining", 99)) or 99)
            if seats < 5:
                st.warning(f"Only {seats} left!")

            if booked_count > 0:
                st.info(f"In plan ×{booked_count}")

            flight_id = flight.get("edge_id", flight.get("flight_id", flight.get("flight_number", id(flight))))
            cabin = flight.get("cabin_class", "")
            if st.button(
                "Add again" if booked_count > 0 else "Select",
                key=f"select_flight_{flight_id}_{cabin}",
                type="primary",
            ):
                if on_select:
                    on_select(flight)
