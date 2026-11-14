import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
from datetime import datetime, date, time, timedelta

st.set_page_config(
    page_title="OFOQ | Lunar Landing Navigator",
    page_icon="🌙",
    layout="wide"
)

API = "https://ssd.jpl.nasa.gov/api/horizons.api"

@st.cache_data(ttl=3600)
def horizons(body, lon, lat, start, hours):
    end = start + timedelta(hours=hours)

    params = {
        "format": "json",
        "COMMAND": f"'{body}'",
        "OBJ_DATA": "'NO'",
        "MAKE_EPHEM": "'YES'",
        "EPHEM_TYPE": "'OBSERVER'",
        "CENTER": "'coord@301'",
        "COORD_TYPE": "'GEODETIC'",
        "SITE_COORD": f"'{lon},{lat},0'",
        "START_TIME": f"'{start:%Y-%m-%d %H:%M}'",
        "STOP_TIME": f"'{end:%Y-%m-%d %H:%M}'",
        "STEP_SIZE": "'1 h'",
        "QUANTITIES": "'4'",
        "CSV_FORMAT": "'YES'",
        "TIME_TYPE": "'UT'",
        "APPARENT": "'AIRLESS'"
    }

    response = requests.get(API, params=params, timeout=60)
    response.raise_for_status()
    result = response.json()["result"]

    if "$$SOE" not in result or "$$EOE" not in result:
        raise ValueError("Horizons error: " + result[:500])

    section = result.split("$$SOE")[1].split("$$EOE")[0]
    records = []

    for line in section.splitlines():
        parts = [p.strip() for p in line.split(",")]

        if len(parts) < 5:
            continue

        try:
            records.append({
                "datetime": pd.to_datetime(
                    parts[0], format="%Y-%b-%d %H:%M"
                ),
                "azimuth": float(parts[3]),
                "elevation": float(parts[4])
            })
        except ValueError:
            continue

    if not records:
        raise ValueError("No valid ephemeris rows returned")

    return pd.DataFrame(records)


def analyze(lon, lat, start, hours):
    sun = horizons("10", lon, lat, start, hours)
    earth = horizons("399", lon, lat, start, hours)

    df = pd.merge(
        sun[["datetime", "elevation"]],
        earth[["datetime", "elevation"]],
        on="datetime",
        suffixes=("_sun", "_earth")
    ).sort_values("datetime")

    # One-hour samples; exclude the final endpoint
    df = df.iloc[:-1].copy()

    df["Sun"] = df["elevation_sun"] > 0
    df["Earth"] = df["elevation_earth"] > 0
    df["Both"] = df["Sun"] & df["Earth"]

    if len(df) != hours:
        raise ValueError("Incomplete hourly data from NASA")

    return df


def display_scenario(df, name):
    st.subheader(name)

    a, b, c = st.columns(3)
    a.metric("☀️ Sun visible", f"{df['Sun'].sum()} h")
    b.metric("🌍 Earth visible", f"{df['Earth'].sum()} h")
    c.metric("🔗 Both visible", f"{df['Both'].sum()} h")

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df["datetime"],
        y=df["elevation_sun"],
        name="Sun",
        line=dict(color="#F5B841", width=3)
    ))

    fig.add_trace(go.Scatter(
        x=df["datetime"],
        y=df["elevation_earth"],
        name="Earth",
        line=dict(color="#39A8FF", width=3)
    ))

    fig.add_hline(y=0, line_dash="dash",
                  line_color="#FF6574")

    fig.update_layout(
        title="Elevation Above Geometric Horizon",
        xaxis_title="UTC",
        yaxis_title="Elevation (degrees)",
        template="plotly_dark",
        height=350
    )
    st.plotly_chart(fig, use_container_width=True)

    timeline = go.Figure(go.Heatmap(
        x=df["datetime"],
        y=["Sun", "Earth", "Both"],
        z=[
            df["Sun"].astype(int).tolist(),
            df["Earth"].astype(int).tolist(),
            df["Both"].astype(int).tolist()
        ],
        zmin=0,
        zmax=1,
        colorscale=[
            [0, "#8C3443"],
            [0.499, "#8C3443"],
            [0.5, "#22B89A"],
            [1, "#22B89A"]
        ],
        showscale=False
    ))

    timeline.update_layout(
        title="Operational Visibility Timeline",
        template="plotly_dark",
        height=230,
        xaxis_title="Time (UTC)"
    )
    st.plotly_chart(timeline, use_container_width=True)
    st.caption("Green: visible | Red: below geometric horizon")


st.title("🌙 OFOQ | Lunar Landing Navigator")
st.write(
    "Explore how landing location and mission delays "
    "change solar illumination and direct-to-Earth visibility."
)

st.sidebar.header("Mission Settings")

landing_date = st.sidebar.date_input(
    "Original landing date (UTC)",
    value=date(2026, 11, 14)
)

duration = st.sidebar.slider(
    "Mission duration (hours)", 24, 96, 48, 12
)

st.sidebar.subheader("Scenario A — Original Site")
lon_a = st.sidebar.number_input(
    "Longitude A (°)", -180.0, 180.0, 0.0
)
lat_a = st.sidebar.number_input(
    "Latitude A (°)", -90.0, -75.0, -89.0
)

st.sidebar.subheader("Scenario B — Plan B")
lon_b = st.sidebar.number_input(
    "Longitude B (°)", -180.0, 180.0, 0.0
)
lat_b = st.sidebar.number_input(
    "Latitude B (°)", -90.0, -75.0, -85.0
)
delay = st.sidebar.slider(
    "Landing delay (hours)", 0, 168, 48, 24
)

start_a = datetime.combine(landing_date, time(0, 0))
start_b = start_a + timedelta(hours=delay)

st.info(
    "Demo coordinates only. These points have NOT "
    "been validated as safe lunar landing sites."
)

try:
    with st.spinner("Loading real NASA JPL Horizons data..."):
        original = analyze(lon_a, lat_a, start_a, duration)
        backup = analyze(lon_b, lat_b, start_b, duration)

    col_a, col_b = st.columns(2)

    with col_a:
        display_scenario(original, "Scenario A")

    with col_b:
        display_scenario(backup, "Scenario B")

    improvement = int(
        backup["Both"].sum() - original["Both"].sum()
    )

    st.subheader("Mission Replanning Impact")
    st.metric(
        "Change in joint Sun + Earth visibility",
        f"{improvement:+d} hours"
    )

    combined = pd.concat([
        original.assign(scenario="A"),
        backup.assign(scenario="B")
    ])

    st.download_button(
        "Download NASA-based comparison (CSV)",
        data=combined.to_csv(index=False),
        file_name="OFOQ_comparison.csv",
        mime="text/csv"
    )

except Exception as error:
    st.error("Could not complete NASA calculation.")
    st.code(str(error))

st.divider()
st.caption(
    "Data source: NASA/JPL Horizons. "
    "Visibility estimates use a geometric horizon. "
    "Local terrain obstruction, solar-panel orientation, "
    "and radio-link performance are not yet modeled. "
    "Hourly samples give approximate durations."
)
