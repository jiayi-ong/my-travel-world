"""
/weather routes: city weather forecasts.
"""
from fastapi import APIRouter, Depends, HTTPException
from travel_world.api.dependencies import get_active_world_state

router = APIRouter(prefix="/weather", tags=["weather"])


@router.get("/forecast")
def get_weather_forecast(
    city_id: str,
    start_date: str,
    end_date: str,
    world_state=Depends(get_active_world_state),
):
    """Get daily weather forecast for a city over a date range."""
    try:
        weather = world_state.get_layer("weather")
    except KeyError:
        raise HTTPException(status_code=503, detail="Weather layer not loaded.")
    forecasts = weather.get_weather_range(city_id, start_date, end_date)
    return [
        {
            "date": date_str,
            "condition": snap.condition.value,
            "temperature_c": round(snap.temperature_c, 1),
            "precipitation_mm": round(snap.precipitation_mm, 1),
            "wind_speed_kmh": round(snap.wind_speed_kmh, 1),
            "visibility_km": round(snap.visibility_km, 1),
            "humidity_pct": round(snap.humidity_pct, 1),
        }
        for date_str, snap in forecasts
    ]


@router.get("/snapshot")
def get_weather_snapshot(
    city_id: str,
    date: str,
    world_state=Depends(get_active_world_state),
):
    """Get weather for a single city/date."""
    try:
        weather = world_state.get_layer("weather")
    except KeyError:
        raise HTTPException(status_code=503, detail="Weather layer not loaded.")
    snap = weather.get_weather(city_id, date)
    if snap is None:
        return None
    return {
        "date": date,
        "condition": snap.condition.value,
        "temperature_c": round(snap.temperature_c, 1),
        "precipitation_mm": round(snap.precipitation_mm, 1),
        "wind_speed_kmh": round(snap.wind_speed_kmh, 1),
        "visibility_km": round(snap.visibility_km, 1),
        "humidity_pct": round(snap.humidity_pct, 1),
    }
