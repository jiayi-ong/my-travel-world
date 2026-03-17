"""
Map tab: interactive world visualisation with three zoom levels.

Level 1 – World   : city territories (coloured convex hulls) + optional flight arcs.
                    Click a city dot to drill in.
Level 2 – City    : district territories + top entity pins (hotels, restaurants, attractions).
                    Click a district square to drill in; click a pin for detail.
Level 3 – District: all venue pins (hotels, restaurants, events/attractions).
                    Click a pin for detail.

Detail panel (right column) shows the clicked item's card.
Back button and breadcrumb allow upward navigation.
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

# ── District type colours (distinct per type to reduce visual overlap noise) ──
_DISTRICT_TYPE_COLOR = {
    "touristic":   "#F28E2B",
    "residential": "#76B7B2",
    "nightlife":   "#E15759",
    "business":    "#4E79A7",
    "cultural":    "#B07AA1",
    "historic":    "#59A14F",
    "waterfront":  "#17BECF",
}

# ── Category options shown in the multi-select filter ────────────────────────
_CAT_OPTIONS = ["Hotels", "Restaurants", "Events", "Attractions"]

# ── Session-state keys (all prefixed tworld_map_) ────────────────────────────
_K_LEVEL = "tworld_map_level"
_K_CITY  = "tworld_map_city_id"
_K_DIST  = "tworld_map_district_id"
_K_ITEM  = "tworld_map_selected_item"
_K_ARCS  = "tworld_map_show_flights"
_K_CATS  = "tworld_map_categories"

_LVL_WORLD = "world"
_LVL_CITY  = "city"
_LVL_DIST  = "district"


def _init() -> None:
    for k, v in [
        (_K_LEVEL, _LVL_WORLD),
        (_K_CITY,  None),
        (_K_DIST,  None),
        (_K_ITEM,  None),
        (_K_ARCS,  True),
        (_K_CATS,  list(_CAT_OPTIONS)),
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

    city_map   = {c["city_id"]:   c for c in map_data["cities"]}
    dist_map   = {d["district_id"]: d for d in map_data["districts"]}
    loc_map    = {l["location_id"]: l for l in map_data["locations"]}
    city_color = {
        c["city_id"]: _PALETTE[i % len(_PALETTE)]
        for i, c in enumerate(map_data["cities"])
    }

    _render_controls(city_map, dist_map)

    col_map, col_detail = st.columns([7, 3], gap="small")

    with col_map:
        level    = st.session_state[_K_LEVEL]
        sel_dist = st.session_state[_K_DIST]
        events: list[dict] = []
        if level == _LVL_DIST and sel_dist:
            dist = dist_map.get(sel_dist, {})
            if dist:
                events = _fetch_city_events(client, dist["city_id"], loc_map)

        fig = _build_figure(map_data, city_map, dist_map, loc_map, city_color, events)

        # Key changes on every navigation step → resets Plotly selection state
        chart_key = (
            f"map_{level}_{st.session_state[_K_CITY]}_{st.session_state[_K_DIST]}"
        )
        sel = st.plotly_chart(
            fig,
            use_container_width=True,
            on_select="rerun",
            selection_mode="points",
            key=chart_key,
        )
        _handle_selection(sel)

    with col_detail:
        _render_detail_panel(city_map, dist_map)

    # Legacy route planner preserved in a collapsed expander
    with st.expander("🗺️ Route Planner", expanded=False):
        _render_route_planner(client)


# ══════════════════════════════════════════════════════════════════════════════
# Controls: breadcrumb + back + flight toggle + category filter
# ══════════════════════════════════════════════════════════════════════════════

def _render_controls(city_map: dict, dist_map: dict) -> None:
    level = st.session_state[_K_LEVEL]

    crumb = "🌍 World"
    if level in (_LVL_CITY, _LVL_DIST):
        city = city_map.get(st.session_state[_K_CITY], {})
        crumb += f" › **{city.get('name', '')}**"
    if level == _LVL_DIST:
        dist = dist_map.get(st.session_state[_K_DIST], {})
        crumb += f" › {dist.get('name', '')}"
    st.caption(crumb)

    c1, c2, c3 = st.columns([1, 1, 3])
    with c1:
        st.session_state[_K_ARCS] = st.toggle(
            "✈ Flight arcs",
            value=st.session_state[_K_ARCS],
            key="map_toggle_arcs",
        )
    with c2:
        if level != _LVL_WORLD and st.button("⬅ Back", key="map_back"):
            if level == _LVL_DIST:
                st.session_state[_K_LEVEL] = _LVL_CITY
                st.session_state[_K_DIST]  = None
            else:
                st.session_state[_K_LEVEL] = _LVL_WORLD
                st.session_state[_K_CITY]  = None
            st.session_state[_K_ITEM] = None
            st.rerun()
    with c3:
        if level != _LVL_WORLD:
            st.session_state[_K_CATS] = st.multiselect(
                "Categories",
                options=_CAT_OPTIONS,
                default=st.session_state[_K_CATS],
                key="map_cat_ms",
                label_visibility="collapsed",
            )


# ══════════════════════════════════════════════════════════════════════════════
# Click / selection handling
# ══════════════════════════════════════════════════════════════════════════════

def _handle_selection(sel) -> None:
    if not sel or not getattr(sel, "selection", None):
        return
    pts = getattr(sel.selection, "points", [])
    if not pts:
        return

    pt = pts[0]
    cd = pt.get("customdata") or []
    if not cd:
        return

    item_type = cd[0] if len(cd) > 0 else None
    item_id   = cd[1] if len(cd) > 1 else None
    raw       = cd[2] if len(cd) > 2 else "{}"
    try:
        item_data = json.loads(raw) if isinstance(raw, str) else (raw or {})
    except (json.JSONDecodeError, TypeError):
        item_data = {}

    if item_type == "city":
        st.session_state[_K_LEVEL] = _LVL_CITY
        st.session_state[_K_CITY]  = item_id
        st.session_state[_K_DIST]  = None
        st.session_state[_K_ITEM]  = {"_type": "city", **item_data}
        st.rerun()
    elif item_type == "district":
        st.session_state[_K_LEVEL] = _LVL_DIST
        st.session_state[_K_DIST]  = item_id
        st.session_state[_K_ITEM]  = {"_type": "district", **item_data}
        st.rerun()
    elif item_type in ("hotel", "restaurant", "event", "attraction", "event_venue",
                       "transport_hub", "landmark"):
        st.session_state[_K_ITEM] = {"_type": item_type, **item_data}
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# Figure builder – dispatches to the three level renderers
# ══════════════════════════════════════════════════════════════════════════════

def _build_figure(map_data, city_map, dist_map, loc_map, city_color, events):
    import plotly.graph_objects as go

    fig = go.Figure()
    fig.update_layout(
        paper_bgcolor="#DCDCDC",
        plot_bgcolor="#F4F2EE",
        xaxis=dict(
            showgrid=False, showticklabels=False, zeroline=False,
            fixedrange=False, constrain="domain",
        ),
        yaxis=dict(
            showgrid=False, showticklabels=False, zeroline=False,
            fixedrange=False, scaleanchor="x", scaleratio=1,
        ),
        margin=dict(l=4, r=4, t=4, b=4),
        height=560,
        showlegend=True,
        legend=dict(
            orientation="h", y=-0.04, x=0, bgcolor="rgba(0,0,0,0)", font=dict(size=11),
        ),
        dragmode="zoom",
        hovermode="closest",
        uirevision="map",   # preserve user pan/zoom across non-navigation rerenders
    )

    level    = st.session_state[_K_LEVEL]
    sel_city = st.session_state[_K_CITY]
    sel_dist = st.session_state[_K_DIST]
    cats     = set(st.session_state[_K_CATS])

    if level == _LVL_WORLD:
        _traces_world(fig, map_data, city_color)
    elif level == _LVL_CITY:
        _traces_city(fig, map_data, loc_map, sel_city, city_color, cats)
    elif level == _LVL_DIST:
        _traces_district(fig, map_data, dist_map, loc_map, sel_dist, city_color, cats, events)

    return fig


# ── Level 1: World ────────────────────────────────────────────────────────────

def _traces_world(fig, map_data, city_color) -> None:
    import plotly.graph_objects as go

    cities    = map_data["cities"]
    districts = map_data["districts"]
    routes    = map_data["flight_routes"]
    city_map  = {c["city_id"]: c for c in cities}

    # City territory hulls (convex hull of district centroids)
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
    if st.session_state[_K_ARCS]:
        ax: list = []
        ay: list = []
        for r in routes:
            oc = city_map.get(r["origin_city_id"])
            dc = city_map.get(r["dest_city_id"])
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

    # City dots (labelled click targets)
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
                "city_id":        c["city_id"],
                "name":           c["name"],
                "safety_score":   c["safety_score"],
                "travel_advisory": c["travel_advisory"],
                "population":     c["population"],
                "tourism_density": c["tourism_density"],
            })]
            for c in cities
        ],
        showlegend=False,
        name="Cities",
        hovertemplate="<b>%{text}</b><extra></extra>",
    ))

    _frame(fig, [c["lon"] for c in cities], [c["lat"] for c in cities], pad=0.4)


# ── Level 2: City ─────────────────────────────────────────────────────────────

def _traces_city(fig, map_data, loc_map, sel_city, city_color, cats) -> None:
    import plotly.graph_objects as go

    base_color = city_color.get(sel_city, "#4E79A7")
    city_dists = [d for d in map_data["districts"] if d["city_id"] == sel_city]
    city_locs  = [l for l in map_data["locations"] if l["city_id"] == sel_city]

    # District territory fills — each district uses its type colour to distinguish overlapping areas
    for d in city_dists:
        pts = [(l["lon"], l["lat"]) for l in city_locs if l["district_id"] == d["district_id"]]
        pts.append((d["lon"], d["lat"]))
        hull  = _hull(pts, pad=0.04)
        dtype = d.get("district_type", "")
        shade = _DISTRICT_TYPE_COLOR.get(dtype, _lighten(base_color, 0.35))
        if hull:
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

    # District click dots
    fig.add_trace(go.Scatter(
        x=[d["lon"] for d in city_dists],
        y=[d["lat"] for d in city_dists],
        mode="markers+text",
        marker=dict(
            size=13,
            color=base_color,
            symbol="square",
            line=dict(color="white", width=1.5),
        ),
        text=[d["name"] for d in city_dists],
        textposition="top center",
        textfont=dict(size=9, color="#222"),
        customdata=[
            ["district", d["district_id"], json.dumps(d)]
            for d in city_dists
        ],
        showlegend=True,
        name="Districts",
        hovertemplate="<b>%{text}</b><extra></extra>",
    ))

    # Top-5 entity pins per visible category (reduced to keep city view readable)
    _add_pins(fig, city_locs, cats, top_n=5)

    _frame(fig, [d["lon"] for d in city_dists], [d["lat"] for d in city_dists], pad=0.38)


# ── Level 3: District ─────────────────────────────────────────────────────────

def _traces_district(fig, map_data, dist_map, loc_map, sel_dist, city_color, cats, events) -> None:
    import plotly.graph_objects as go

    dist      = dist_map.get(sel_dist, {})
    city_id   = dist.get("city_id", "")
    base_color = city_color.get(city_id, "#4E79A7")
    dist_locs  = [l for l in map_data["locations"] if l["district_id"] == sel_dist]

    # District boundary highlight
    pts  = [(l["lon"], l["lat"]) for l in dist_locs] + [(dist.get("lon", 0), dist.get("lat", 0))]
    hull = _hull(pts, pad=0.03)
    if hull:
        fig.add_trace(go.Scatter(
            x=[p[0] for p in hull],
            y=[p[1] for p in hull],
            mode="lines",
            fill="toself",
            fillcolor=_rgba(base_color, 0.06),
            line=dict(color=base_color, width=2),
            showlegend=False,
            hoverinfo="skip",
        ))

    # All entity pins in this district — jitter applied to separate clustered markers
    _add_pins(fig, dist_locs, cats, top_n=None, jitter=True)

    # Events / attractions in district
    ev_cats: set = set()
    if "Events" in cats:
        ev_cats.update(["music", "sports", "food", "theater", "art", "festival", "other", "conference"])
    if "Attractions" in cats:
        ev_cats.add("attraction")

    if ev_cats:
        dist_events = [
            e for e in events
            if e.get("_district_id") == sel_dist
            and e.get("_lat") is not None
            and (e.get("category", "").lower() in ev_cats)
        ]
        if dist_events:
            ev_xs = [e["_lon"] + _jitter_x(500 + i) for i, e in enumerate(dist_events)]
            ev_ys = [e["_lat"] + _jitter_y(500 + i) for i, e in enumerate(dist_events)]
            fig.add_trace(go.Scatter(
                x=ev_xs,
                y=ev_ys,
                mode="markers",
                marker=dict(size=10, symbol="star", color="#E15759",
                            line=dict(color="white", width=1)),
                text=[e.get("name", "") for e in dist_events],
                customdata=[
                    ["event", e["event_id"], json.dumps({
                        "event_id":         e["event_id"],
                        "name":             e.get("name", ""),
                        "category":         e.get("category", ""),
                        "start_datetime":   e.get("start_datetime", ""),
                        "end_datetime":     e.get("end_datetime", ""),
                        "base_ticket_price": e.get("base_ticket_price", 0),
                        "requires_booking": e.get("requires_booking", True),
                        "is_all_day_entry": e.get("is_all_day_entry", False),
                        "description":      e.get("description", ""),
                    })]
                    for e in dist_events
                ],
                showlegend=True,
                name="🎭 Events",
                hovertemplate="<b>%{text}</b><extra></extra>",
            ))

    all_lons = [l["lon"] for l in dist_locs] + [dist.get("lon", 0)]
    all_lats = [l["lat"] for l in dist_locs] + [dist.get("lat", 0)]
    _frame(fig, all_lons, all_lats, pad=0.40)


# ── Shared entity pin renderer ─────────────────────────────────────────────────

_PIN_CFG = {
    "hotel":      ("Hotels",      "square",   "#FF6B35", "🏨"),
    "restaurant": ("Restaurants", "diamond",  "#4CAF50", "🍽"),
    "attraction": ("Attractions", "pentagon", "#9C27B0", "🏛"),
}


def _add_pins(fig, locs: list, cats: set, top_n: int | None, jitter: bool = False) -> None:
    import plotly.graph_objects as go

    # Running counter across all pin types so jitter offsets don't repeat per type
    global_idx = 0

    for loc_type, (cat_name, symbol, color, emoji) in _PIN_CFG.items():
        if cat_name not in cats:
            continue
        pins = [l for l in locs if l.get("location_type") == loc_type]
        if not pins:
            continue
        if top_n is not None:
            pins = sorted(pins, key=lambda x: x.get("average_rating") or 0, reverse=True)[:top_n]

        if jitter:
            xs = [p["lon"] + _jitter_x(global_idx + i) for i, p in enumerate(pins)]
            ys = [p["lat"] + _jitter_y(global_idx + i) for i, p in enumerate(pins)]
            global_idx += len(pins)
        else:
            xs = [p["lon"] for p in pins]
            ys = [p["lat"] for p in pins]

        fig.add_trace(go.Scatter(
            x=xs, y=ys,
            mode="markers",
            marker=dict(size=10, symbol=symbol, color=color,
                        line=dict(color="white", width=1)),
            text=[p["name"] for p in pins],
            customdata=[
                [loc_type, p["location_id"], json.dumps(_loc_payload(p, loc_type))]
                for p in pins
            ],
            showlegend=True,
            name=f"{emoji} {cat_name}",
            hovertemplate="<b>%{text}</b><extra></extra>",
        ))


# ══════════════════════════════════════════════════════════════════════════════
# Detail panel
# ══════════════════════════════════════════════════════════════════════════════

def _render_detail_panel(city_map: dict, dist_map: dict) -> None:
    item = st.session_state.get(_K_ITEM)
    if not item:
        level = st.session_state[_K_LEVEL]
        hints = {
            _LVL_WORLD: "👆 Click a **city** to zoom in.",
            _LVL_CITY:  "👆 Click a **district** to zoom in, or a pin for details.",
            _LVL_DIST:  "👆 Click a **pin** to see details.",
        }
        st.caption(hints.get(level, ""))
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
        elif itype == "event":
            _panel_event(item)
        elif itype == "attraction":
            _panel_attraction(item)
        else:
            st.caption(f"**{item.get('name', item.get('location_id', ''))}**")
            st.caption(f"Type: {itype}")


def _panel_city(item: dict) -> None:
    safety = item.get("safety_score", 0)
    emoji  = "🟢" if safety >= 0.75 else ("🟡" if safety >= 0.55 else ("🟠" if safety >= 0.35 else "🔴"))
    st.markdown(f"### 🏙️ {item.get('name', 'City')}")
    c1, c2 = st.columns(2)
    c1.metric("Safety", f"{emoji} {safety:.2f}")
    c2.metric("Population", f"{item.get('population', 0):,}")
    advisory = item.get("travel_advisory", "")
    if advisory:
        if safety >= 0.75:
            st.info(advisory)
        elif safety >= 0.35:
            st.warning(advisory)
        else:
            st.error(advisory)


def _panel_district(item: dict) -> None:
    safety = item.get("safety_score", 0)
    s_em   = "🟢" if safety >= 0.75 else ("🟡" if safety >= 0.55 else "🔴")
    st.markdown(f"### 📍 {item.get('name', 'District')}")
    st.caption(item.get("district_type", "").replace("_", " ").title())
    c1, c2 = st.columns(2)
    c1.metric("Safety", f"{s_em} {safety:.2f}")
    c1.metric("Walkability", f"{item.get('walkability_score', 0):.2f}")
    c2.metric("Cost index", f"{item.get('cost_index', 1):.2f}×")
    desc = item.get("description", "")
    if desc:
        st.write(desc)


def _panel_hotel(item: dict) -> None:
    stars   = "⭐" * int(item.get("star_rating") or 0)
    rating  = item.get("average_rating")
    price   = item.get("price_per_night")
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


def _panel_attraction(item: dict) -> None:
    rating = item.get("average_rating")
    st.markdown(f"### 🏛️ {item.get('name', 'Attraction')}")
    if rating is not None:
        em = "🟢" if rating >= 4 else ("🟡" if rating >= 3 else "🔴")
        st.caption(f"{em} {rating:.1f} / 5  ({item.get('review_count', 0)} reviews)")
    desc = item.get("description", "")
    if desc:
        st.write(desc)


# ══════════════════════════════════════════════════════════════════════════════
# Data helpers
# ══════════════════════════════════════════════════════════════════════════════

def _fetch_city_events(client: TravelWorldClient, city_id: str, loc_map: dict) -> list[dict]:
    """Return events for a city, with venue lat/lon and district_id attached."""
    cache_key = f"tworld_map_evts_{city_id}"
    if cache_key not in st.session_state:
        try:
            evts = client.search_events(city_id=city_id)
            for e in evts:
                venue = loc_map.get(e.get("venue_id", ""), {})
                e["_lat"]         = venue.get("lat")
                e["_lon"]         = venue.get("lon")
                e["_district_id"] = venue.get("district_id")
            st.session_state[cache_key] = evts
        except Exception:
            st.session_state[cache_key] = []
    return st.session_state[cache_key]


def _loc_payload(loc: dict, loc_type: str) -> dict:
    """Minimal dict for the detail panel (keep customdata JSON lean)."""
    base = {
        "location_id":   loc["location_id"],
        "name":          loc.get("name", ""),
        "description":   loc.get("description", ""),
        "average_rating": loc.get("average_rating"),
        "review_count":  loc.get("review_count", 0),
    }
    if loc_type == "hotel":
        base["star_rating"]    = loc.get("star_rating")
        base["price_per_night"] = loc.get("price_per_night")
    elif loc_type == "restaurant":
        base["cuisine_types"]      = loc.get("cuisine_types", [])
        base["average_spend"]      = loc.get("average_spend")
        base["michelin_stars"]     = loc.get("michelin_stars", 0)
        base["reservation_required"] = loc.get("reservation_required", False)
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


def _hull(pts: list[tuple], pad: float = 0.15) -> list[tuple]:
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


def _frame(fig, lons: list, lats: list, pad: float = 0.35) -> None:
    """Set xaxis/yaxis range to frame the given coordinate cloud."""
    if not lons or not lats:
        return
    lon_span = max(max(lons) - min(lons), 0.1)
    lat_span = max(max(lats) - min(lats), 0.1)
    fig.update_layout(
        xaxis_range=[min(lons) - lon_span * pad, max(lons) + lon_span * pad],
        yaxis_range=[min(lats) - lat_span * pad, max(lats) + lat_span * pad],
    )


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


# ══════════════════════════════════════════════════════════════════════════════
# Legacy route planner (preserved in collapsed expander)
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

    today          = datetime.date.today()
    dep_date       = st.date_input("Departure Date", value=today, min_value=today, key="rp_date")
    dep_time       = st.time_input("Departure Time", value=datetime.time(9, 0), key="rp_time")
    dep_dt_str     = datetime.datetime.combine(dep_date, dep_time).isoformat()

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
