"""
Map tab: interactive world visualisation with two views.

World view  : city territory hulls + optional flight arcs + city dot markers.
City view   : district territory fills + all location pins by layer toggle.
              Includes transit network, area attraction polygons, events.

Detail panel (right column) shows the clicked item's card.
City selection via selectbox (no click-to-navigate).
"""

import json
import math

import streamlit as st

from travel_world.frontend import state
from travel_world.frontend.api_client import TravelWorldClient, APIError

# ── City colour palette ───────────────────────────────────────────────────────
_PALETTE = [
    "#4E79A7", "#F28E2B", "#E15759", "#76B7B2", "#59A14F",
    "#EDC948", "#B07AA1", "#FF9DA7", "#9C755F", "#BAB0AC",
]

# ── District type colours ─────────────────────────────────────────────────────
_DISTRICT_TYPE_COLOR = {
    "touristic":   "#F28E2B",
    "residential": "#76B7B2",
    "nightlife":   "#E15759",
    "business":    "#4E79A7",
    "cultural":    "#B07AA1",
    "historic":    "#59A14F",
    "waterfront":  "#17BECF",
}

# ── Layer toggle options ──────────────────────────────────────────────────────
_ALL_LAYERS = [
    "🏨 Hotels", "🍽 Restaurants", "🏛 Attractions", "🌿 Area Attractions",
    "🎭 Events", "🎮 Service Venues", "🏥 Amenities", "🚉 Transit",
    "🚏 Transport Hubs", "✈ Flight Arcs",
]

# ── Pin configuration: loc_type -> (layer_label, symbol, color) ──────────────
_PIN_CFG = {
    "hotel":           ("🏨 Hotels",         "square",    "#FF6B35"),
    "restaurant":      ("🍽 Restaurants",     "diamond",   "#4CAF50"),
    "attraction":      ("🏛 Attractions",     "pentagon",  "#9C27B0"),
    "area_attraction": ("🌿 Area Attractions", "circle",   "#00897B"),
    "service_venue":   ("🎮 Service Venues",  "hexagram",  "#FFD700"),
    "public_amenity":  ("🏥 Amenities",       "x",         "#5B9BD5"),
    "transport_hub":   ("🚏 Transport Hubs",  "circle",    "#1A237E"),
}


# ══════════════════════════════════════════════════════════════════════════════
# Initialisation
# ══════════════════════════════════════════════════════════════════════════════

def _init() -> None:
    for k, v in [
        ("tworld_map_view",   "world"),
        ("tworld_map_item",   None),
        ("tworld_map_layers", list(_ALL_LAYERS)),
    ]:
        if k not in st.session_state:
            st.session_state[k] = v


# ══════════════════════════════════════════════════════════════════════════════
# Public entry point
# ══════════════════════════════════════════════════════════════════════════════

def render(client: TravelWorldClient) -> None:
    """Render the Map tab."""
    _init()
    st.header("World Map")

    world_id = st.session_state.get(state.WORLD_ID_KEY)
    if not world_id:
        st.info("Select a world in Trip Setup first.")
        return

    try:
        map_data = client.get_map_data(world_id)
    except APIError as e:
        st.error(f"Could not load map data: {e.message}")
        return

    city_map = {c["city_id"]: c for c in map_data["cities"]}
    loc_map  = {l["location_id"]: l for l in map_data["locations"]}

    _render_controls(city_map)

    col_map, col_detail = st.columns([7, 3], gap="small")
    with col_map:
        fig, xmin, xmax, ymin, ymax = _build_figure(map_data, city_map, loc_map, client)
        # unique key so plotly resets selection when view changes
        chart_key = f"map_{st.session_state['tworld_map_view']}"
        sel = st.plotly_chart(fig, use_container_width=True, on_select="rerun",
                              selection_mode="points", key=chart_key)
        _handle_selection(sel)
    with col_detail:
        _render_detail_panel(city_map)

    with st.expander("🗺️ Route Planner", expanded=False):
        _render_route_planner(client)


# ══════════════════════════════════════════════════════════════════════════════
# Controls
# ══════════════════════════════════════════════════════════════════════════════

def _render_controls(city_map: dict) -> None:
    # Row 1: view selector
    options  = ["🌍 World Overview"] + [c["name"] for c in city_map.values()]
    city_ids = ["world"] + list(city_map.keys())
    cur      = st.session_state["tworld_map_view"]
    cur_idx  = city_ids.index(cur) if cur in city_ids else 0

    chosen_label = st.selectbox(
        "View", options=options, index=cur_idx,
        key="map_view_select", label_visibility="collapsed",
    )
    chosen_id = city_ids[options.index(chosen_label)]
    if chosen_id != st.session_state["tworld_map_view"]:
        st.session_state["tworld_map_view"] = chosen_id
        st.session_state["tworld_map_item"] = None
        st.rerun()

    # Row 2: layer toggles
    st.session_state["tworld_map_layers"] = st.multiselect(
        "Layers", options=_ALL_LAYERS,
        default=st.session_state["tworld_map_layers"],
        key="map_layers_ms", label_visibility="collapsed",
    )


# ══════════════════════════════════════════════════════════════════════════════
# Figure builder
# ══════════════════════════════════════════════════════════════════════════════

def _build_figure(map_data, city_map, loc_map, client):
    import plotly.graph_objects as go

    fig = go.Figure()
    fig.update_layout(
        paper_bgcolor="#DCDCDC", plot_bgcolor="#F4F2EE",
        xaxis=dict(showgrid=False, showticklabels=False, zeroline=False,
                   fixedrange=False, constrain="domain"),
        yaxis=dict(showgrid=False, showticklabels=False, zeroline=False,
                   fixedrange=False, scaleanchor="x", scaleratio=1),
        margin=dict(l=4, r=4, t=4, b=4),
        height=620, showlegend=True,
        legend=dict(orientation="h", y=-0.04, x=0,
                    bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
        dragmode="pan", hovermode="closest",
        uirevision=f"map_{st.session_state['tworld_map_view']}",
    )

    layers = set(st.session_state["tworld_map_layers"])
    view   = st.session_state["tworld_map_view"]

    if view == "world":
        xmin, xmax, ymin, ymax = _traces_world(fig, map_data, layers)
    else:
        xmin, xmax, ymin, ymax = _traces_city(fig, map_data, loc_map, view, layers, client)

    fig.update_layout(
        xaxis_range=[xmin, xmax],
        yaxis_range=[ymin, ymax],
    )
    _add_scale_bar(fig, xmin, xmax, ymin, ymax)
    return fig, xmin, xmax, ymin, ymax


# ── World view ────────────────────────────────────────────────────────────────

def _traces_world(fig, map_data, layers):
    import plotly.graph_objects as go

    cities    = map_data["cities"]
    districts = map_data["districts"]
    routes    = map_data.get("flight_routes", [])
    city_map  = {c["city_id"]: c for c in cities}

    city_color = {
        c["city_id"]: _PALETTE[i % len(_PALETTE)]
        for i, c in enumerate(cities)
    }

    # City territory hulls (convex hull of district points)
    city_dist_pts: dict = {}
    for d in districts:
        city_dist_pts.setdefault(d["city_id"], []).append((d["lon"], d["lat"]))

    for city_id, pts in city_dist_pts.items():
        color = city_color.get(city_id, "#888888")
        hull  = _hull(pts, pad=0.10)
        if hull:
            fig.add_trace(go.Scatter(
                x=[p[0] for p in hull],
                y=[p[1] for p in hull],
                mode="lines",
                fill="toself",
                fillcolor=_rgba(color, 0.18),
                line=dict(color=color, width=1.5),
                showlegend=False,
                hoverinfo="skip",
            ))

    # Flight arcs
    if "✈ Flight Arcs" in layers:
        ax: list = []
        ay: list = []
        for r in routes:
            oc = city_map.get(r.get("origin_city_id", ""))
            dc = city_map.get(r.get("dest_city_id", ""))
            if oc and dc:
                bx, by = _arc(oc["lon"], oc["lat"], dc["lon"], dc["lat"])
                ax.extend(bx)
                ay.extend(by)
        if ax:
            fig.add_trace(go.Scatter(
                x=ax, y=ay,
                mode="lines",
                line=dict(color="#5B9BD5", width=1, dash="dot"),
                showlegend=True,
                name="✈ Flight Routes",
                hoverinfo="skip",
            ))

    # City dot markers (always shown — main world-level content)
    fig.add_trace(go.Scatter(
        x=[c["lon"] for c in cities],
        y=[c["lat"] for c in cities],
        mode="markers+text",
        marker=dict(
            size=14,
            color=[city_color.get(c["city_id"], "#888") for c in cities],
            symbol="circle",
            line=dict(color="white", width=2),
        ),
        text=[c["name"] for c in cities],
        textposition="top center",
        textfont=dict(size=10, color="#222"),
        customdata=[
            ["city", c["city_id"], json.dumps({
                "city_id":          c["city_id"],
                "name":             c["name"],
                "safety_score":     c.get("safety_score"),
                "travel_advisory":  c.get("travel_advisory"),
                "population":       c.get("population"),
                "tourism_density":  c.get("tourism_density"),
                **({"city_archetype": c["city_archetype"]} if c.get("city_archetype") else {}),
            })]
            for c in cities
        ],
        showlegend=False,
        name="Cities",
        hovertemplate="<b>%{text}</b><extra></extra>",
    ))

    return _compute_bounds([c["lon"] for c in cities], [c["lat"] for c in cities], pad=0.35)


# ── City view ─────────────────────────────────────────────────────────────────

def _traces_city(fig, map_data, loc_map, city_id, layers, client):
    city_locs  = [l for l in map_data["locations"]  if l.get("city_id") == city_id]
    city_dists = [d for d in map_data["districts"]  if d.get("city_id") == city_id]

    # District territory fills
    for d in city_dists:
        pts = [(l["lon"], l["lat"]) for l in city_locs if l.get("district_id") == d["district_id"]]
        pts.append((d["lon"], d["lat"]))
        hull  = _hull(pts, pad=0.04)
        dtype = d.get("district_type", "")
        shade = _DISTRICT_TYPE_COLOR.get(dtype, "#888888")
        if hull:
            import plotly.graph_objects as go
            fig.add_trace(go.Scatter(
                x=[p[0] for p in hull],
                y=[p[1] for p in hull],
                mode="lines",
                fill="toself",
                fillcolor=_rgba(shade, 0.14),
                line=dict(color=shade, width=1.2),
                showlegend=False,
                hoverinfo="skip",
            ))

    # Location pins by layer
    _add_city_pins(fig, city_locs, layers, loc_map)

    # Area attraction polygons
    _add_area_polygons(fig, city_locs, layers)

    # Events
    if "🎭 Events" in layers:
        cache_key = f"tworld_map_evts_{city_id}"
        if cache_key not in st.session_state:
            try:
                evts = client.search_events(city_id=city_id)
                for e in evts:
                    venue = loc_map.get(e.get("venue_id", ""), {})
                    e["_lat"] = venue.get("lat")
                    e["_lon"] = venue.get("lon")
                st.session_state[cache_key] = evts
            except Exception:
                st.session_state[cache_key] = []
        evts_data = st.session_state[cache_key]
        valid_evts = [e for e in evts_data if e.get("_lat") is not None]
        if valid_evts:
            import plotly.graph_objects as go
            fig.add_trace(go.Scatter(
                x=[e["_lon"] + _jitter_x(500 + i) for i, e in enumerate(valid_evts)],
                y=[e["_lat"] + _jitter_y(500 + i) for i, e in enumerate(valid_evts)],
                mode="markers",
                marker=dict(size=10, symbol="star", color="#E15759",
                            line=dict(color="white", width=1)),
                text=[e.get("name", "") for e in valid_evts],
                customdata=[
                    ["event", e["event_id"], json.dumps({
                        "event_id":          e["event_id"],
                        "name":              e.get("name", ""),
                        "category":          e.get("category", ""),
                        "start_datetime":    e.get("start_datetime", ""),
                        "end_datetime":      e.get("end_datetime", ""),
                        "base_ticket_price": e.get("base_ticket_price", 0),
                        "requires_booking":  e.get("requires_booking", True),
                        "is_all_day_entry":  e.get("is_all_day_entry", False),
                        "description":       e.get("description", ""),
                    })]
                    for e in valid_evts
                ],
                showlegend=True, name="🎭 Events",
                hovertemplate="<b>%{text}</b><extra></extra>",
            ))

    # Transit network
    if "🚉 Transit" in layers:
        _draw_transit(fig, city_locs, city_id, layers, client)

    # Compute bounds
    all_lons = [l["lon"] for l in city_locs] + [d["lon"] for d in city_dists]
    all_lats = [l["lat"] for l in city_locs] + [d["lat"] for d in city_dists]
    return _compute_bounds(all_lons, all_lats, pad=0.30)


# ── Pin renderer ──────────────────────────────────────────────────────────────

def _add_city_pins(fig, city_locs, layers, loc_map):
    import plotly.graph_objects as go

    global_idx = 0
    for loc_type, (layer_label, symbol, color) in _PIN_CFG.items():
        if layer_label not in layers:
            continue
        pins = [l for l in city_locs if l.get("location_type") == loc_type]
        if not pins:
            continue

        xs = [p["lon"] + _jitter_x(global_idx + i) for i, p in enumerate(pins)]
        ys = [p["lat"] + _jitter_y(global_idx + i) for i, p in enumerate(pins)]
        global_idx += len(pins)

        fig.add_trace(go.Scatter(
            x=xs, y=ys,
            mode="markers",
            marker=dict(size=10, symbol=symbol, color=color,
                        line=dict(color="white", width=1)),
            text=[p.get("name", "") for p in pins],
            customdata=[
                [loc_type, p["location_id"], json.dumps(_loc_payload(p, loc_type))]
                for p in pins
            ],
            showlegend=True,
            name=layer_label,
            hovertemplate="<b>%{text}</b><extra></extra>",
        ))


# ── Area attraction polygons ──────────────────────────────────────────────────

def _add_area_polygons(fig, city_locs, layers):
    import plotly.graph_objects as go

    if "🌿 Area Attractions" not in layers:
        return

    for loc in city_locs:
        if loc.get("location_type") != "area_attraction":
            continue

        bp = loc.get("boundary_polygon")
        if bp:
            # boundary_polygon expected as list of {lon, lat} dicts or [lon, lat] pairs
            try:
                if isinstance(bp[0], dict):
                    poly_lons = [pt["lon"] for pt in bp] + [bp[0]["lon"]]
                    poly_lats = [pt["lat"] for pt in bp] + [bp[0]["lat"]]
                else:
                    poly_lons = [pt[0] for pt in bp] + [bp[0][0]]
                    poly_lats = [pt[1] for pt in bp] + [bp[0][1]]
                fig.add_trace(go.Scatter(
                    x=poly_lons, y=poly_lats,
                    mode="lines",
                    fill="toself",
                    fillcolor=_rgba("#00897B", 0.22),
                    line=dict(color="#00897B", width=1.5),
                    showlegend=False,
                    hoverinfo="skip",
                ))
            except (IndexError, KeyError, TypeError):
                pass

        entrances = loc.get("entrances", [])
        if entrances:
            fig.add_trace(go.Scatter(
                x=[e.get("lon", loc["lon"]) for e in entrances],
                y=[e.get("lat", loc["lat"]) for e in entrances],
                mode="markers",
                marker=dict(size=9, symbol="star", color="#00897B",
                            line=dict(color="white", width=1)),
                text=[e.get("name", "Entrance") for e in entrances],
                customdata=[
                    ["entrance", e.get("entrance_id", ""), json.dumps({
                        "entrance_id":      e.get("entrance_id", ""),
                        "name":             e.get("name", "Entrance"),
                        "is_main_entrance": e.get("is_main_entrance", False),
                        "accessible":       e.get("accessible", True),
                    })]
                    for e in entrances
                ],
                showlegend=False,
                hovertemplate="<b>%{text}</b><extra></extra>",
            ))


# ── Transit network drawing ───────────────────────────────────────────────────

def _draw_transit(fig, city_locs, city_id, layers, client):
    import plotly.graph_objects as go

    cache_key = f"tworld_map_transit_{city_id}"
    if cache_key not in st.session_state:
        try:
            lines = client.get_transit_lines(city_id)
            st.session_state[cache_key] = lines
        except Exception:
            st.session_state[cache_key] = []
    transit_lines = st.session_state[cache_key]

    # Build stop location lookup
    stop_locs = {l["location_id"]: l for l in city_locs if l.get("location_type") == "transit_stop"}

    # Draw each line as polyline
    for line in transit_lines:
        coords = [
            (stop_locs[sid]["lon"], stop_locs[sid]["lat"])
            for sid in line.get("stop_ids", [])
            if sid in stop_locs
        ]
        if len(coords) < 2:
            continue
        color = line.get("color", "#888888")
        fig.add_trace(go.Scatter(
            x=[c[0] for c in coords],
            y=[c[1] for c in coords],
            mode="lines",
            line=dict(color=color, width=3),
            showlegend=False,
            hoverinfo="skip",
            name=line.get("name", "Transit Line"),
        ))

    # Draw stop markers — split into regular and interchange for per-group styling
    all_stops = list(stop_locs.values())
    if not all_stops:
        return

    def stop_color(s):
        for line in transit_lines:
            if s["location_id"] in line.get("stop_ids", []):
                return line.get("color", "#888888")
        return "#888888"

    regular     = [s for s in all_stops if not s.get("is_interchange")]
    interchange = [s for s in all_stops if s.get("is_interchange")]

    for group, size, border_color, border_w, legend_name in [
        (regular,     7,  "white", 1,   "🚉 Transit Stops"),
        (interchange, 11, "black", 1.5, "🔀 Interchanges"),
    ]:
        if not group:
            continue
        grp_colors = [stop_color(s) for s in group]
        fig.add_trace(go.Scatter(
            x=[s["lon"] for s in group],
            y=[s["lat"] for s in group],
            mode="markers",
            marker=dict(
                size=size,
                color=grp_colors,
                symbol="circle",
                line=dict(color=border_color, width=border_w),
            ),
            text=[s.get("name", "") for s in group],
            customdata=[
                ["transit_stop", s["location_id"], json.dumps({
                    "location_id":   s["location_id"],
                    "name":          s.get("name", ""),
                    "line_ids":      s.get("line_ids", []),
                    "is_interchange": s.get("is_interchange", False),
                    "accessible":    s.get("accessible", True),
                })]
                for s in group
            ],
            showlegend=True, name=legend_name,
            hovertemplate="<b>%{text}</b><extra></extra>",
        ))


# ══════════════════════════════════════════════════════════════════════════════
# Scale bar
# ══════════════════════════════════════════════════════════════════════════════

def _add_scale_bar(fig, xmin, xmax, ymin, ymax):
    import plotly.graph_objects as go

    xspan = xmax - xmin
    yspan = ymax - ymin
    if xspan <= 0 or yspan <= 0:
        return

    lat_c = (ymin + ymax) / 2
    km_per_deg = 111.32 * math.cos(math.radians(lat_c))

    # Pick the largest d_km that fits in 25% of the visible width
    d_km = 1
    for candidate in [1, 2, 5, 10, 20, 50, 100]:
        if candidate / km_per_deg < xspan * 0.25:
            d_km = candidate

    bar_deg = d_km / km_per_deg
    x0    = xmin + xspan * 0.04
    x1    = x0 + bar_deg
    y_bar = ymin + yspan * 0.05
    y_top = y_bar + yspan * 0.008

    # Bar line
    fig.add_trace(go.Scatter(
        x=[x0, x1], y=[y_bar, y_bar],
        mode="lines", line=dict(color="black", width=3),
        showlegend=False, hoverinfo="skip",
    ))
    # Tick marks at ends
    for x_tick in [x0, x1]:
        fig.add_trace(go.Scatter(
            x=[x_tick, x_tick], y=[y_bar, y_top],
            mode="lines", line=dict(color="black", width=2),
            showlegend=False, hoverinfo="skip",
        ))
    # Label
    fig.add_annotation(
        x=(x0 + x1) / 2, y=y_top + yspan * 0.012,
        text=f"{d_km} km",
        showarrow=False, font=dict(size=10, color="black"),
        xanchor="center",
        bgcolor="rgba(255,255,255,0.75)",
        bordercolor="black", borderwidth=1,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Selection handling
# ══════════════════════════════════════════════════════════════════════════════

def _handle_selection(sel) -> None:
    if not sel or not getattr(sel, "selection", None):
        return
    pts = getattr(sel.selection, "points", [])
    if not pts:
        return
    pt = pts[0]
    cd = pt.get("customdata") or []
    if not cd or len(cd) < 3:
        return
    item_type, item_id, raw = cd[0], cd[1], cd[2]
    try:
        item_data = json.loads(raw) if isinstance(raw, str) else (raw or {})
    except Exception:
        item_data = {}
    st.session_state["tworld_map_item"] = {"_type": item_type, "_id": item_id, **item_data}
    st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# Detail panel
# ══════════════════════════════════════════════════════════════════════════════

def _render_detail_panel(city_map: dict) -> None:
    item = st.session_state.get("tworld_map_item")
    if not item:
        st.caption("👆 Click any location pin to see details.")
        return

    itype = item.get("_type", "")
    with st.container(border=True):
        if itype == "city":
            _panel_city(item)
        elif itype == "district":
            _panel_district(item)
        elif itype == "hotel":
            _panel_hotel(item)
        elif itype == "restaurant":
            _panel_restaurant(item)
        elif itype in ("attraction", "area_attraction"):
            _panel_attraction(item)
        elif itype == "event":
            _panel_event(item)
        elif itype == "service_venue":
            _panel_service_venue(item)
        elif itype == "public_amenity":
            _panel_public_amenity(item)
        elif itype == "transit_stop":
            _panel_transit_stop(item)
        elif itype == "transport_hub":
            _panel_transport_hub(item)
        elif itype == "entrance":
            _panel_entrance(item)
        else:
            st.caption(f"**{item.get('name', item.get('_id', ''))}**")
            st.caption(f"Type: {itype}")


# ── Panel renderers ───────────────────────────────────────────────────────────

def _panel_city(item: dict) -> None:
    safety = item.get("safety_score") or 0
    emoji  = "🟢" if safety >= 0.75 else ("🟡" if safety >= 0.55 else ("🟠" if safety >= 0.35 else "🔴"))
    st.markdown(f"### 🏙️ {item.get('name', 'City')}")
    arch = item.get("city_archetype")
    if arch:
        st.caption(f"**{arch.replace('_', ' ').title()}**")
    c1, c2 = st.columns(2)
    c1.metric("Safety", f"{emoji} {safety:.2f}")
    pop = item.get("population")
    if pop is not None:
        c2.metric("Population", f"{pop:,}")
    advisory = item.get("travel_advisory", "")
    if advisory:
        if safety >= 0.75:
            st.info(advisory)
        elif safety >= 0.35:
            st.warning(advisory)
        else:
            st.error(advisory)
    vibe = item.get("vibe_summary", "")
    if vibe:
        st.write(vibe)


def _panel_district(item: dict) -> None:
    safety = item.get("safety_score") or 0
    s_em   = "🟢" if safety >= 0.75 else ("🟡" if safety >= 0.55 else "🔴")
    st.markdown(f"### 📍 {item.get('name', 'District')}")
    st.caption(item.get("district_type", "").replace("_", " ").title())
    c1, c2 = st.columns(2)
    c1.metric("Safety",      f"{s_em} {safety:.2f}")
    c1.metric("Walkability", f"{item.get('walkability_score', 0):.2f}")
    c2.metric("Cost index",  f"{item.get('cost_index', 1):.2f}×")
    desc = item.get("description", "")
    if desc:
        st.write(desc)


def _panel_hotel(item: dict) -> None:
    stars  = "⭐" * int(item.get("star_rating") or 0)
    rating = item.get("average_rating")
    price  = item.get("price_per_night")
    st.markdown(f"### 🏨 {item.get('name', 'Hotel')}")
    if stars:
        st.caption(stars)
    if price is not None:
        st.metric("From", f"${price:.0f} / night")
    if rating is not None:
        em = "🟢" if rating >= 4 else ("🟡" if rating >= 3 else "🔴")
        st.caption(f"{em} {rating:.1f} / 5  ({item.get('review_count', 0)} reviews)")
    desc = item.get("description", "")
    if desc:
        st.write(desc)


def _panel_restaurant(item: dict) -> None:
    cuisines = ", ".join(item.get("cuisine_types") or [])
    avg      = item.get("average_spend")
    rating   = item.get("average_rating")
    michelin = int(item.get("michelin_stars") or 0)
    st.markdown(f"### 🍽️ {item.get('name', 'Restaurant')}")
    if michelin:
        st.caption("⭐" * michelin + " Michelin")
    if cuisines:
        st.caption(f"🍴 {cuisines}")
    if avg is not None:
        st.metric("Avg spend", f"${avg:.0f} / person")
    if rating is not None:
        em = "🟢" if rating >= 4 else ("🟡" if rating >= 3 else "🔴")
        st.caption(f"{em} {rating:.1f} / 5  ({item.get('review_count', 0)} reviews)")
    desc = item.get("description", "")
    if desc:
        st.write(desc)


def _panel_attraction(item: dict) -> None:
    rating = item.get("average_rating")
    st.markdown(f"### 🏛️ {item.get('name', 'Attraction')}")
    cat = item.get("category")
    if cat:
        st.caption(f"**{cat.replace('_', ' ').title()}**")
    c1, c2 = st.columns(2)
    duration = item.get("duration_hours")
    if duration is not None:
        c1.metric("Duration", f"{duration}h")
    ticket = item.get("ticket_price")
    if ticket is not None:
        c2.metric("Ticket", f"${ticket:.2f}" if ticket else "Free")
    ws = item.get("weather_sensitivity")
    if ws is not None:
        st.caption(f"Weather sensitivity: {ws:.1f}")
    if rating is not None:
        em = "🟢" if rating >= 4 else ("🟡" if rating >= 3 else "🔴")
        st.caption(f"{em} {rating:.1f} / 5  ({item.get('review_count', 0)} reviews)")
    sub_areas = item.get("sub_areas", [])
    if sub_areas:
        st.caption("Sub-areas: " + ", ".join(str(s) for s in sub_areas))
    entrances = item.get("entrances", [])
    if entrances:
        st.caption(f"{len(entrances)} entrance(s)")
    desc = item.get("description", "")
    if desc:
        st.write(desc)


def _panel_event(item: dict) -> None:
    start   = item.get("start_datetime", "")
    end     = item.get("end_datetime", "")
    s_time  = start[11:16] if len(start) >= 16 else ""
    e_time  = end[11:16]   if len(end)   >= 16 else ""
    price   = item.get("base_ticket_price", 0)
    all_day = item.get("is_all_day_entry", False)
    booking = item.get("requires_booking", True)
    st.markdown(f"### 🎭 {item.get('name', 'Event')}")
    st.caption(item.get("category", "").replace("_", " ").title())
    if start:
        st.caption(f"📅 {start[:10]}")
    if s_time:
        time_label = f"🕐 {s_time}"
        if e_time:
            time_label += f"–{e_time}"
        if all_day:
            time_label += " (all-day entry)"
        st.caption(time_label)
    if price == 0:
        st.success("🆓 Free entry")
    else:
        st.metric("Ticket", f"${price:.2f}")
    if not booking:
        st.caption("🚶 Walk-in welcome")
    desc = item.get("description", "")
    if desc:
        st.write(desc)


def _panel_service_venue(item: dict) -> None:
    st.markdown(f"### 🎮 {item.get('name', 'Service Venue')}")
    cat = item.get("category")
    if cat:
        st.caption(f"**{cat.replace('_', ' ').title()}**")
    open_t  = item.get("opening_time")
    close_t = item.get("closing_time")
    if open_t or close_t:
        st.caption(f"🕐 {open_t or '?'} – {close_t or '?'}")
    avg_spend = item.get("average_spend_per_person")
    if avg_spend is not None:
        st.metric("Avg spend", f"${avg_spend:.0f} / person")
    age_r = item.get("age_restriction")
    if age_r:
        st.caption(f"🔞 Age restriction: {age_r}+")
    if item.get("requires_reservation"):
        st.info("Reservation required")
    desc = item.get("description", "")
    if desc:
        st.write(desc)


def _panel_public_amenity(item: dict) -> None:
    st.markdown(f"### 🏥 {item.get('name', 'Amenity')}")
    atype = item.get("amenity_type")
    if atype:
        st.caption(f"**{atype.replace('_', ' ').title()}**")
    if item.get("is_24_hours"):
        st.success("🕐 Open 24 hours")
    phone = item.get("phone_number", "")
    if phone:
        st.caption(f"📞 {phone}")
    if item.get("emergency_services"):
        st.error("🚨 Emergency services")
    desc = item.get("description", "")
    if desc:
        st.write(desc)


def _panel_transit_stop(item: dict) -> None:
    st.markdown(f"### 🚉 {item.get('name', 'Transit Stop')}")
    line_ids = item.get("line_ids", [])
    if line_ids:
        st.caption("Lines: " + ", ".join(str(l) for l in line_ids))
    if item.get("is_interchange"):
        st.info("🔀 Interchange station")
    if item.get("accessible", True):
        st.caption("♿ Accessible")
    else:
        st.caption("❌ Not accessible")


def _panel_transport_hub(item: dict) -> None:
    st.markdown(f"### 🚏 {item.get('name', 'Transport Hub')}")
    hub_type = item.get("hub_type")
    if hub_type:
        st.caption(f"**{hub_type.replace('_', ' ').title()}**")
    iata = item.get("iata_code")
    if iata:
        st.caption(f"IATA: **{iata}**")
    desc = item.get("description", "")
    if desc:
        st.write(desc)


def _panel_entrance(item: dict) -> None:
    st.markdown(f"### 🚪 {item.get('name', 'Entrance')}")
    if item.get("is_main_entrance"):
        st.success("Main entrance")
    if item.get("accessible", True):
        st.caption("♿ Accessible")
    else:
        st.caption("❌ Not accessible")


# ══════════════════════════════════════════════════════════════════════════════
# Data helpers
# ══════════════════════════════════════════════════════════════════════════════

def _loc_payload(loc: dict, loc_type: str) -> dict:
    """Minimal dict for the detail panel (keep customdata JSON lean)."""
    base = {
        "location_id":    loc["location_id"],
        "name":           loc.get("name", ""),
        "description":    loc.get("description", ""),
        "average_rating": loc.get("average_rating"),
        "review_count":   loc.get("review_count", 0),
    }
    if loc_type == "hotel":
        base.update({
            "star_rating":    loc.get("star_rating"),
            "price_per_night": loc.get("price_per_night"),
            "amenities":      loc.get("amenities", []),
        })
    elif loc_type == "restaurant":
        base.update({
            "cuisine_types":       loc.get("cuisine_types", []),
            "average_spend":       loc.get("average_spend"),
            "michelin_stars":      loc.get("michelin_stars", 0),
            "reservation_required": loc.get("reservation_required", False),
        })
    elif loc_type in ("attraction", "area_attraction"):
        base.update({
            "category":           loc.get("category"),
            "duration_hours":     loc.get("duration_hours"),
            "ticket_price":       loc.get("ticket_price", 0),
            "weather_sensitivity": loc.get("weather_sensitivity", 0),
            "sub_areas":          loc.get("sub_areas", []),
            "entrances":          loc.get("entrances", []),
        })
    elif loc_type == "service_venue":
        base.update({
            "category":                loc.get("category"),
            "opening_time":            loc.get("opening_time"),
            "closing_time":            loc.get("closing_time"),
            "average_spend_per_person": loc.get("average_spend_per_person"),
            "age_restriction":         loc.get("age_restriction"),
            "requires_reservation":    loc.get("requires_reservation", False),
        })
    elif loc_type == "public_amenity":
        base.update({
            "amenity_type":      loc.get("amenity_type"),
            "is_24_hours":       loc.get("is_24_hours", False),
            "phone_number":      loc.get("phone_number", ""),
            "emergency_services": loc.get("emergency_services", False),
        })
    elif loc_type == "transit_stop":
        base.update({
            "line_ids":       loc.get("line_ids", []),
            "is_interchange": loc.get("is_interchange", False),
            "accessible":     loc.get("accessible", True),
        })
    elif loc_type == "transport_hub":
        base.update({
            "hub_type":  loc.get("hub_type"),
            "iata_code": loc.get("iata_code"),
        })
    return base


# ══════════════════════════════════════════════════════════════════════════════
# Geometry helpers
# ══════════════════════════════════════════════════════════════════════════════

def _jitter_x(i: int, scale: float = 0.004) -> float:
    """Deterministic x-offset on an Archimedean spiral so clustered pins don't stack."""
    angle = i * 2.399963  # golden angle (radians)
    return scale * math.sqrt(i + 1) * math.cos(angle)


def _jitter_y(i: int, scale: float = 0.004) -> float:
    angle = i * 2.399963
    return scale * math.sqrt(i + 1) * math.sin(angle)


def _hull(pts: list, pad: float = 0.15) -> list:
    """
    Compute a padded convex hull. Falls back to bounding box when scipy is
    unavailable, and handles degenerate 1- or 2-point cases.
    """
    unique = list({(round(x, 6), round(y, 6)) for x, y in pts})
    if not unique:
        return []

    if len(unique) == 1:
        x0, y0 = unique[0]
        r = max(0.06, pad)
        return [
            (x0 + r * math.cos(2 * math.pi * i / 20),
             y0 + r * math.sin(2 * math.pi * i / 20))
            for i in range(21)
        ]

    if len(unique) == 2:
        (x0, y0), (x1, y1) = unique[0], unique[1]
        dx = max(abs(x1 - x0) * pad, 0.05)
        dy = max(abs(y1 - y0) * pad, 0.05)
        return [
            (x0 - dx, y0 - dy), (x1 + dx, y0 - dy),
            (x1 + dx, y1 + dy), (x0 - dx, y1 + dy),
            (x0 - dx, y0 - dy),
        ]

    try:
        import numpy as np
        from scipy.spatial import ConvexHull

        arr  = np.array(unique)
        hull = ConvexHull(arr)
        verts    = arr[hull.vertices]
        centroid = verts.mean(axis=0)
        expanded = [centroid + (v - centroid) * (1 + pad) for v in verts]
        expanded.append(expanded[0])
        return [(float(p[0]), float(p[1])) for p in expanded]

    except Exception:
        xs = [p[0] for p in unique]
        ys = [p[1] for p in unique]
        dx = max((max(xs) - min(xs)) * pad, 0.05)
        dy = max((max(ys) - min(ys)) * pad, 0.05)
        return [
            (min(xs) - dx, min(ys) - dy), (max(xs) + dx, min(ys) - dy),
            (max(xs) + dx, max(ys) + dy), (min(xs) - dx, max(ys) + dy),
            (min(xs) - dx, min(ys) - dy),
        ]


def _arc(x0: float, y0: float, x1: float, y1: float, n: int = 25) -> tuple:
    """Quadratic bezier arc. Returns (x_list, y_list) with trailing None to break polylines."""
    import numpy as np

    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    dx, dy = x1 - x0, y1 - y0
    dist   = max((dx ** 2 + dy ** 2) ** 0.5, 1e-9)
    nx, ny = -dy / dist, dx / dist                   # unit perpendicular
    cx, cy = mx + nx * dist * 0.25, my + ny * dist * 0.25

    t  = np.linspace(0, 1, n)
    bx = (1 - t) ** 2 * x0 + 2 * (1 - t) * t * cx + t ** 2 * x1
    by = (1 - t) ** 2 * y0 + 2 * (1 - t) * t * cy + t ** 2 * y1
    return list(bx) + [None], list(by) + [None]


def _rgba(hex_color: str, alpha: float) -> str:
    """Convert '#RRGGBB' to 'rgba(r,g,b,alpha)'."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _lighten(hex_color: str, factor: float) -> str:
    """Blend hex colour toward white by factor (0 = no change, 1 = white)."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    r = int(r + (255 - r) * factor)
    g = int(g + (255 - g) * factor)
    b = int(b + (255 - b) * factor)
    return f"#{r:02x}{g:02x}{b:02x}"


def _compute_bounds(lons: list, lats: list, pad: float = 0.3):
    if not lons or not lats:
        return -1, 1, -1, 1
    lon_span = max(max(lons) - min(lons), 0.05)
    lat_span = max(max(lats) - min(lats), 0.05)
    xmin = min(lons) - lon_span * pad
    xmax = max(lons) + lon_span * pad
    ymin = min(lats) - lat_span * pad
    ymax = max(lats) + lat_span * pad
    return xmin, xmax, ymin, ymax


# ══════════════════════════════════════════════════════════════════════════════
# Route planner (preserved verbatim)
# ══════════════════════════════════════════════════════════════════════════════

def _render_route_planner(client: TravelWorldClient) -> None:
    import datetime

    prefs    = state.get_preferences()
    world_id = st.session_state.get(state.WORLD_ID_KEY)

    cities: list[dict] = []
    if world_id:
        try:
            cities = client.list_cities(world_id)
        except APIError:
            pass

    if cities:
        city_ids    = [c["city_id"] for c in cities]
        city_labels = {c["city_id"]: c["name"] for c in cities}

        saved_o = st.session_state.get(state.MAP_ORIGIN_KEY, prefs.get("origin_city_id", ""))
        saved_d = st.session_state.get(
            state.MAP_DEST_KEY,
            (prefs.get("destination_city_ids") or [prefs.get("destination_city_id", "")])[0],
        )
        origin_id = st.selectbox(
            "Origin City", city_ids,
            index=city_ids.index(saved_o) if saved_o in city_ids else 0,
            format_func=lambda x: city_labels.get(x, x),
            key="rp_origin",
        )
        dest_id = st.selectbox(
            "Destination City", city_ids,
            index=city_ids.index(saved_d) if saved_d in city_ids else (1 if len(city_ids) > 1 else 0),
            format_func=lambda x: city_labels.get(x, x),
            key="rp_dest",
        )
    else:
        origin_id = st.text_input("Origin City ID", key="rp_origin",
                                  value=st.session_state.get(state.MAP_ORIGIN_KEY, ""))
        dest_id   = st.text_input("Destination City ID", key="rp_dest",
                                  value=st.session_state.get(state.MAP_DEST_KEY, ""))

    st.session_state[state.MAP_ORIGIN_KEY] = origin_id
    st.session_state[state.MAP_DEST_KEY]   = dest_id

    today      = datetime.date.today()
    dep_date   = st.date_input("Departure Date", value=today, min_value=today, key="rp_date")
    dep_time   = st.time_input("Departure Time", value=datetime.time(9, 0), key="rp_time")
    dep_dt_str = datetime.datetime.combine(dep_date, dep_time).isoformat()

    if st.button("Compare Routes", type="primary", key="rp_compare"):
        if not origin_id or not dest_id:
            st.warning("Enter both origin and destination.")
            return
        with st.spinner("Fetching routes…"):
            try:
                results = client.compare_routes(
                    origin_location_id=origin_id,
                    destination_location_id=dest_id,
                    departure_datetime=dep_dt_str,
                )
                st.session_state[state.ROUTE_RESULTS_KEY] = results
            except APIError as e:
                st.error(f"Route comparison failed: {e.message}")

    results = st.session_state.get(state.ROUTE_RESULTS_KEY)
    if results:
        from travel_world.frontend.components.route_panel import render_route_comparison
        routes = results.get("routes", []) if isinstance(results, dict) else []
        if routes:
            render_route_comparison(routes)
        else:
            st.info("No route options returned.")
