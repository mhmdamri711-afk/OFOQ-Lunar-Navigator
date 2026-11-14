import streamlit as st
import streamlit.components.v1 as components
from streamlit_folium import st_folium
import folium
import requests
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import rasterio
from rasterio.windows import Window
from rasterio.transform import rowcol
from pyproj import CRS, Transformer
from datetime import datetime, date, time, timedelta
import base64
import json
import html
import os
import shutil
import tempfile

# ============================================================
# OFOQ v3 — LUNAR MISSION EXPLORER
# NASA Space Apps Challenge 2026
# ============================================================

st.set_page_config(
    page_title="OFOQ | Lunar Mission Explorer",
    page_icon="🌙",
    layout="wide",
    initial_sidebar_state="expanded"
)

NASA_API = "https://ssd.jpl.nasa.gov/api/horizons.api"

MOON_TEXTURE = (
    "https://svs.gsfc.nasa.gov/vis/a000000/"
    "a004700/a004720/lroc_color_2k.jpg"
)

MOON_TILES = (
    "https://trek.nasa.gov/tiles/Moon/EQ/"
    "LRO_WAC_Mosaic_Global_303ppd_v02/"
    "1.0.0/default/default028mm/"
    "{z}/{y}/{x}.jpg"
)

NASA_DEM_PAGE = (
    "https://pgda.gsfc.nasa.gov/products/78"
)

LUNAR_GEO = CRS.from_proj4(
    "+proj=longlat +a=1737400 +b=1737400 "
    "+no_defs +type=crs"
)

# ============================================================
# DESIGN SYSTEM
# ============================================================

st.markdown("""
<style>
@import url(
'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap'
);

html, body, [class*="css"], .stApp {
    font-family: 'Inter', sans-serif;
}

.stApp {
    background:
      radial-gradient(
        circle at 70% 0%, #102742 0%,
        #070e19 44%, #050a12 100%
      );
    color: #edf5ff;
}

[data-testid="stSidebar"] {
    background: #0c1727;
    border-right: 1px solid #26364b;
}

.block-container {
    max-width: 1540px;
    padding-top: 1.1rem;
    padding-bottom: 4rem;
}

h1, h2, h3 {
    color: #f1f7ff !important;
}

.brand {
    padding: 27px 31px;
    border-radius: 22px;
    margin-bottom: 22px;
    border: 1px solid #35516b;
    background: linear-gradient(
        110deg, #0c192c, #102e48, #163e54
    );
}

.brand h1 {
    font-size: clamp(34px, 5vw, 54px);
    letter-spacing: 5px;
    margin: 0;
}

.brand .subtitle {
    color: #6de4e7;
    font-size: 13px;
    letter-spacing: 2px;
    font-weight: 700;
}

.brand .desc {
    color: #bacbe0;
    margin-top: 14px;
    max-width: 850px;
}

.section-label {
    color: #6de4e7;
    font-size: 12px;
    letter-spacing: 2px;
    font-weight: 800;
}

.note-card {
    background: #102136;
    border: 1px solid #2c435d;
    border-radius: 14px;
    padding: 19px;
    margin: 10px 0;
}

.note-card strong {
    color: #ffffff;
}

[data-testid="stMetric"] {
    background: #12243a;
    border: 1px solid #304963;
    border-radius: 14px;
    padding: 16px;
}

[data-testid="stMetricValue"] {
    color: #f4fbff;
}

.stButton button[kind="primary"] {
    background: #28b9b9;
    color: #06101a;
    border-radius: 11px;
    font-weight: 800;
    border: none;
}

.stButton button {
    border-radius: 11px;
}

hr {
    border-color: #23384e;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="brand">
    <div class="subtitle">
        OFOQ / MISSION INTELLIGENCE
    </div>
    <h1>OFOQ 🌙</h1>
    <div class="desc">
        Explore the Moon. Inspect the terrain.
        Understand sunlight and Earth visibility.
        Compare mission plans using NASA data.
    </div>
</div>
""", unsafe_allow_html=True)

# ============================================================
# STATE
# ============================================================

defaults = {
    "lat": -89.0,
    "lon": 0.0,
    "scan_slope_path": None,
    "scan_dem_path": None,
    "scan_unc_path": None,
    "map_message": ""
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

# ============================================================
# HELPERS
# ============================================================

def normalized_lon(value):
    return ((float(value) + 180) % 360) - 180


def set_site(lat, lon):
    st.session_state.lat = round(float(lat), 5)
    st.session_state.lon = round(
        normalized_lon(lon), 5
    )


def on_map_click():
    state = st.session_state.get(
        "ofoq_selection_map", {}
    ) or {}

    point = state.get("last_clicked")

    if not point:
        return

    lat = float(point["lat"])
    lon = float(point["lng"])

    if -90 <= lat <= -75:
        set_site(lat, lon)
        st.session_state.map_message = (
            "Landing point updated."
        )
    else:
        st.session_state.map_message = (
            "Choose a point from 75°S to 90°S."
        )


def info_box(title, message):
    st.markdown(
        '<div class="note-card">'
        '<strong>' + html.escape(title) + '</strong>'
        '<p>' + html.escape(message) + '</p>'
        '</div>',
        unsafe_allow_html=True
    )


# ============================================================
# THREE.JS MOON GLOBE
# ============================================================

@st.cache_data(ttl=86400, show_spinner=False)
def get_texture():
    response = requests.get(
        MOON_TEXTURE, timeout=35
    )
    response.raise_for_status()

    return (
        "data:image/jpeg;base64,"
        + base64.b64encode(
            response.content
        ).decode("ascii")
    )


def draw_moon_globe():
    texture = get_texture()

    globe_html = """
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <style>
      body {
        margin: 0;
        background: #040a14;
        overflow: hidden;
        font-family: Arial, sans-serif;
      }
      #scene {
        width: 100%;
        height: 510px;
      }
      #hint {
        position: absolute;
        bottom: 15px;
        left: 18px;
        color: #e9f5ff;
        background: #12253ac9;
        border: 1px solid #35516b;
        border-radius: 10px;
        padding: 11px 16px;
        font-size: 13px;
      }
    </style>
    <script type="importmap">
    {
      "imports": {
        "three":
        "https://unpkg.com/three@0.160.0/build/three.module.js",
        "three/addons/":
        "https://unpkg.com/three@0.160.0/examples/jsm/"
      }
    }
    </script>
    </head>
    <body>
      <div id="scene"></div>
      <div id="hint">
        DRAG: ROTATE &nbsp; • &nbsp; SCROLL: ZOOM
      </div>

      <script type="module">
        import * as THREE from "three";
        import { OrbitControls } from
        "three/addons/controls/OrbitControls.js";

        const root = document.getElementById("scene");
        const scene = new THREE.Scene();
        const camera = new THREE.PerspectiveCamera(
          44, 1, 0.1, 100
        );

        camera.position.set(0, 0, 5);

        const renderer = new THREE.WebGLRenderer({
          antialias: true
        });

        renderer.setPixelRatio(
          Math.min(window.devicePixelRatio, 2)
        );
        root.appendChild(renderer.domElement);

        const texture = new THREE.TextureLoader().load(
          __TEXTURE__
        );
        texture.colorSpace = THREE.SRGBColorSpace;

        const moon = new THREE.Mesh(
          new THREE.SphereGeometry(1.7, 96, 72),
          new THREE.MeshStandardMaterial({
            map: texture,
            roughness: 1
          })
        );

        scene.add(moon);
        scene.add(
          new THREE.AmbientLight(0xffffff, 1.35)
        );

        const light = new THREE.DirectionalLight(
          0xffffff, 2.0
        );
        light.position.set(5, 4, 7);
        scene.add(light);

        const controls = new OrbitControls(
          camera, renderer.domElement
        );
        controls.enableDamping = true;
        controls.enablePan = false;
        controls.minDistance = 2.2;
        controls.maxDistance = 8;

        function resize() {
          const w = root.clientWidth || 800;
          renderer.setSize(w, 510);
          camera.aspect = w / 510;
          camera.updateProjectionMatrix();
        }

        window.addEventListener("resize", resize);
        resize();

        function animate() {
          requestAnimationFrame(animate);
          controls.update();
          renderer.render(scene, camera);
        }

        animate();
      </script>
    </body>
    </html>
    """

    globe_html = globe_html.replace(
        "__TEXTURE__",
        json.dumps(texture)
    )

    components.html(
        globe_html,
        height=515,
        scrolling=False
    )


# ============================================================
# LUNAR MAP
# ============================================================

def lunar_map(lat=-85, lon=0, zoom=4):
    m = folium.Map(
        location=[lat, lon],
        zoom_start=zoom,
        tiles=None,
        crs="EPSG4326",
        control_scale=True
    )

    folium.TileLayer(
        tiles=MOON_TILES,
        attr="NASA/JPL Moon Trek / LRO WAC",
        name="NASA Lunar Imagery",
        max_zoom=8,
        no_wrap=True
    ).add_to(m)

    return m


# ============================================================
# NASA HORIZONS
# ============================================================

@st.cache_data(ttl=21600, show_spinner=False)
def horizons(body, lon, lat, start_text, hours):
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

    r = requests.get(
        NASA_API,
        params=params,
        timeout=60
    )
    r.raise_for_status()

    text = r.json()["result"]

    if "$$SOE" not in text or "$$EOE" not in text:
        raise ValueError(
            "NASA returned no valid ephemeris table: "
            + text[:350]
        )

    block = text.split(
        "$$SOE", 1
    )[1].split("$$EOE", 1)[0]

    rows = []

    for line in block.splitlines():
        p = [
            x.strip()
            for x in line.split(",")
        ]

        if len(p) < 5:
            continue

        try:
            rows.append({
                "time": pd.to_datetime(
                    p[0],
                    format="%Y-%b-%d %H:%M"
                ),
                "azimuth": float(p[3]),
                "elevation": float(p[4])
            })
        except ValueError:
            continue

    if not rows:
        raise ValueError(
            "NASA returned no numeric rows."
        )

    return pd.DataFrame(rows)


def mission_analysis(lat, lon, start, hours):
    start_text = start.strftime(
        "%Y-%m-%d %H:%M"
    )

    sun = horizons(
        "10", lon, lat, start_text, hours
    )
    earth = horizons(
        "399", lon, lat, start_text, hours
    )

    df = sun[["time", "elevation"]].merge(
        earth[["time", "elevation"]],
        on="time",
        suffixes=("_sun", "_earth")
    ).sort_values("time")

    # Use each hourly sample for the following hour.
    df = df.iloc[:-1].copy()

    if len(df) != hours:
        raise ValueError(
            "NASA data is incomplete."
        )

    df["sun_visible"] = (
        df.elevation_sun > 0
    )
    df["earth_visible"] = (
        df.elevation_earth > 0
    )
    df["both_visible"] = (
        df.sun_visible & df.earth_visible
    )

    return df


def mission_metrics(df):
    return {
        "sun": int(df.sun_visible.sum()),
        "earth": int(df.earth_visible.sum()),
        "both": int(df.both_visible.sum()),
        "total": len(df)
    }


def show_mission_result(df):
    m = mission_metrics(df)

    a, b, c = st.columns(3)

    a.metric(
        "☀️ Sun above horizon",
        f"{m['sun']} h"
    )

    b.metric(
        "🌍 Earth above horizon",
        f"{m['earth']} h"
    )

    c.metric(
        "🔗 Both at once",
        f"{m['both']} h"
    )

    if m["both"] == 0:
        st.warning(
            "No simultaneous visibility was found "
            "at the sampled times."
        )
    else:
        st.success(
            "Sun and Earth are both above the "
            "reference horizon for approximately "
            f"{m['both']} sampled hours."
        )

    st.caption(
        "These are hourly geometric estimates, "
        "not terrain-aware power or radio-link predictions."
    )

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df.time,
        y=df.elevation_sun,
        name="Sun",
        mode="lines",
        line=dict(
            color="#FFD166",
            width=3
        )
    ))

    fig.add_trace(go.Scatter(
        x=df.time,
        y=df.elevation_earth,
        name="Earth",
        mode="lines",
        line=dict(
            color="#38BDF8",
            width=3
        )
    ))

    fig.add_hline(
        y=0,
        line_dash="dash",
        line_color="#F87171"
    )

    fig.update_layout(
        template="plotly_dark",
        title="Sun and Earth above the horizon",
        xaxis_title="Time (UTC)",
        yaxis_title="Elevation (degrees)",
        height=380,
        hovermode="x unified",
        margin=dict(l=20, r=20, t=55, b=25)
    )

    st.plotly_chart(
        fig, use_container_width=True
    )

    heat = go.Figure(go.Heatmap(
        x=df.time,
        y=["Sun", "Earth", "Together"],
        z=[
            df.sun_visible.astype(int).tolist(),
            df.earth_visible.astype(int).tolist(),
            df.both_visible.astype(int).tolist()
        ],
        zmin=0,
        zmax=1,
        showscale=False,
        colorscale=[
            [0, "#673348"],
            [0.499, "#673348"],
            [0.5, "#16B8A6"],
            [1, "#16B8A6"]
        ]
    ))

    heat.update_layout(
        template="plotly_dark",
        title="Operational visibility timeline",
        height=240,
        margin=dict(l=20, r=20, t=50, b=20)
    )

    st.plotly_chart(
        heat, use_container_width=True
    )

    st.caption(
        "Teal = above geometric horizon. "
        "Red = below geometric horizon."
    )

    return m


# ============================================================
# NASA TERRAIN FILE HANDLING
# ============================================================

def store_uploaded_tif(uploaded, label):
    if uploaded is None:
        return st.session_state.get(
            f"scan_{label}_path"
        )

    identity = (
        uploaded.name,
        uploaded.size
    )
    identity_key = f"scan_{label}_identity"

    if st.session_state.get(
        identity_key
    ) != identity:

        with tempfile.NamedTemporaryFile(
            suffix=".tif",
            delete=False
        ) as tmp:
            uploaded.seek(0)
            shutil.copyfileobj(uploaded, tmp)
            path = tmp.name

        old_path = st.session_state.get(
            f"scan_{label}_path"
        )

        if old_path and os.path.exists(old_path):
            try:
                os.remove(old_path)
            except OSError:
                pass

        st.session_state[
            f"scan_{label}_path"
        ] = path

        st.session_state[
            identity_key
        ] = identity

    return st.session_state[
        f"scan_{label}_path"
    ]


def file_path(label):
    path = st.session_state.get(
        f"scan_{label}_path"
    )

    if path and os.path.exists(path):
        return path

    return None


def raster_center(path):
    with rasterio.open(path) as src:
        if src.crs is None:
            raise ValueError(
                "GeoTIFF has no coordinate reference."
            )

        x = (src.bounds.left + src.bounds.right) / 2
        y = (src.bounds.bottom + src.bounds.top) / 2

        transform = Transformer.from_crs(
            src.crs,
            LUNAR_GEO,
            always_xy=True
        )

        lon, lat = transform.transform(x, y)

        return lat, normalized_lon(lon)


@st.cache_data(show_spinner=False)
def read_local_raster(path, lat, lon, size=80):
    with rasterio.open(path) as src:

        if src.crs is None:
            raise ValueError(
                "Raster coordinate system is missing."
            )

        transform = Transformer.from_crs(
            LUNAR_GEO,
            src.crs,
            always_xy=True
        )

        x, y = transform.transform(lon, lat)

        row, col = rowcol(
            src.transform, x, y
        )

        if not (
            0 <= row < src.height
            and 0 <= col < src.width
        ):
            raise ValueError(
                "Selected point is outside this "
                "NASA terrain dataset."
            )

        half = size // 2

        window = Window(
            col - half,
            row - half,
            size,
            size
        )

        masked = src.read(
            1,
            window=window,
            boundless=True,
            masked=True
        )

        data = np.ma.array(
            masked,
            dtype=float
        ).filled(np.nan)

        if src.nodata is not None:
            data[
                np.isclose(data, src.nodata)
            ] = np.nan

        dx = abs(src.transform.a)
        dy = abs(src.transform.e)

        if dx == 0 or dy == 0:
            raise ValueError(
                "Invalid raster pixel size."
            )

        return data, dx, dy


# ============================================================
# TERRAIN GRID
# ============================================================

def build_terrain_scan(lat, lon):
    slope_path = file_path("slope")
    dem_path = file_path("dem")
    uncertainty_path = file_path("unc")

    if not slope_path and not dem_path:
        return None

    elevation = None
    uncertainty = None

    if dem_path:
        elevation, dx, dy = read_local_raster(
            dem_path, lat, lon
        )

    if slope_path:
        slopes, sx, sy = read_local_raster(
            slope_path, lat, lon
        )
    else:
        if elevation is None:
            return None

        # An approximate slope derived from the DEM.
        gy, gx = np.gradient(
            elevation, dy, dx
        )

        slopes = np.degrees(
            np.arctan(
                np.sqrt(gx**2 + gy**2)
            )
        )

    if uncertainty_path:
        uncertainty, _, _ = read_local_raster(
            uncertainty_path, lat, lon
        )

    cells = []

    for r in range(8):
        for c in range(8):
            ys = slice(r * 10, (r + 1) * 10)
            xs = slice(c * 10, (c + 1) * 10)

            block = slopes[ys, xs]
            valid = block[
                np.isfinite(block)
            ]

            coverage = len(valid) / block.size

            cell = {
                "id": f"{r+1}-{c+1}",
                "row": r,
                "col": c,
                "slope": None,
                "uncertainty": None,
                "coverage": round(
                    coverage * 100, 1
                ),
                "status": "unknown"
            }

            if coverage >= 0.75:
                slope = float(
                    np.median(valid)
                )

                cell["slope"] = round(
                    slope, 2
                )

                if slope <= 5:
                    cell["status"] = "gentle"
                elif slope <= 12:
                    cell["status"] = "caution"
                else:
                    cell["status"] = "steep"

            if uncertainty is not None:
                ublock = uncertainty[ys, xs]
                uvalid = ublock[
                    np.isfinite(ublock)
                ]

                if len(uvalid):
                    cell["uncertainty"] = round(
                        float(np.median(uvalid)), 2
                    )

            cells.append(cell)

    return {
        "cells": cells,
        "elevation": elevation,
        "slopes": slopes,
        "source": (
            "NASA slope GeoTIFF"
            if slope_path
            else "Slope derived from NASA DEM"
        )
    }


# ============================================================
# ANIMATED LANDING SCAN
# ============================================================

def landing_scanner(scan=None):
    if scan:
        cells = scan["cells"]
        real_data = True
    else:
        real_data = False
        cells = [
            {
                "id": f"{r+1}-{c+1}",
                "slope": None,
                "uncertainty": None,
                "coverage": 0,
                "status": "unknown"
            }
            for r in range(8)
            for c in range(8)
        ]

    component_html = """
    <!DOCTYPE html>
    <html>
    <head>
    <style>
      * { box-sizing: border-box; }
      body {
        background: #07121f;
        color: #eaf8ff;
        font-family: Arial, sans-serif;
        margin: 0;
        padding: 12px;
      }
      .hud {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 10px;
        border: 1px solid #1f5064;
        border-radius: 10px;
        color: #5fe3dd;
        letter-spacing: 1px;
        font-size: 12px;
      }
      .screen {
        position: relative;
        overflow: hidden;
        border: 1px solid #2b5364;
        background:
          radial-gradient(
            circle at center,
            #254052 0%, #0a1725 65%,
            #06101c 100%
          );
        margin-top: 12px;
        border-radius: 14px;
        padding: 18px;
      }
      .grid {
        display: grid;
        grid-template-columns: repeat(8, 1fr);
        gap: 5px;
        width: min(100%, 550px);
        margin: auto;
        position: relative;
        z-index: 2;
      }
      .cell {
        aspect-ratio: 1;
        border: 1px solid #86d6e0;
        border-radius: 3px;
        cursor: pointer;
        opacity: .20;
        color: white;
        font-size: 11px;
        transition: transform .15s;
        animation: appear .35s forwards;
      }
      .cell:hover {
        transform: scale(1.08);
        outline: 2px solid #ffffff;
        z-index: 5;
      }
      .gentle { background: #17876f; }
      .caution { background: #ad812e; }
      .steep { background: #a63e51; }
      .unknown { background: #465369; }
      .beam {
        pointer-events: none;
        position: absolute;
        left: 0;
        right: 0;
        height: 5px;
        top: 0;
        background: #56f3e0;
        box-shadow:
          0 0 20px #56f3e0,
          0 0 55px #56f3e0;
        animation: sweep 4s linear infinite;
        opacity: .8;
      }
      .details {
        margin-top: 13px;
        border-radius: 10px;
        border: 1px solid #294b60;
        background: #10263a;
        padding: 16px;
        min-height: 84px;
        font-size: 14px;
        line-height: 1.7;
      }
      .small {
        color: #a4bdd0;
        font-size: 12px;
        margin-top: 11px;
      }
      @keyframes sweep {
        0% { top: 0; }
        100% { top: 100%; }
      }
      @keyframes appear {
        to { opacity: .90; }
      }
    </style>
    </head>
    <body>
      <div class="hud">
        <span>OFOQ / TERRAIN RECON</span>
        <span>SCANNING GRID 08 × 08</span>
      </div>

      <div class="screen">
        <div class="beam"></div>
        <div id="grid" class="grid"></div>
      </div>

      <div id="details" class="details">
        Select a cell to inspect its terrain data.
      </div>

      <div class="small">
        The scanning beam is a visualization of
        preprocessed data, not a real spacecraft sensor.
      </div>

      <script>
        const cells = __CELLS__;
        const grid = document.getElementById("grid");
        const details = document.getElementById("details");

        cells.forEach((cell, index) => {
          const el = document.createElement("button");
          el.className = "cell " + cell.status;
          el.style.animationDelay =
            (index * 0.045) + "s";
          el.title = "Cell " + cell.id;
          el.setAttribute("aria-label",
            "Inspect cell " + cell.id);

          el.onclick = () => {
            let slope = cell.slope === null
              ? "Not available"
              : cell.slope + " degrees";

            let uncertainty =
              cell.uncertainty === null
              ? "Not available"
              : cell.uncertainty + " m RMS";

            details.innerHTML =
              "<b>GRID CELL " + cell.id + "</b>" +
              "<div>Terrain screening: " +
              cell.status + "</div>" +
              "<div>Median slope: " +
              slope + "</div>" +
              "<div>Height uncertainty: " +
              uncertainty + "</div>" +
              "<div>Valid data: " +
              cell.coverage + "%</div>";
          };

          grid.appendChild(el);
        });
      </script>
    </body>
    </html>
    """

    component_html = component_html.replace(
        "__CELLS__",
        json.dumps(cells)
    )

    components.html(
        component_html,
        height=740,
        scrolling=False
    )

    if real_data:
        valid = [
            x for x in cells
            if x["slope"] is not None
        ]

        if valid:
            best = min(
                valid,
                key=lambda x: x["slope"]
            )

            st.info(
                "Lowest median slope in this scan: "
                f"cell {best['id']} "
                f"({best['slope']}°). "
                "This is not proof of safe landing."
            )

        st.caption(
            "Illustrative screening thresholds: "
            "gentle ≤5°, caution 5–12°, steep >12°. "
            "These are OFOQ prototype thresholds, "
            "not NASA-approved landing criteria."
        )
    else:
        st.warning(
            "Terrain data not loaded. "
            "The scanner animation is active, "
            "but all cells remain unassessed."
        )


# ============================================================
# VIRTUAL SURFACE VIEW
# ============================================================

def show_surface_3d(scan):
    elevation = scan.get("elevation")

    if elevation is None:
        st.warning(
            "A local NASA DEM is required for "
            "a terrain-based surface perspective."
        )
        return

    if not np.isfinite(elevation).any():
        st.warning(
            "No valid elevation values here."
        )
        return

    z = elevation.copy()
    z = z - np.nanmedian(z)

    yy, xx = np.indices(z.shape)

    fig = go.Figure(go.Surface(
        x=xx * 5,
        y=yy * 5,
        z=z,
        colorscale="Greys",
        showscale=False
    ))

    fig.update_layout(
        title="Virtual Terrain View — NASA DEM",
        template="plotly_dark",
        height=540,
        scene=dict(
            xaxis_title="Local X (approx. m)",
            yaxis_title="Local Y (approx. m)",
            zaxis_title="Relative height (m)",
            camera=dict(
                eye=dict(x=0.15, y=-1.9, z=0.65)
            ),
            aspectmode="manual",
            aspectratio=dict(x=1, y=1, z=0.35)
        )
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )

    st.caption(
        "Computer-generated 3D terrain based on "
        "NASA elevation data. Not an actual "
        "lander-camera photograph. Height appearance "
        "is exaggerated for visual clarity."
    )


# ============================================================
# NAVIGATION
# ============================================================

with st.sidebar:
    st.markdown("## 🌙 OFOQ")
    st.caption("LUNAR MISSION CONTROL")

    page = st.radio(
        "Explore",
        [
            "01 / Moon Explorer",
            "02 / Choose Landing Point",
            "03 / Landing Scanner",
            "04 / Lander View",
            "05 / Mission Windows",
            "06 / Plan B Comparison",
            "07 / Science & Sources"
        ]
    )

    st.divider()

    st.caption("CURRENT SELECTED POINT")

    st.write(
        f"**Latitude:** {st.session_state.lat:.5f}°"
    )
    st.write(
        f"**Longitude:** {st.session_state.lon:.5f}°"
    )

    st.divider()

    mission_date = st.date_input(
        "Landing date (UTC)",
        value=date(2026, 11, 14)
    )

    mission_hours = st.slider(
        "Mission duration (hours)",
        min_value=24,
        max_value=96,
        value=48,
        step=12
    )

    st.caption(
        "NASA data source: JPL Horizons"
    )

# ============================================================
# PAGE 1 — MOON EXPLORER
# ============================================================

if page == "01 / Moon Explorer":
    st.markdown(
        '<div class="section-label">'
        '01 / EXPLORE</div>',
        unsafe_allow_html=True
    )

    st.header("The Moon is your mission map")

    left, right = st.columns(
        [3, 1], gap="large"
    )

    with left:
        try:
            draw_moon_globe()
        except Exception as error:
            st.warning(
                "3D globe unavailable. "
                "The other mission tools still work."
            )
            st.caption(str(error))

    with right:
        info_box(
            "Rotate the Moon",
            "Drag to rotate. Scroll to zoom in. "
            "This globe uses lunar imagery."
        )

        info_box(
            "Choose a location",
            "Open Choose Landing Point to click "
            "on real lunar imagery and select "
            "coordinates."
        )

        info_box(
            "Explore conditions",
            "Analyze sunlight, Earth visibility, "
            "terrain, and possible mission delays."
        )

    st.caption(
        "3D globe imagery: NASA Scientific "
        "Visualization Studio / LRO. "
        "The globe is an exploration model."
    )

# ============================================================
# PAGE 2 — CHOOSE A LANDING POINT
# ============================================================

elif page == "02 / Choose Landing Point":
    st.markdown(
        '<div class="section-label">'
        '02 / LANDING SITE SELECTION</div>',
        unsafe_allow_html=True
    )

    st.header("Where should we investigate?")

    st.write(
        "Move around the lunar map and click "
        "a point near the south pole."
    )

    m = lunar_map(-85, 0, 4)

    marker_layer = folium.FeatureGroup(
        name="Selected Point"
    )

    folium.CircleMarker(
        location=[
            st.session_state.lat,
            st.session_state.lon
        ],
        radius=8,
        color="#57F2E6",
        fill=True,
        fill_color="#57F2E6",
        fill_opacity=0.95,
        tooltip="Current lunar location"
    ).add_to(marker_layer)

    st_folium(
        m,
        key="ofoq_selection_map",
        height=530,
        use_container_width=True,
        returned_objects=["last_clicked"],
        on_change=on_map_click,
        feature_group_to_add=marker_layer
    )

    st.success(
        "Selected location: "
        f"{st.session_state.lat:.5f}°, "
        f"{st.session_state.lon:.5f}°"
    )

    if st.session_state.map_message:
        st.caption(
            st.session_state.map_message
        )

    with st.expander(
        "Enter coordinates manually"
    ):
        with st.form("manual_coordinates"):
            lat = st.number_input(
                "Latitude (°)",
                min_value=-90.0,
                max_value=-75.0,
                value=float(
                    st.session_state.lat
                ),
                format="%.5f"
            )

            lon = st.number_input(
                "Longitude (°)",
                min_value=-180.0,
                max_value=180.0,
                value=float(
                    st.session_state.lon
                ),
                format="%.5f"
            )

            apply = st.form_submit_button(
                "Use this point"
            )

            if apply:
                set_site(lat, lon)
                st.rerun()

    st.warning(
        "This is a selected investigation point, "
        "not a certified safe landing site."
    )

    st.caption(
        "NASA Moon Trek WAC imagery. "
        "This global map projection distorts "
        "the shape of features near the pole."
    )

# ============================================================
# PAGE 3 — LANDING SCANNER
# ============================================================

elif page == "03 / Landing Scanner":
    st.markdown(
        '<div class="section-label">'
        '03 / TERRAIN RECONNAISSANCE</div>',
        unsafe_allow_html=True
    )

    st.header("Landing Terrain Scanner")

    st.write(
        "Inspect a grid of terrain cells. "
        "The colors describe slope categories "
        "only when NASA raster data is available."
    )

    with st.expander(
        "Load NASA terrain data",
        expanded=True
    ):
        st.markdown(
            "Download suitable **Site01** files from "
            f"[NASA's official repository]({NASA_DEM_PAGE})."
        )

        slope_file = st.file_uploader(
            "Slope GeoTIFF (.tif)",
            type=["tif", "tiff"],
            key="upload_slope"
        )

        dem_file = st.file_uploader(
            "Elevation DEM GeoTIFF (.tif)",
            type=["tif", "tiff"],
            key="upload_dem"
        )

        unc_file = st.file_uploader(
            "Elevation uncertainty GeoTIFF (.tif)",
            type=["tif", "tiff"],
            key="upload_unc"
        )

        store_uploaded_tif(
            slope_file, "slope"
        )
        store_uploaded_tif(
            dem_file, "dem"
        )
        store_uploaded_tif(
            unc_file, "unc"
        )

        available = (
            file_path("slope")
            or file_path("dem")
        )

        if available and st.button(
            "Use center of loaded terrain"
        ):
            try:
                lat, lon = raster_center(
                    available
                )
                set_site(lat, lon)
                st.rerun()
            except Exception as error:
                st.error(str(error))

    scan = None

    if file_path("slope") or file_path("dem"):
        try:
            scan = build_terrain_scan(
                st.session_state.lat,
                st.session_state.lon
            )

            st.success(
                "NASA terrain data loaded for "
                "the current location."
            )
        except Exception as error:
            st.warning(
                "Terrain scan unavailable: "
                + str(error)
            )

    landing_scanner(scan)

    if scan:
        rows = pd.DataFrame(scan["cells"])

        st.download_button(
            "Download terrain scan CSV",
            data=rows.to_csv(index=False),
            file_name="OFOQ_terrain_scan.csv",
            mime="text/csv"
        )

    info_box(
        "How to interpret the scan",
        "Green means lower measured slope. "
        "Amber means moderate slope. "
        "Red means steeper terrain. "
        "Gray means insufficient data. "
        "None of these colors guarantees "
        "that a landing is safe."
    )

# ============================================================
# PAGE 4 — LANDER VIEW
# ============================================================

elif page == "04 / Lander View":
    st.markdown(
        '<div class="section-label">'
        '04 / SURFACE PERSPECTIVE</div>',
        unsafe_allow_html=True
    )

    st.header("Lander Reconnaissance View")

    st.write(
        "Inspect the landscape near the "
        "selected site."
    )

    if file_path("dem"):
        try:
            scan = build_terrain_scan(
                st.session_state.lat,
                st.session_state.lon
            )

            show_surface_3d(scan)
        except Exception as error:
            st.warning(str(error))

    else:
        st.info(
            "Upload a NASA elevation DEM in "
            "Landing Scanner to unlock the "
            "terrain-based virtual camera."
        )

    st.subheader("Actual lunar orbital imagery")

    st_folium(
        lunar_map(
            st.session_state.lat,
            st.session_state.lon,
            zoom=7
        ),
        height=470,
        use_container_width=True,
        key="surface_orbit_view"
    )

    st.caption(
        "The image above is orbital imagery, "
        "not a photograph from a lander "
        "at the selected point."
    )

# ============================================================
# PAGE 5 — MISSION WINDOWS
# ============================================================

elif page == "05 / Mission Windows":
    st.markdown(
        '<div class="section-label">'
        '05 / SUNLIGHT AND COMMUNICATION</div>',
        unsafe_allow_html=True
    )

    st.header("Can the lander see the Sun and Earth?")

    st.write(
        "This tool calculates the Sun and "
        "Earth's apparent positions from "
        "your selected lunar location."
    )

    st.info(
        "The results show geometric visibility. "
        "Nearby mountains and crater walls "
        "are not yet included."
    )

    if st.button(
        "Calculate NASA visibility",
        type="primary"
    ):
        start = datetime.combine(
            mission_date,
            time(0, 0)
        )

        try:
            with st.spinner(
                "Calculating with NASA Horizons..."
            ):
                df = mission_analysis(
                    st.session_state.lat,
                    st.session_state.lon,
                    start,
                    mission_hours
                )

            st.session_state["mission_result"] = (
                df,
                (
                    st.session_state.lat,
                    st.session_state.lon,
                    mission_date,
                    mission_hours
                )
            )

        except Exception as error:
            st.error(str(error))

    stored = st.session_state.get(
        "mission_result"
    )

    signature = (
        st.session_state.lat,
        st.session_state.lon,
        mission_date,
        mission_hours
    )

    if stored and stored[1] == signature:
        df = stored[0]
        show_mission_result(df)

        st.download_button(
            "Download NASA mission data",
            data=df.to_csv(index=False),
            file_name="OFOQ_visibility.csv",
            mime="text/csv"
        )
    else:
        st.caption(
            "Choose a location and press "
            "Calculate NASA visibility."
        )

# ============================================================
# PAGE 6 — PLAN B
# ============================================================

elif page == "06 / Plan B Comparison":
    st.markdown(
        '<div class="section-label">'
        '06 / MISSION REPLANNING</div>',
        unsafe_allow_html=True
    )

    st.header("What if the landing plan changes?")

    comparison_mode = st.radio(
        "What would you like to change?",
        [
            "Delay landing at the same site",
            "Change site on the same date"
        ]
    )

    start = datetime.combine(
        mission_date,
        time(0, 0)
    )

    alt_lat = st.session_state.lat
    alt_lon = st.session_state.lon
    alt_start = start

    if comparison_mode.startswith("Delay"):
        delay = st.slider(
            "Delay in hours",
            min_value=0,
            max_value=168,
            value=48,
            step=12
        )

        alt_start = start + timedelta(
            hours=delay
        )

    else:
        a, b = st.columns(2)

        alt_lat = a.number_input(
            "Alternative latitude",
            min_value=-90.0,
            max_value=-75.0,
            value=-85.0
        )

        alt_lon = b.number_input(
            "Alternative longitude",
            min_value=-180.0,
            max_value=180.0,
            value=0.0
        )

    if st.button(
        "Compare mission plans",
        type="primary"
    ):
        try:
            with st.spinner(
                "Calculating both scenarios..."
            ):
                original = mission_analysis(
                    st.session_state.lat,
                    st.session_state.lon,
                    start,
                    mission_hours
                )

                alternative = mission_analysis(
                    alt_lat,
                    alt_lon,
                    alt_start,
                    mission_hours
                )

            m1 = mission_metrics(original)
            m2 = mission_metrics(alternative)

            left, right = st.columns(2)

            with left:
                st.subheader("Original plan")
                st.metric(
                    "Sun visible",
                    f"{m1['sun']} h"
                )
                st.metric(
                    "Earth visible",
                    f"{m1['earth']} h"
                )
                st.metric(
                    "Both visible",
                    f"{m1['both']} h"
                )

            with right:
                st.subheader("Alternative plan")
                st.metric(
                    "Sun visible",
                    f"{m2['sun']} h",
                    delta=(
                        m2["sun"] - m1["sun"]
                    )
                )
                st.metric(
                    "Earth visible",
                    f"{m2['earth']} h",
                    delta=(
                        m2["earth"] - m1["earth"]
                    )
                )
                st.metric(
                    "Both visible",
                    f"{m2['both']} h",
                    delta=(
                        m2["both"] - m1["both"]
                    )
                )

            diff = m2["both"] - m1["both"]

            if diff > 0:
                st.success(
                    "The alternative has more "
                    "sampled simultaneous visibility."
                )
            elif diff < 0:
                st.warning(
                    "The alternative has less "
                    "sampled simultaneous visibility."
                )
            else:
                st.info(
                    "Both plans have the same "
                    "sampled simultaneous visibility."
                )

            st.caption(
                "Comparison changes only one "
                "factor at a time: either date "
                "or site. Results are geometric."
            )

            chart = go.Figure()

            chart.add_trace(go.Bar(
                name="Original",
                x=["Sun", "Earth", "Both"],
                y=[
                    m1["sun"],
                    m1["earth"],
                    m1["both"]
                ]
            ))

            chart.add_trace(go.Bar(
                name="Alternative",
                x=["Sun", "Earth", "Both"],
                y=[
                    m2["sun"],
                    m2["earth"],
                    m2["both"]
                ]
            ))

            chart.update_layout(
                barmode="group",
                template="plotly_dark",
                height=380,
                title="Visibility hours comparison",
                yaxis_title="Approximate sampled hours"
            )

            st.plotly_chart(
                chart, use_container_width=True
            )

        except Exception as error:
            st.error(str(error))

# ============================================================
# PAGE 7 — SCIENCE
# ============================================================

else:
    st.markdown(
        '<div class="section-label">'
        '07 / SCIENCE AND TRANSPARENCY</div>',
        unsafe_allow_html=True
    )

    st.header("How OFOQ works")

    info_box(
        "Where do the positions come from?",
        "NASA JPL Horizons calculates the "
        "positions of the Sun and Earth as "
        "seen from a lunar location."
    )

    info_box(
        "What does the terrain scanner measure?",
        "It uses NASA elevation or slope "
        "GeoTIFF data to compare small areas "
        "of lunar terrain."
    )

    info_box(
        "Does green mean safe landing?",
        "No. A low slope alone does not "
        "guarantee safety. Boulders, craters, "
        "spacecraft dimensions, data gaps, "
        "and landing dynamics also matter."
    )

    info_box(
        "Is the lander camera real?",
        "No. When NASA elevation data is "
        "loaded, OFOQ can create a virtual "
        "3D terrain perspective."
    )

    info_box(
        "Why not use a single risk score?",
        "Different missions have different "
        "requirements. OFOQ keeps the "
        "underlying terrain and visibility "
        "measurements visible."
    )

    st.markdown(
        """
        ### Scientific sources

        - [NASA JPL Horizons](https://ssd.jpl.nasa.gov/horizons/)
        - [Horizons API documentation](https://ssd-api.jpl.nasa.gov/doc/horizons.html)
        - [NASA Moon Trek](https://trek.nasa.gov/moon/)
        - [NASA CGI Moon Kit](https://svs.gsfc.nasa.gov/4720/)
        - [NASA South Pole LOLA Terrain](https://pgda.gsfc.nasa.gov/products/78)

        ### Current limitations

        - Hourly samples approximate visibility durations.
        - Local horizon obstruction is not calculated yet.
        - Direct-to-Earth visibility is not a radio-link guarantee.
        - Terrain thresholds are prototype heuristics.
        - Small obstacles may not be resolved by the source DEM.
        - The virtual surface view is not a real spacecraft image.
        """
    )

st.divider()

st.caption(
    "OFOQ | NASA Space Apps Challenge 2026 "
    "— Prototype decision-support experience. "
    "NASA data is credited to its original providers. "
    "OFOQ is not an official NASA mission-planning tool."
)
