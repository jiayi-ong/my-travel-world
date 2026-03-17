"""
Folium map construction helpers.

Builds a Folium map with color-coded polylines for each transport mode,
waypoint markers, and tooltips showing route details.
"""
import folium

# Color mapping per transport mode
MODE_COLORS = {
    "FLIGHT": "#3498db",      # blue
    "RAIL": "#2ecc71",        # green
    "BUS": "#e67e22",         # orange
    "METRO": "#9b59b6",       # purple
    "WALKING": "#95a5a6",     # gray
    "TAXI": "#f1c40f",        # yellow
    "RIDESHARE": "#f39c12",   # dark yellow
    "RENTAL_CAR": "#e74c3c",  # red
    "CYCLING": "#1abc9c",     # teal
}


def build_route_map(
    routes: list[dict], center: list[float] | None = None
) -> folium.Map:
    """
    Build a Folium map with one polyline per route option.

    Args:
        routes: List of RouteOption dicts from /routing/compare.
        center: [lat, lon] for initial map center; auto-computed from routes if None.

    Returns:
        A configured folium.Map ready for st_folium rendering.
    """
    DEFAULT_CENTER = [48.8566, 2.3522]  # Paris

    # Collect all polyline points to compute center
    all_points: list[list[float]] = []
    for route in routes:
        polyline = route.get("polyline") or []
        all_points.extend(polyline)

    if center is None:
        if all_points:
            avg_lat = sum(p[0] for p in all_points) / len(all_points)
            avg_lon = sum(p[1] for p in all_points) / len(all_points)
            center = [avg_lat, avg_lon]
        else:
            center = DEFAULT_CENTER

    zoom_start = 12 if all_points else 5
    m = folium.Map(location=center, zoom_start=zoom_start, tiles="CartoDB positron")

    start_point: list[float] | None = None
    end_point: list[float] | None = None

    for route in routes:
        mode = route.get("mode", "UNKNOWN")
        color = MODE_COLORS.get(mode, "#333333")
        polyline = route.get("polyline") or []

        if not polyline:
            continue

        duration = route.get("total_duration_min", 0)
        cost = float(route.get("total_cost", 0.0) or 0.0)
        tooltip_text = f"{mode}: {duration} min | ${cost:.2f}"

        folium.PolyLine(
            locations=polyline,
            color=color,
            weight=4,
            opacity=0.8,
            tooltip=tooltip_text,
        ).add_to(m)

        # Track first and last points across all routes for markers
        if start_point is None:
            start_point = polyline[0]
        end_point = polyline[-1]

    # Add start/end markers if we have polylines
    if start_point is not None:
        folium.Marker(
            location=start_point,
            tooltip="Origin",
            icon=folium.Icon(color="green", icon="play"),
        ).add_to(m)

    if end_point is not None and end_point != start_point:
        folium.Marker(
            location=end_point,
            tooltip="Destination",
            icon=folium.Icon(color="red", icon="stop"),
        ).add_to(m)

    return m


def add_location_marker(
    m: folium.Map, lat: float, lon: float, name: str, icon_color: str = "blue"
) -> None:
    """Add a named marker to the map."""
    folium.Marker(
        location=[lat, lon],
        tooltip=name,
        icon=folium.Icon(color=icon_color),
    ).add_to(m)


def add_trip_plan_markers(
    m: folium.Map, trip_plan_items: list[dict], geo_data: dict
) -> folium.Map:
    """
    Add markers for all trip plan items (hotels, venues, attractions) to the map.

    Args:
        m: Existing folium.Map to add markers to.
        trip_plan_items: List of TripPlanItem dicts from the session.
        geo_data: Dict mapping ref_id to {name, lat, lon} for marker placement.

    Returns:
        The same folium.Map with markers added.
    """
    icon_color_by_type = {
        "hotel": "red",
        "event": "purple",
        "attraction": "green",
        "flight": "blue",
    }

    for item in trip_plan_items:
        ref_id = item.get("ref_id")
        if ref_id and ref_id in geo_data:
            loc = geo_data[ref_id]
            item_type = item.get("item_type", "")
            icon_color = icon_color_by_type.get(item_type, "blue")
            add_location_marker(
                m, loc["lat"], loc["lon"], loc.get("name", ref_id), icon_color
            )

    return m
