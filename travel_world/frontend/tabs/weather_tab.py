"""
Weather tab: city forecast view for the trip date range.
"""
import datetime
import streamlit as st
from travel_world.frontend import state
from travel_world.frontend.api_client import TravelWorldClient, APIError

_CONDITION_ICON = {
    "sunny": "☀️",
    "partly_cloudy": "⛅",
    "cloudy": "☁️",
    "rainy": "🌧️",
    "stormy": "⛈️",
    "snowy": "❄️",
    "foggy": "🌫️",
    "windy": "💨",
}
_CONDITION_COLOR = {
    "sunny": "#FFF9C4",
    "partly_cloudy": "#E3F2FD",
    "cloudy": "#ECEFF1",
    "rainy": "#E1F5FE",
    "stormy": "#EDE7F6",
    "snowy": "#F3F4F6",
    "foggy": "#F5F5F5",
    "windy": "#E8F5E9",
}


def render(client: TravelWorldClient) -> None:
    """Render the Weather Forecast tab."""
    st.header("Weather Forecast")

    prefs = state.get_preferences()
    world_id = st.session_state.get(state.WORLD_ID_KEY)

    # City selector
    cities: list[dict] = []
    if world_id:
        try:
            cities = client.list_cities(world_id)
        except Exception:
            pass

    dest_list = prefs.get("destination_city_ids", [])
    default_city = dest_list[0] if dest_list else prefs.get("destination_city_id", "")
    city_labels: dict[str, str] = {}

    if cities:
        city_ids = [c["city_id"] for c in cities]
        city_labels = {c["city_id"]: c["name"] for c in cities}
        idx = city_ids.index(default_city) if default_city in city_ids else 0
        city_id = st.selectbox(
            "City",
            city_ids,
            index=idx,
            format_func=lambda x: city_labels.get(x, x),
            key="weather_tab_city",
        )
    else:
        city_id = st.text_input("City ID", value=default_city, key="weather_tab_city")

    if not city_id:
        st.info("Select a city to view the forecast.")
        return

    # Date range (defaults to trip dates, minimum today)
    today = datetime.date.today()
    raw_depart = prefs.get("departure_date")
    raw_return = prefs.get("return_date")
    try:
        default_start = datetime.date.fromisoformat(str(raw_depart)) if raw_depart else today
    except (ValueError, TypeError):
        default_start = today
    try:
        default_end = datetime.date.fromisoformat(str(raw_return)) if raw_return else today + datetime.timedelta(days=14)
    except (ValueError, TypeError):
        default_end = default_start + datetime.timedelta(days=14)

    col1, col2 = st.columns(2)
    start_date = col1.date_input("From", value=default_start, key="weather_start")
    end_date = col2.date_input("To", value=default_end, min_value=start_date, key="weather_end")

    # Fetch forecast
    try:
        forecast = client.get_weather_forecast(city_id, str(start_date), str(end_date))
    except APIError as e:
        st.error(f"Could not load forecast: {e.message}")
        return

    if not forecast:
        st.info("No forecast data available for this period.")
        return

    city_name = city_labels.get(city_id, city_id)
    st.subheader(f"📍 {city_name}  ·  {start_date} → {end_date}")

    # Summary stats
    temps = [d["temperature_c"] for d in forecast]
    conditions = [d["condition"] for d in forecast]
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Days", len(forecast))
    col2.metric("Avg Temp", f"{sum(temps)/len(temps):.1f}°C")
    col3.metric("Min Temp", f"{min(temps):.1f}°C")
    col4.metric("Max Temp", f"{max(temps):.1f}°C")

    # Most common condition
    from collections import Counter
    most_common = Counter(conditions).most_common(1)[0][0]
    icon = _CONDITION_ICON.get(most_common, "🌡️")
    st.caption(f"Predominant condition: {icon} {most_common.replace('_', ' ').title()}")

    st.divider()

    # Day-by-day cards in rows of 7
    chunk_size = 7
    for chunk_start in range(0, len(forecast), chunk_size):
        chunk = forecast[chunk_start:chunk_start + chunk_size]
        cols = st.columns(len(chunk))
        for col, day in zip(cols, chunk):
            cond = day["condition"]
            icon = _CONDITION_ICON.get(cond, "🌡️")
            with col:
                st.markdown(f"**{day['date'][5:]}**")  # MM-DD
                st.markdown(f"### {icon}")
                st.markdown(f"**{day['temperature_c']}°C**")
                st.caption(cond.replace("_", " "))
                st.caption(f"💧 {day['precipitation_mm']}mm")
                st.caption(f"💨 {day['wind_speed_kmh']}km/h")
