"""
Route comparison panel: side-by-side table of all transport modes.
"""
import streamlit as st

# Emoji mapping per transport mode
MODE_EMOJI = {
    "FLIGHT": "✈️",
    "RAIL": "🚂",
    "BUS": "🚌",
    "METRO": "🚇",
    "WALKING": "🚶",
    "TAXI": "🚗",
    "RIDESHARE": "🛵",
    "RENTAL_CAR": "🚗",
    "CYCLING": "🚲",
}


def render_route_comparison(routes: list[dict]) -> None:
    """
    Render a comparison table for all available route options.

    Columns: Mode | Duration | Cost | Distance | Congestion
    Fastest row is highlighted green, cheapest row is highlighted blue.

    Args:
        routes: List of RouteOption dicts from the API.
    """
    if not routes:
        st.info("No routes to compare.")
        return

    st.subheader("Route Comparison")

    try:
        import pandas as pd

        rows = []
        for r in routes:
            mode = r.get("mode", "UNKNOWN")
            emoji = MODE_EMOJI.get(mode, "🚀")
            rows.append(
                {
                    "Mode": f"{emoji} {mode.replace('_', ' ').title()}",
                    "Duration (min)": r.get("total_duration_min", 0),
                    "Cost ($)": round(float(r.get("total_cost", 0.0) or 0.0), 2),
                    "Distance (km)": round(float(r.get("total_distance_km", 0.0) or 0.0), 1),
                    "Congestion": "Yes" if r.get("congestion_applied") else r.get("congestion_level", "No"),
                }
            )

        df = pd.DataFrame(rows)
        df = df.sort_values("Duration (min)", ascending=True).reset_index(drop=True)

        min_dur_idx = int(df["Duration (min)"].idxmin()) if not df.empty else None
        min_cost_idx = int(df["Cost ($)"].idxmin()) if not df.empty else None

        def highlight(row):
            styles = [""] * len(row)
            if row.name == min_dur_idx:
                styles = ["background-color: #d4edda; color: #155724"] * len(row)
            elif row.name == min_cost_idx:
                styles = ["background-color: #cce5ff; color: #004085"] * len(row)
            return styles

        styled_df = df.style.apply(highlight, axis=1)
        st.dataframe(styled_df, use_container_width=True, hide_index=True)

        col1, col2 = st.columns(2)
        col1.markdown(
            '<span style="background-color:#d4edda;padding:2px 8px">Fastest route</span>',
            unsafe_allow_html=True,
        )
        col2.markdown(
            '<span style="background-color:#cce5ff;padding:2px 8px">Cheapest route</span>',
            unsafe_allow_html=True,
        )

    except ImportError:
        # Fallback without pandas
        for r in routes:
            mode = r.get("mode", "UNKNOWN")
            emoji = MODE_EMOJI.get(mode, "🚀")
            duration = r.get("total_duration_min", 0)
            cost = float(r.get("total_cost", 0.0) or 0.0)
            st.write(f"{emoji} **{mode}**: {duration} min, ${cost:.2f}")
