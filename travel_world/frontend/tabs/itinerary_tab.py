"""
Itinerary tab: sequential view of all items in the current trip plan.

Items are sorted chronologically and grouped by date.
City context is tracked from flight destinations — a city header banner
appears whenever the destination city changes, giving a clear visual
section break between legs of the trip.
"""
from collections import defaultdict
import streamlit as st
from travel_world.frontend import state
from travel_world.frontend.api_client import TravelWorldClient, APIError


_TYPE_ICON = {"flight": "✈️", "hotel": "🏨", "event": "🎭", "restaurant": "🍽️"}


def render(client: TravelWorldClient) -> None:
    """Render the Itinerary tab."""
    st.header("My Itinerary")

    session_id = state.get_session_id()
    if not session_id:
        st.info("Start a session in Trip Setup to build your itinerary.")
        return

    # Load city name lookup
    world_id = st.session_state.get(state.WORLD_ID_KEY)
    city_labels: dict[str, str] = {}
    if world_id:
        try:
            cities = client.list_cities(world_id)
            city_labels = {c["city_id"]: c["name"] for c in cities}
        except Exception:
            pass

    try:
        plan = client.get_trip_plan(session_id)
    except APIError as e:
        st.error(f"Could not load itinerary: {e.message}")
        return

    items = plan.get("items", [])
    total_cost = plan.get("total_cost", 0.0)

    if not items:
        st.info("Your itinerary is empty. Add flights, hotels, and events from the other tabs.")
        return

    # ── Itinerary evaluation ─────────────────────────────────────────────
    _render_evaluation(plan, city_labels)

    # Sort chronologically using fine-grained datetime:
    # flights → arrival_datetime; hotels → date + check_in_time; events → start datetime
    def _sort_key(item):
        date = (item.get("date", "") or "")[:10]
        meta = item.get("metadata", {}) or {}
        itype = item.get("item_type", "")
        if itype == "flight":
            arr = (meta.get("arrival_datetime") or item.get("date", "") or "")
            return arr[:16] if len(arr) >= 16 else date + "T23:59"
        elif itype == "hotel":
            t = meta.get("check_in_time", "13:00") or "13:00"
            return date + "T" + t
        else:
            return date + "T12:00"

    items_sorted = sorted(items, key=_sort_key)

    # Combine duplicate items (same ref_id + type + date) into one with quantity
    from collections import defaultdict as _dd
    _groups: dict = _dd(list)
    for item in items_sorted:
        key = (item.get("ref_id", ""), item.get("item_type", ""), (item.get("date", "") or "")[:10])
        _groups[key].append(item)

    merged: list[dict] = []
    for group in _groups.values():
        if len(group) == 1:
            group[0]["_quantity"] = 1
            merged.append(group[0])
        else:
            combined = dict(group[0])  # copy first item
            combined["_quantity"] = len(group)
            combined["cost"] = sum(g.get("cost", 0) for g in group)
            merged.append(combined)
    # Re-sort merged list
    items_sorted = sorted(merged, key=_sort_key)

    # Annotate each item with its city context:
    # after a flight lands in city X, all subsequent items inherit city X.
    current_city_id: str | None = None
    for item in items_sorted:
        meta = item.get("metadata", {}) or {}
        item_type = item.get("item_type")
        if item_type == "flight":
            dest = meta.get("destination_city_id")
            if dest:
                current_city_id = dest
        elif item_type in ("hotel", "event"):
            # Use the item's own city if we don't have one from a flight yet
            own_city = meta.get("city_id")
            if own_city and not current_city_id:
                current_city_id = own_city
        item["_city_ctx"] = current_city_id

    # Pre-fetch weather for event dates
    weather_cache: dict[tuple, dict | None] = {}
    for item in items:
        if item.get("item_type") == "event":
            meta_i = item.get("metadata", {}) or {}
            w_city = meta_i.get("city_id") or item.get("_city_ctx")
            w_date = (item.get("date", "") or "")[:10]
            if w_city and w_date and (w_city, w_date) not in weather_cache:
                weather_cache[(w_city, w_date)] = client.get_weather_snapshot(w_city, w_date)

    # Group by date
    by_date: dict[str, list[dict]] = defaultdict(list)
    for item in items_sorted:
        date_key = (item.get("date", "") or "")[:10] or "No date"
        by_date[date_key].append(item)

    # Render
    last_city_shown: str | None = "__none__"
    for date_str in sorted(by_date.keys()):
        day_items = by_date[date_str]

        # City divider — show when city context changes for this day
        day_city = next(
            (it["_city_ctx"] for it in day_items if it.get("_city_ctx")), None
        )
        if day_city and day_city != last_city_shown:
            city_name = city_labels.get(day_city, day_city)
            st.markdown(
                f"""
                <div style="
                    background: linear-gradient(90deg,#1F77B4,#2E86AB);
                    color: white;
                    padding: 8px 16px;
                    border-radius: 8px;
                    margin: 16px 0 4px 0;
                    font-size: 16px;
                    font-weight: 600;
                ">📍 {city_name}</div>
                """,
                unsafe_allow_html=True,
            )
            last_city_shown = day_city

        st.subheader(f"📅 {date_str}")
        for item in day_items:
            _render_item(client, session_id, item, city_labels, weather_cache)
        st.divider()

    # Summary footer + budget breakdown
    st.divider()
    prefs = state.get_preferences()
    budget = prefs.get("budget_total")

    col1, col2, col3 = st.columns(3)
    col2.metric("Total Plan Cost", f"${total_cost:,.2f}")
    if budget:
        remaining = float(budget) - total_cost
        col1.metric(
            "Budget Remaining",
            f"${remaining:,.2f}",
            delta=f"of ${float(budget):,.0f}",
            delta_color="normal" if remaining >= 0 else "inverse",
        )
    col3.metric("Items", len(items))

    # Category breakdown bar chart
    breakdown: dict[str, float] = {}
    for item in items:
        cat = item.get("item_type", "other").title()
        breakdown[cat] = breakdown.get(cat, 0.0) + float(item.get("cost", 0.0))

    if breakdown:
        st.markdown("#### Budget Breakdown by Category")
        try:
            import pandas as pd
            import altair as alt
            df = pd.DataFrame([
                {"Category": k, "Cost ($)": round(v, 2)}
                for k, v in sorted(breakdown.items(), key=lambda x: -x[1])
            ])
            chart = (
                alt.Chart(df)
                .mark_bar()
                .encode(
                    x=alt.X("Cost ($):Q", title="Cost (USD)"),
                    y=alt.Y("Category:N", sort="-x", title=""),
                    color=alt.Color("Category:N", legend=None),
                    tooltip=["Category", alt.Tooltip("Cost ($):Q", format="$.2f")],
                )
                .properties(height=max(120, len(breakdown) * 40))
            )
            st.altair_chart(chart, use_container_width=True)
        except ImportError:
            # Fallback: plain table if altair/pandas not available
            for cat, amt in sorted(breakdown.items(), key=lambda x: -x[1]):
                pct = amt / total_cost * 100 if total_cost else 0
                st.caption(f"**{cat}**: ${amt:,.2f}  ({pct:.0f}%)")


def _render_item(
    client: TravelWorldClient,
    session_id: str,
    item: dict,
    city_labels: dict[str, str],
    weather_cache: dict | None = None,
) -> None:
    """Render one itinerary item card with info, cost, and a remove button."""
    item_id = item.get("item_id", "")
    item_type = item.get("item_type", "unknown")
    cost = item.get("cost", 0.0)
    meta = item.get("metadata", {}) or {}
    icon = _TYPE_ICON.get(item_type, "📌")
    quantity = item.get("_quantity", 1)

    with st.container(border=True):
        col_info, col_cost, col_remove = st.columns([5, 1, 1])

        with col_info:
            if item_type == "flight":
                airline = meta.get("airline", "")
                flight_number = meta.get("flight_number", item.get("ref_id", ""))
                cabin = (meta.get("cabin_class") or "").upper()
                is_direct = meta.get("is_direct", True)
                layover = meta.get("layover_city_name", "")

                orig_id = meta.get("origin_city_id", "")
                dest_id = meta.get("destination_city_id", "")
                orig_name = city_labels.get(orig_id, orig_id) if orig_id else ""
                dest_name = city_labels.get(dest_id, dest_id) if dest_id else ""

                dep_dt = meta.get("departure_datetime") or item.get("date", "") or ""
                arr_dt = meta.get("arrival_datetime") or ""
                dep_str = dep_dt[11:16] if len(dep_dt) >= 16 else dep_dt[:10]
                arr_str = arr_dt[11:16] if len(arr_dt) >= 16 else ""

                direct_label = "Direct" if is_direct else (f"Via {layover}" if layover else "Connecting")

                headline = f"{icon} **{airline} {flight_number}**"
                if quantity > 1:
                    headline += f" ×{quantity}"
                if cabin:
                    headline += f" · {cabin}"
                st.markdown(headline)

                details = []
                if orig_name and dest_name:
                    details.append(f"✈️ {orig_name} → {dest_name}")
                if dep_str:
                    time_str = f"{dep_str} → {arr_str}" if arr_str else dep_str
                    details.append(f"🕐 {time_str}")
                details.append(direct_label)
                st.caption("  |  ".join(details))

            elif item_type == "hotel":
                hotel_name = meta.get("name", item.get("ref_id", "Hotel"))
                check_in = meta.get("check_in", item.get("date", ""))
                check_out = meta.get("check_out", "")
                check_in_time = meta.get("check_in_time", "")
                num_beds = meta.get("num_beds")
                bed_str = f"  |  🛏️ {num_beds} bed{'s' if num_beds and num_beds > 1 else ''}" if num_beds else ""
                time_str = f" @ {check_in_time}" if check_in_time else ""
                st.markdown(f"{icon} **{hotel_name}**" + (f" ×{quantity}" if quantity > 1 else ""))
                if check_out:
                    st.caption(f"Check-in: {check_in}{time_str} → Check-out: {check_out}{bed_str}")
                else:
                    st.caption(f"Check-in: {check_in}{time_str}{bed_str}")

            elif item_type == "event":
                event_name = meta.get("name", item.get("ref_id", "Event"))
                venue = meta.get("venue", "")
                date_str = item.get("date", "")
                _sdt_it = meta.get("start_datetime") or ""
                _edt_it = meta.get("end_datetime") or ""
                start_time_it = _sdt_it[11:16] if len(_sdt_it) >= 16 else ""
                end_time_it = _edt_it[11:16] if len(_edt_it) >= 16 else ""
                is_all_day_it = meta.get("is_all_day_entry", False)
                if is_all_day_it and start_time_it and end_time_it:
                    time_str_it = f"🕐 {start_time_it}–{end_time_it} (all-day entry)"
                elif start_time_it and end_time_it:
                    time_str_it = f"🕐 {start_time_it}–{end_time_it}"
                elif start_time_it:
                    time_str_it = f"🕐 {start_time_it}"
                else:
                    time_str_it = ""
                description_it = meta.get("description", "")
                st.markdown(f"{icon} **{event_name}**" + (f" ×{quantity}" if quantity > 1 else ""))
                caption_parts = [p for p in [date_str, time_str_it, venue] if p]
                st.caption(" · ".join(caption_parts))
                if description_it:
                    st.write(description_it)
                # Weather on event day
                if weather_cache is not None:
                    w_city = meta.get("city_id") or item.get("_city_ctx")
                    w_date = (date_str or "")[:10]
                    snap = weather_cache.get((w_city, w_date)) if w_city else None
                    if snap:
                        _COND_ICON = {
                            "sunny": "☀️", "partly_cloudy": "⛅", "cloudy": "☁️",
                            "rainy": "🌧️", "stormy": "⛈️", "snowy": "❄️", "foggy": "🌫️",
                        }
                        cond = snap.get("condition", "")
                        w_icon = _COND_ICON.get(cond, "🌡️")
                        temp = snap.get("temperature_c", "")
                        st.caption(f"{w_icon} {cond.replace('_',' ').title()}  ·  {temp}°C")

            elif item_type == "restaurant":
                rest_name = meta.get("name", item.get("ref_id", "Restaurant"))
                cuisine = meta.get("cuisine_types", [])
                cuisine_str = ", ".join(cuisine) if cuisine else ""
                district = meta.get("district_name", "")
                avg_spend = meta.get("average_spend")
                michelin = meta.get("michelin_stars", 0)
                stars_str = "⭐" * michelin if michelin else ""
                st.markdown(f"🍽️ **{rest_name}**{' ' + stars_str if stars_str else ''}" + (f" ×{quantity}" if quantity > 1 else ""))
                caption_parts = [p for p in [cuisine_str, f"📍 {district}" if district else "", f"~${avg_spend:.0f}/person" if avg_spend else ""] if p]
                st.caption("  |  ".join(caption_parts))

            else:
                st.markdown(f"{icon} **{item.get('ref_id', item_id)}**")
                st.caption(f"Type: {item_type}")

        with col_cost:
            st.markdown(f"**${cost:,.2f}**")
            st.caption("cost")

        with col_remove:
            if st.button("Remove", key=f"remove_{item_id}", type="secondary"):
                try:
                    client.delete_trip_item(session_id, item_id)
                    st.success("Removed.")
                    st.cache_data.clear()
                    st.rerun()
                except APIError as e:
                    st.error(f"Could not remove: {e.message}")


def _render_evaluation(plan: dict, city_labels: dict) -> None:
    """Run all itinerary checks and display results as an expandable panel."""
    from travel_world.frontend import state as _state
    from travel_world.evaluation.evaluator import build_default_evaluator

    prefs = _state.get_preferences()
    context = {"city_labels": city_labels}

    evaluator = build_default_evaluator()
    report = evaluator.run_all(plan, prefs, context)

    if not report.any_failed:
        with st.expander("✅ Itinerary checks passed", expanded=False):
            for r in report.results:
                st.caption(f"✓ {r.check_name}: {r.message}")
        return

    # Determine worst severity
    if report.errors:
        expander_label = f"❌ {len(report.errors)} error(s) in itinerary"
        expanded = True
    else:
        expander_label = f"⚠️ {len(report.warnings)} warning(s) in itinerary"
        expanded = True

    with st.expander(expander_label, expanded=expanded):
        for r in report.results:
            if r.passed:
                st.caption(f"✓ {r.check_name}: {r.message}")
            elif r.severity.value == "error":
                st.error(f"**{r.check_name}**: {r.message}")
            else:
                st.warning(f"**{r.check_name}**: {r.message}")

        # LLM-ready text output (collapsed)
        with st.expander("📋 Text report (for LLM evaluation)", expanded=False):
            st.code(report.to_text(), language=None)
