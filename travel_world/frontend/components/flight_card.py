"""
Reusable flight result card component.

Renders a single flight as a styled card with airline, times, duration,
price, delay estimate, baggage info, seats remaining, and a select button.
"""
import streamlit as st


def render_flight_card(flight: dict, on_select=None) -> None:
    """
    Render one flight result as a card.

    Args:
        flight: FlightResult dict from the API.
        on_select: Callback called with the flight dict when user clicks Select.
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
            st.markdown(f"🛫 `{dep}` → 🛬 `{arr}`")
            st.caption(f"Duration: {duration_str} | {cabin}")

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

            flight_id = flight.get("edge_id", flight.get("flight_id", flight.get("flight_number", id(flight))))
            cabin = flight.get("cabin_class", "")
            if st.button(
                "Select",
                key=f"select_flight_{flight_id}_{cabin}",
                type="primary",
            ):
                if on_select:
                    on_select(flight)
