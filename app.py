import streamlit as st
import streamlit.components.v1 as components
from streamlit_folium import st_folium
import folium
import requests
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, date, time, timedelta
import base64
import json

st.set_page_config(
    page_title="OFOQ | Lunar Explorer",
    page_icon="🌙",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------- Design ----------
st.markdown("""
<style>
.stApp {
    background: #080e1b;
    color: #f1f5ff;
}
[data-testid="stSidebar"] {
    background: #111b2e;
}
.block-container {
    padding-top: 1.1rem;
    max-width: 1550px;
}
h1, h2, h3 {
    color: #f2f6ff !important;
}
.hero {
    background:
      linear-gradient(100deg, #091124 10%,
      #142842 75%, #183d55);
    padding: 27px 30px;
    border: 1px solid #29435b;
    border-radius: 18px;
    margin-bottom: 20px;
}
.hero h1 {
    font-size: 45px;
    margin: 0;
    letter-spacing: 3px;
}
.hero p {
    color: #b9cce0;
    font-size: 16px;
    margin-top: 5px;
}
div[data-testid="stMetric"] {
    background: #15243a;
    padding: 15px;
    border: 1px solid #30465f;
    border-radius: 13px;
}
div[data-testid="stMetricValue"] {
    color: #ffffff;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hero">
<h1>🌙 OFOQ</h1>
<p>EXPLORE THE MOON. PLAN THE MISSION.</p>
<p>Find a lunar location, explore Sun and Earth visibility,
and test what happens when a mission is delayed.</p>
</div>
""", unsafe_allow_html=True)

# ---------- Session ----------
if "site_lat" not in st.session_state:
    st.session_state.site_lat = -89.0

if "site_lon" not in st.session_state:
    st.session_state.site_lon = 0.0

NASA_API = "https://ssd.jpl.nasa.gov/api/horizons.api"

NASA_TEXTURE = (
    "https://svs.gsfc.nasa.gov/vis/a000000/"
    "a004700/a004720/lroc_color_2k.jpg"
)

NASA_TILES = (
    "https://trek.nasa.gov/tiles/Moon/EQ/"
    "LRO_WAC_Mosaic_Global_303ppd_v02/"
    "1.0.0/default/default028mm/"
    "{z}/{y}/{x}.jpg"
)

# ---------- Real NASA imagery ----------
@st.cache_data(ttl=86400, show_spinner=False)
def moon_texture():
    r = requests.get(NASA_TEXTURE, timeout=30)
    r.raise_for_status()
    return (
        "data:image/jpeg;base64,"
        + base64.b64encode(r.content).decode("ascii")
    )


def show_globe():
    texture = moon_texture()

    html = """
    <html>
    <head>
    <style>
      body { margin:0; background:#080e1b; color:white;
             font-family:Arial,sans-serif; overflow:hidden; }
      #globe { width:100%; height:440px; }
      #hint {position:absolute; bottom:12px; left:15px;
             background:#12233acc; padding:9px 14px;
             border-radius:8px; font-size:13px;}
    </style>
    <script type="importmap">
    {
      "imports": {
        "three": "https://unpkg.com/three@0.160.0/build/three.module.js",
        "three/addons/":
        "https://unpkg.com/three@0.160.0/examples/jsm/"
      }
    }
    </script>
    </head>
    <body>
    <div id="globe"></div>
    <div id="hint">Drag to rotate · Scroll to zoom</div>

    <script type="module">
      import * as THREE from "three";
      import { OrbitControls } from
        "three/addons/controls/OrbitControls.js";

      const root = document.getElementById("globe");
      const w = root.clientWidth || 800;
      const h = 440;

      const scene = new THREE.Scene();
      const camera = new THREE.PerspectiveCamera(
        42, w/h, 0.1, 100
      );
      camera.position.set(0, 0, 5.2);

      const renderer = new THREE.WebGLRenderer({
        antialias:true, alpha:true
      });
      renderer.setSize(w, h);
      renderer.setPixelRatio(
        Math.min(window.devicePixelRatio, 2)
      );
      root.appendChild(renderer.domElement);

      const textureUrl = __TEXTURE__;
      const texture = new THREE.TextureLoader().load(
        textureUrl
      );
      texture.colorSpace = THREE.SRGBColorSpace;

      const moon = new THREE.Mesh(
        new THREE.SphereGeometry(1.75, 96, 64),
        new THREE.MeshStandardMaterial({
          map:texture, roughness:1
        })
      );
      scene.add(moon);

      scene.add(new THREE.AmbientLight(0xffffff, 1.5));

      const sun = new THREE.DirectionalLight(
        0xffffff, 2.0
      );
      sun.position.set(5, 3, 6);
      scene.add(sun);

      const controls = new OrbitControls(
        camera, renderer.domElement
      );
      controls.enablePan = false;
      controls.enableDamping = true;
      controls.minDistance = 2.3;
      controls.maxDistance = 8;

      function animate() {
        requestAnimationFrame(animate);
        controls.update();
        renderer.render(scene, camera);
      }
      animate();

      window.addEventListener("resize", () => {
        const width = root.clientWidth || 800;
        camera.aspect = width / h;
        camera.updateProjectionMatrix();
        renderer.setSize(width, h);
      });
    </script>
    </body>
    </html>
    """

    html = html.replace(
        "__TEXTURE__", json.dumps(texture)
    )
    components.html(html, height=450, scrolling=False)


# ---------- Moon map ----------
def make_map(lat, lon, zoom=4, marker=True):
    m = folium.Map(
        location=[lat, lon],
        zoom_start=zoom,
        tiles=None,
        crs="EPSG4326",
        control_scale=True
    )

    folium.TileLayer(
        tiles=NASA_TILES,
        attr="NASA/JPL Moon Trek - LRO WAC",
        name="NASA Lunar Imagery",
        overlay=False,
        control=True,
        max_zoom=8,
        no_wrap=True
    ).add_to(m)

    if marker:
        folium.CircleMarker(
            location=[lat, lon],
            radius=7,
            color="#00d8ff",
            fill=True,
            fill_color="#00d8ff",
            fill_opacity=0.9,
            tooltip="Selected lunar point"
        ).add_to(m)

    return m


# ---------- NASA Horizons ----------
@st.cache_data(ttl=21600, show_spinner=False)
def get_horizons(body, lon, lat, start_text, hours):
    start = datetime.strptime(
        start_text, "%Y-%m-%d %H:%M"
    )
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

    response = requests.get(
        NASA_API, params=params, timeout=60
    )
    response.raise_for_status()
    text = response.json()["result"]

    if "$$SOE" not in text or "$$EOE" not in text:
        raise ValueError(
            "NASA returned no ephemeris table: "
            + text[:350]
        )

    block = text.split("$$SOE")[1].split("$$EOE")[0]
    records = []

    for line in block.splitlines():
        parts = [p.strip() for p in line.split(",")]

        if len(parts) < 5:
            continue

        try:
            records.append({
                "time": pd.to_datetime(
                    parts[0], format="%Y-%b-%d %H:%M"
                ),
                "azimuth": float(parts[3]),
                "elevation": float(parts[4])
            })
        except ValueError:
            continue

    if not records:
        raise ValueError("NASA returned no valid rows")

    return pd.DataFrame(records)


def analyze(lat, lon, start, hours):
    start_text = start.strftime("%Y-%m-%d %H:%M")

    sun = get_horizons(
        "10", lon, lat, start_text, hours
    )
    earth = get_horizons(
        "399", lon, lat, start_text, hours
    )

    df = sun[["time", "elevation"]].merge(
        earth[["time", "elevation"]],
        on="time",
        suffixes=("_sun", "_earth")
    ).sort_values("time")

    # Each sample represents the following hour.
    # The final sample is an endpoint only.
    df = df.iloc[:-1].copy()

    if len(df) != hours:
        raise ValueError(
            "Incomplete hourly data: "
            + str(len(df))
        )

    df["Sun"] = df["elevation_sun"] > 0
    df["Earth"] = df["elevation_earth"] > 0
    df["Both"] = df["Sun"] & df["Earth"]

    return df


def explain(df):
    sun_hours = int(df["Sun"].sum())
    earth_hours = int(df["Earth"].sum())
    both_hours = int(df["Both"].sum())
    total = len(df)

    a, b, c = st.columns(3)
    a.metric("☀️ Sun above horizon",
             f"{sun_hours}/{total} h")
    b.metric("🌍 Earth above horizon",
             f"{earth_hours}/{total} h")
    c.metric("🔗 Both at once",
             f"{both_hours}/{total} h")

    if both_hours == 0:
        st.warning(
            "No simultaneous Sun and Earth visibility "
            "was found during these sampled hours. "
            "A different site or date may help."
        )
    else:
        st.success(
            f"Sun and Earth are both above the "
            f"geometric horizon for approximately "
            f"{both_hours} hours."
        )

    st.caption(
        "These are hourly geometric estimates. "
        "Mountains, crater walls, and radio-link "
        "performance are not included."
    )

    fig = go.Figure()

    for label, column, color in [
        ("Sun", "elevation_sun", "#ffcb54"),
        ("Earth", "elevation_earth", "#38bdf8")
    ]:
        fig.add_trace(go.Scatter(
            x=df["time"], y=df[column],
            mode="lines",
            name=label,
            line=dict(color=color, width=3)
        ))

    fig.add_hline(
        y=0, line_dash="dash",
        line_color="#fb7185"
    )

    fig.update_layout(
        title="How high are the Sun and Earth?",
        xaxis_title="Time (UTC)",
        yaxis_title="Degrees above or below horizon",
        template="plotly_dark",
        height=340,
        margin=dict(l=20, r=20, t=50, b=25),
        hovermode="x unified"
    )

    st.plotly_chart(fig, use_container_width=True)

    heat = go.Figure(go.Heatmap(
        x=df["time"],
        y=["Sun", "Earth", "Both"],
        z=[
            df["Sun"].astype(int).tolist(),
            df["Earth"].astype(int).tolist(),
            df["Both"].astype(int).tolist()
        ],
        zmin=0, zmax=1,
        colorscale=[
            [0, "#693143"],
            [0.499, "#693143"],
            [0.5, "#15b8a6"],
            [1, "#15b8a6"]
        ],
        showscale=False
    ))

    heat.update_layout(
        title="When are they above the horizon?",
        template="plotly_dark",
        height=220,
        margin=dict(l=20, r=20, t=50, b=20)
    )

    st.plotly_chart(heat, use_container_width=True)
    st.caption(
        "Teal = above geometric horizon. "
        "Dark red = below geometric horizon."
    )

    return both_hours


# ---------- Mission controls ----------
with st.sidebar:
    st.header("🚀 Mission Control")

    mission_date = st.date_input(
        "Landing date (UTC)",
        value=date(2026, 11, 14)
    )

    hours = st.slider(
        "Mission duration (hours)",
        24, 96, 48, 12
    )

    mode = st.selectbox(
        "What would you like to test?",
        [
            "Current site only",
            "Delay at the same site",
            "Different site, same date"
        ]
    )

    delay = 0
    backup_lat = st.session_state.site_lat
    backup_lon = st.session_state.site_lon

    if mode == "Delay at the same site":
        delay = st.slider(
            "Landing delay (hours)",
            0, 168, 48, 24
        )

    elif mode == "Different site, same date":
        backup_lat = st.number_input(
            "Backup latitude",
            -90.0, -75.0, -85.0
        )
        backup_lon = st.number_input(
            "Backup longitude",
            -180.0, 180.0, 0.0
        )

    st.markdown("---")
    st.caption("NASA/JPL Horizons + NASA Moon Trek")
    run = st.button(
        "🔎 Analyze Mission",
        type="primary",
        use_container_width=True
    )


# ---------- Explore ----------
tab_globe, tab_map, tab_close = st.tabs([
    "🌕 3D Moon",
    "📍 Choose a Landing Point",
    "🔭 Surface Close-Up"
])

with tab_globe:
    left, right = st.columns([3, 1])

    with left:
        try:
            show_globe()
        except Exception as err:
            st.warning("3D globe could not load.")
            st.image(NASA_TEXTURE)
            st.caption(str(err))

    with right:
        st.subheader("Explore the Moon")
        st.write(
            "Rotate the Moon with your mouse. "
            "Zoom in to explore its surface."
        )
        st.info(
            "To select an exact lunar point, "
            "open the Choose a Landing Point tab."
        )
        st.caption(
            "3D texture: NASA Scientific Visualization "
            "Studio / LRO. Visual exploration only."
        )

with tab_map:
    st.subheader("Select a location on the Moon")
    st.write(
        "Drag the map, zoom in, then click a point. "
        "The coordinates will be used for "
        "the mission analysis."
    )

    m = make_map(
        st.session_state.site_lat,
        st.session_state.site_lon,
        zoom=4
    )

    clicked_map = st_folium(
        m,
        height=480,
        use_container_width=True,
        returned_objects=["last_clicked"],
        key="ofoq_lunar_map"
    )

    if clicked_map and clicked_map.get("last_clicked"):
        p = clicked_map["last_clicked"]
        lat = round(float(p["lat"]), 5)
        lon = round(float(p["lng"]), 5)

        if -90 <= lat <= -75 and -180 <= lon <= 180:
            changed = (
                lat != st.session_state.site_lat or
                lon != st.session_state.site_lon
            )

            if changed:
                st.session_state.site_lat = lat
                st.session_state.site_lon = lon
                st.rerun()
        else:
            st.warning(
                "Select a point between 75°S "
                "and 90°S for this version."
            )

    st.caption(
        "Basemap: NASA Moon Trek LRO WAC mosaic. "
        "Polar areas are distorted in this "
        "equirectangular map."
    )

    st.markdown("**Or enter coordinates manually:**")

    with st.form("manual_location"):
        latitude = st.number_input(
            "Latitude (degrees)",
            -90.0, -75.0,
            float(st.session_state.site_lat),
            format="%.5f"
        )
        longitude = st.number_input(
            "Longitude (degrees)",
            -180.0, 180.0,
            float(st.session_state.site_lon),
            format="%.5f"
        )
        choose = st.form_submit_button("Use this location")

        if choose:
            st.session_state.site_lat = latitude
            st.session_state.site_lon = longitude
            st.rerun()

with tab_close:
    st.subheader("Surface Close-Up — Orbital View")
    st.write(
        "Zoom in to inspect visible craters "
        "and surface features near the selected point."
    )

    close_map = make_map(
        st.session_state.site_lat,
        st.session_state.site_lon,
        zoom=7
    )
    st_folium(
        close_map,
        height=480,
        use_container_width=True,
        key="closeup"
    )

    st.info(
        "This is satellite imagery from above, "
        "not a real camera mounted on a lander. "
        "A terrain-based lander perspective "
        "requires a local elevation model."
    )


# ---------- Site analysis ----------
st.divider()

lat = st.session_state.site_lat
lon = st.session_state.site_lon

st.subheader("📍 Selected Lunar Point")

a, b = st.columns(2)
a.metric("Latitude", f"{lat:.5f}°")
b.metric("Longitude", f"{lon:.5f}°")

st.warning(
    "Landing safety: NOT ASSESSED. "
    "We have not yet checked local slope, "
    "surface roughness, or boulders."
)

start = datetime.combine(
    mission_date, time(0, 0)
)

if run:
    try:
        with st.spinner(
            "Calculating real NASA mission conditions..."
        ):
            original = analyze(lat, lon, start, hours)

        st.subheader("☀️ Your Mission Conditions")
        original_both = explain(original)

        if mode != "Current site only":
            if mode == "Delay at the same site":
                next_start = start + timedelta(
                    hours=delay
                )
                next_lat = lat
                next_lon = lon
                label = "Same site, later landing"
            else:
                next_start = start
                next_lat = backup_lat
                next_lon = backup_lon
                label = "Different site, same date"

            with st.spinner("Comparing scenarios..."):
                alternative = analyze(
                    next_lat, next_lon,
                    next_start, hours
                )

            st.subheader("🔁 Plan B Comparison")
            st.write(label)
            alt_both = explain(alternative)

            diff = alt_both - original_both

            st.metric(
                "Change in simultaneous visibility",
                f"{diff:+d} sampled hours"
            )

            if diff > 0:
                st.success(
                    "Plan B provides more hours "
                    "with both objects above "
                    "the geometric horizon."
                )
            elif diff < 0:
                st.warning(
                    "Plan B provides fewer hours "
                    "with both objects above "
                    "the geometric horizon."
                )
            else:
                st.info(
                    "Both scenarios have equal "
                    "sampled simultaneous visibility."
                )

        st.download_button(
            "Download original NASA analysis (CSV)",
            data=original.to_csv(index=False),
            file_name="OFOQ_mission_analysis.csv",
            mime="text/csv"
        )

    except Exception as err:
        st.error("NASA analysis could not finish.")
        st.code(str(err))

else:
    st.info(
        "Choose your location and mission date, "
        "then press Analyze Mission in the sidebar."
    )


# ---------- Science and credits ----------
st.divider()

st.markdown("### 🛰️ What does this analysis mean?")
st.write(
    "**Sun above horizon:** the Sun is geometrically "
    "above the local reference horizon. "
    "It does not guarantee usable solar power."
)
st.write(
    "**Earth above horizon:** a direct geometric "
    "line of sight to Earth may exist. "
    "Terrain and communication link quality "
    "are not evaluated."
)
st.write(
    "**Both at once:** the Sun and Earth are "
    "above that reference horizon at the "
    "same sampled time."
)

st.caption(
    "OFOQ — NASA Space Apps Challenge 2026. "
    "Data: NASA/JPL Horizons, NASA Moon Trek, "
    "NASA Scientific Visualization Studio. "
    "This is an educational mission-planning "
    "prototype, not a certified landing safety tool."
)
