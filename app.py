import streamlit as st
import streamlit.components.v1 as components
from streamlit_folium import st_folium
import folium
import pandas as pd
import numpy as np
import requests
import plotly.graph_objects as go
import tifffile

from io import BytesIO
from datetime import datetime, date, time, timedelta
import base64
import json

# =====================================================
# OFOQ v4 | LUNAR MISSION EXPLORER
# =====================================================

st.set_page_config(
    page_title="OFOQ | Lunar Mission Explorer",
    page_icon="🌙",
    layout="wide",
    initial_sidebar_state="expanded"
)

API = "https://ssd.jpl.nasa.gov/api/horizons.api"

BASE = (
    "https://svs.gsfc.nasa.gov/vis/"
    "a000000/a004700/a004720/"
)

TEXTURE_URL = BASE + "lroc_color_2k.jpg"

DEM_URLS = [
    (BASE + "ldem_16_uint.tif", 16, "uint"),
    (BASE + "ldem_4.tif", 4, "float")
]

MOON_TILES = (
    "https://trek.nasa.gov/tiles/Moon/EQ/"
    "LRO_WAC_Mosaic_Global_303ppd_v02/"
    "1.0.0/default/default028mm/"
    "{z}/{y}/{x}.jpg"
)

RADIUS_M = 1737400.0

# =====================================================
# COLORS AND DESIGN
# =====================================================

st.markdown("""
<style>
.stApp {
    color: #e7f3ff;
    background:
      radial-gradient(
        ellipse at 75% 0%,
        #152e49 0%,
        #081526 42%,
        #050b15 100%
      );
}
[data-testid="stSidebar"] {
    background: #0a1729;
    border-right: 1px solid #29415e;
}
.block-container {
    max-width: 1520px;
    padding-top: 1rem;
}
h1, h2, h3 {
    color: #ecf7ff !important;
}
.ofoq-hero {
    border: 1px solid #365875;
    border-radius: 20px;
    background:
      linear-gradient(110deg,
      #081525, #112d48, #0b1c30);
    padding: 24px 30px;
    margin-bottom: 22px;
}
.ofoq-logo {
    font-size: 39px;
    font-weight: 800;
    color: #dceef9;
    letter-spacing: 3px;
}
.ofoq-sub {
    color: #8ec9f1;
    font-size: 12px;
    letter-spacing: 2px;
    font-weight: 700;
}
.ofoq-hero p {
    color: #bbcee0;
    margin-top: 12px;
}
[data-testid="stMetric"] {
    background: #12263e;
    border: 1px solid #31516b;
    border-radius: 13px;
    padding: 15px;
}
.stButton button {
    border-radius: 10px;
}
.stButton button[kind="primary"] {
    background: #71c5f5;
    color: #06111e;
    font-weight: 800;
    border: 0;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="ofoq-hero">
    <div class="ofoq-sub">
        BEYOND THE HORIZON, TOWARD THE MOON
    </div>
    <div class="ofoq-logo">أُفُق | OFOQ</div>
    <p>
       Explore real lunar terrain.
       Choose a location with one click.
       Analyze mission conditions using NASA data.
    </p>
</div>
""", unsafe_allow_html=True)

# =====================================================
# SHARED STATE
# =====================================================

if "lat" not in st.session_state:
    st.session_state.lat = -89.0

if "lon" not in st.session_state:
    st.session_state.lon = 0.0

if "map_message" not in st.session_state:
    st.session_state.map_message = ""

if "visibility_result" not in st.session_state:
    st.session_state.visibility_result = None


def normalize_lon(lon):
    return ((float(lon) + 180) % 360) - 180


def select_location(lat, lon):
    st.session_state.lat = round(float(lat), 5)
    st.session_state.lon = round(
        normalize_lon(lon), 5
    )


# =====================================================
# NASA IMAGE AND TERRAIN DATA
# =====================================================

@st.cache_data(ttl=86400, show_spinner=False)
def load_moon_texture():
    response = requests.get(
        TEXTURE_URL, timeout=35
    )
    response.raise_for_status()
    return (
        "data:image/jpeg;base64,"
        + base64.b64encode(
            response.content
        ).decode("ascii")
    )


@st.cache_data(ttl=86400, show_spinner=False)
def load_global_dem():
    """
    Automatically downloads real NASA LOLA terrain.
    First try 16 pixels/degree, then 4.
    This is regional topography, NOT landing hazard data.
    """
    errors = []

    for url, resolution, kind in DEM_URLS:
        try:
            response = requests.get(
                url, timeout=90
            )
            response.raise_for_status()

            array = tifffile.imread(
                BytesIO(response.content)
            )

            return array, resolution, kind

        except Exception as error:
            errors.append(str(error))

    raise RuntimeError(
        "NASA DEM could not be loaded: "
        + "; ".join(errors)
    )


def sample_lunar_terrain(
    lat, lon, radius_km=12, count=73
):
    """
    Sample a regional 24 km x 24 km area.

    Lunar global DEM is an equirectangular image:
    x = longitude, y = latitude.
    Pixel interpolation does not improve source resolution.
    """

    source, ppd, kind = load_global_dem()

    height, width = source.shape[:2]

    distance = radius_km * 1000.0

    axis = np.linspace(
        -distance, distance, count
    )

    xx, yy = np.meshgrid(axis, axis)

    lat_grid = (
        lat
        + np.degrees(yy / RADIUS_M)
    )

    cosine = max(
        abs(np.cos(np.radians(lat))),
        0.01
    )

    lon_grid = (
        lon
        + np.degrees(
            xx / (RADIUS_M * cosine)
        )
    )

    lat_grid = np.clip(
        lat_grid, -90, 90
    )

    lon_grid = (
        (lon_grid + 180) % 360
    ) - 180

    px = (
        (lon_grid + 180) * ppd - 0.5
    ) % width

    py = (
        (90 - lat_grid) * ppd - 0.5
    )

    py = np.clip(py, 0, height - 1.001)

    x0 = np.floor(px).astype(int)
    y0 = np.floor(py).astype(int)

    x1 = (x0 + 1) % width
    y1 = np.minimum(y0 + 1, height - 1)

    fx = px - x0
    fy = py - y0

    a = source[y0, x0].astype(float)
    b = source[y0, x1].astype(float)
    c = source[y1, x0].astype(float)
    d = source[y1, x1].astype(float)

    values = (
        a * (1 - fx) * (1 - fy)
        + b * fx * (1 - fy)
        + c * (1 - fx) * fy
        + d * fx * fy
    )

    if kind == "uint":
        # NASA unsigned DEM uses half-meter units
        # offset by +20,000.
        elevations = (
            values - 20000
        ) / 2.0
    else:
        # Floating TIFF uses kilometers.
        elevations = values * 1000.0

    return axis, elevations, ppd


# =====================================================
# CLICKABLE 2D LUNAR MAP
# =====================================================

def map_click_callback():
    state = st.session_state.get(
        "ofoq_clickable_map", {}
    ) or {}

    point = state.get("last_clicked")

    if point is None:
        return

    lat = float(point["lat"])
    lon = float(point["lng"])

    if -90 <= lat <= -75:
        select_location(lat, lon)
        st.session_state.map_message = (
            "Location selected successfully."
        )
    else:
        st.session_state.map_message = (
            "Choose a point between 75°S "
            "and 90°S."
        )


def make_locked_map():
    moon = folium.Map(
        location=[-83.0, 0.0],
        zoom_start=5,
        min_zoom=5,
        max_zoom=8,
        tiles=None,
        crs="EPSG4326",
        zoom_control=True,
        control_scale=False
    )

    # Restrict movement to the lunar south-pole area.
    moon.options["maxBounds"] = [
        [-90, -180],
        [-75, 180]
    ]
    moon.options["maxBoundsViscosity"] = 1.0
    moon.options["worldCopyJump"] = False

    # Dark fallback outside any missing image tiles.
    moon.get_root().header.add_child(
        folium.Element("""
        <style>
        .leaflet-container {
            background: #071526 !important;
        }
        </style>
        """)
    )

    folium.TileLayer(
        tiles=MOON_TILES,
        attr="NASA/JPL Moon Trek — LRO WAC",
        name="Lunar surface imagery",
        overlay=False,
        control=False,
        no_wrap=True,
        max_zoom=8
    ).add_to(moon)

    return moon


def show_clickable_map():
    m = make_locked_map()

    markers = folium.FeatureGroup(
        name="Selected location"
    )

    folium.CircleMarker(
        location=[
            st.session_state.lat,
            st.session_state.lon
        ],
        radius=8,
        color="#83dfff",
        weight=3,
        fill=True,
        fill_color="#40b7f5",
        fill_opacity=0.95,
        tooltip="Your selected site"
    ).add_to(markers)

    st_folium(
        m,
        key="ofoq_clickable_map",
        height=540,
        use_container_width=True,
        returned_objects=["last_clicked"],
        on_change=map_click_callback,
        feature_group_to_add=markers,
        wrap_longitude=False
    )

    a, b = st.columns(2)

    a.metric(
        "Selected latitude",
        f"{st.session_state.lat:.5f}°"
    )

    b.metric(
        "Selected longitude",
        f"{st.session_state.lon:.5f}°"
    )

    if st.session_state.map_message:
        st.caption(
            st.session_state.map_message
        )

    st.info(
        "Click any point on the lunar map. "
        "The marker and coordinates update automatically."
    )


# =====================================================
# ROTATING 3D MOON
# =====================================================

def show_3d_moon():
    texture = load_moon_texture()

    page = """
    <html>
    <head>
    <style>
      body {
        background:#060d18;
        margin:0;
        overflow:hidden;
        font-family:Arial;
      }
      #scene {
        width:100%;
        height:520px;
      }
      .label {
        position:absolute;
        left:15px;
        bottom:15px;
        padding:10px 15px;
        color:#c4e9ff;
        background:#0d243bcc;
        border:1px solid #315b83;
        border-radius:10px;
        font-size:13px;
      }
    </style>
    <script type="importmap">
    {
      "imports":{
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
      <div class="label">
        Drag to rotate • Scroll to zoom
      </div>
      <script type="module">
        import * as THREE from "three";
        import { OrbitControls } from
          "three/addons/controls/OrbitControls.js";

        const root = document.getElementById("scene");
        const scene = new THREE.Scene();

        const camera = new THREE.PerspectiveCamera(
          43, 1, 0.1, 100
        );

        camera.position.set(0,0,5);

        const renderer = new THREE.WebGLRenderer({
          antialias:true
        });

        renderer.setPixelRatio(
          Math.min(window.devicePixelRatio,2)
        );
        root.appendChild(renderer.domElement);

        const tex = new THREE.TextureLoader().load(
          __TEXTURE__
        );
        tex.colorSpace = THREE.SRGBColorSpace;

        const moon = new THREE.Mesh(
          new THREE.SphereGeometry(1.7,96,72),
          new THREE.MeshStandardMaterial({
            map:tex,
            roughness:1
          })
        );

        scene.add(moon);
        scene.add(
          new THREE.AmbientLight(0xffffff,1.4)
        );

        const light = new THREE.DirectionalLight(
          0xffffff,2
        );
        light.position.set(4,3,6);
        scene.add(light);

        const controls = new OrbitControls(
          camera,renderer.domElement
        );

        controls.enableDamping = true;
        controls.enablePan = false;
        controls.minDistance = 2.2;
        controls.maxDistance = 8;

        function resize(){
          const w = root.clientWidth || 800;
          renderer.setSize(w,520);
          camera.aspect = w/520;
          camera.updateProjectionMatrix();
        }

        window.addEventListener("resize",resize);
        resize();

        function animate(){
          requestAnimationFrame(animate);
          controls.update();
          renderer.render(scene,camera);
        }
        animate();
      </script>
    </body>
    </html>
    """

    page = page.replace(
        "__TEXTURE__",
        json.dumps(texture)
    )

    components.html(
        page,
        height=525,
        scrolling=False
    )


# =====================================================
# ACTUAL REGIONAL TERRAIN SCANNER
# =====================================================

def create_scan_cells(z):
    n = z.shape[0]
    cells = []

    low = float(np.nanquantile(z, 0.33))
    high = float(np.nanquantile(z, 0.67))

    for row in range(8):
        for col in range(8):

            r0 = round(row * n / 8)
            r1 = round((row + 1) * n / 8)

            c0 = round(col * n / 8)
            c1 = round((col + 1) * n / 8)

            block = z[r0:r1, c0:c1]

            median = float(
                np.nanmedian(block)
            )

            if median < low:
                category = "lower"
            elif median > high:
                category = "higher"
            else:
                category = "middle"

            cells.append({
                "id": f"{row+1}-{col+1}",
                "height": round(median, 1),
                "category": category
            })

    return cells


def show_scanner(cells):
    code = """
    <html>
    <head>
    <style>
    body {
      background:#071323;
      color:#e6f6ff;
      margin:0;
      padding:14px;
      font-family:Arial;
    }
    .head {
      display:flex;
      justify-content:space-between;
      color:#8dd9fb;
      padding:12px;
      border:1px solid #294b67;
      border-radius:10px;
      font-size:12px;
    }
    .frame {
      margin-top:13px;
      padding:20px;
      position:relative;
      overflow:hidden;
      background:#0d2035;
      border:1px solid #345572;
      border-radius:14px;
    }
    .grid {
      display:grid;
      grid-template-columns:repeat(8,1fr);
      gap:5px;
      max-width:560px;
      margin:auto;
    }
    .cell {
      aspect-ratio:1;
      border:1px solid #8abfe0;
      border-radius:3px;
      opacity:.92;
      cursor:pointer;
    }
    .cell:hover {
      outline:2px solid white;
      transform:scale(1.05);
    }
    .lower { background:#203c68; }
    .middle { background:#347da7; }
    .higher { background:#8dccf0; }
    .beam {
      position:absolute;
      left:0;
      width:100%;
      height:4px;
      background:#d9f5ff;
      box-shadow:0 0 24px #58d8ff;
      pointer-events:none;
      animation:sweep 4s linear infinite;
    }
    @keyframes sweep {
      from { top:0%; }
      to { top:100%; }
    }
    #details {
      padding:16px;
      margin-top:12px;
      background:#102a43;
      border:1px solid #345572;
      border-radius:12px;
      min-height:65px;
    }
    </style>
    </head>
    <body>
      <div class="head">
        <span>OFOQ / REGIONAL TERRAIN SCAN</span>
        <span>NASA LOLA DATA</span>
      </div>
      <div class="frame">
        <div class="beam"></div>
        <div class="grid" id="grid"></div>
      </div>
      <div id="details">
        Click a cell to inspect its elevation.
      </div>
      <script>
        const cells = __CELLS__;
        const grid = document.getElementById("grid");
        const details = document.getElementById("details");

        cells.forEach(cell => {
          const b = document.createElement("button");
          b.className = "cell " + cell.category;
          b.title = "Cell " + cell.id;

          b.onclick = () => {
            details.textContent =
              "Cell " + cell.id +
              " | Regional elevation: " +
              cell.height + " meters" +
              " | Relative category: " +
              cell.category;
          };

          grid.appendChild(b);
        });
      </script>
    </body>
    </html>
    """

    code = code.replace(
        "__CELLS__",
        json.dumps(cells)
    )

    components.html(
        code,
        height=700,
        scrolling=False
    )


# =====================================================
# DIFFERENT VIEW: VIRTUAL LANDER CAMERA
# =====================================================

def show_lander_camera(z):
    """
    Build a low-angle 3D terrain experience
    from actual NASA global DEM elevations.
    The terrain is vertically exaggerated.
    """

    relative = z - np.nanmedian(z)

    # Visual vertical scale only.
    heights = np.clip(
        relative / 600.0,
        -1.7,
        1.7
    )

    heights = np.nan_to_num(heights)

    data = heights.tolist()

    code = """
    <html>
    <head>
    <style>
      body {
        margin:0;
        overflow:hidden;
        background:#050d19;
        font-family:Arial;
      }
      #scene {
        width:100%;
        height:540px;
      }
      .camera-hud {
        position:absolute;
        top:15px;
        left:16px;
        color:#aee5ff;
        padding:10px 15px;
        background:#0c243bd9;
        border:1px solid #366b8e;
        border-radius:9px;
        font-size:12px;
      }
      .reticle {
        position:absolute;
        top:50%;
        left:50%;
        width:32px;
        height:32px;
        margin:-16px;
        border:1px solid #a7e7ff;
        border-radius:50%;
        pointer-events:none;
      }
      .reticle:after {
        content:"+";
        display:block;
        color:#a7e7ff;
        text-align:center;
        font-size:23px;
        line-height:30px;
      }
      .bottom {
        position:absolute;
        bottom:13px;
        left:15px;
        background:#10263ddd;
        color:#dcefff;
        border-radius:8px;
        padding:10px;
        font-size:12px;
      }
    </style>
    <script type="importmap">
    {
      "imports":{
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
      <div class="camera-hud">
        OFOQ / VIRTUAL LANDER VIEW<br>
        TERRAIN RECONNAISSANCE
      </div>
      <div class="reticle"></div>
      <div class="bottom">
        Drag to look around · Scroll to zoom<br>
        Simulated view based on NASA elevations
      </div>
      <script type="module">
      import * as THREE from "three";
      import { OrbitControls } from
        "three/addons/controls/OrbitControls.js";

      const values = __HEIGHTS__;
      const n = values.length;

      const root = document.getElementById("scene");
      const scene = new THREE.Scene();
      scene.background = new THREE.Color(0x050d19);

      const camera = new THREE.PerspectiveCamera(
        68, 1, 0.1, 100
      );

      camera.position.set(0,2.8,7.5);

      const renderer = new THREE.WebGLRenderer({
        antialias:true
      });

      renderer.setPixelRatio(
        Math.min(window.devicePixelRatio,2)
      );

      root.appendChild(renderer.domElement);

      const geometry = new THREE.PlaneGeometry(
        12,12,n-1,n-1
      );

      const pos = geometry.attributes.position;

      for (let row=0;row<n;row++){
        for (let col=0;col<n;col++){
          let index = row*n+col;
          pos.setZ(index,values[row][col]);
        }
      }

      geometry.computeVertexNormals();

      const material = new THREE.MeshStandardMaterial({
        color:0xadb6c4,
        roughness:1,
        side:THREE.DoubleSide
      });

      const terrain = new THREE.Mesh(
        geometry,material
      );

      terrain.rotation.x=-Math.PI/2;
      scene.add(terrain);

      scene.add(
        new THREE.AmbientLight(0xffffff,1.3)
      );

      const sun = new THREE.DirectionalLight(
        0xe3f2ff,2.3
      );

      sun.position.set(-4,8,5);
      scene.add(sun);

      const grid = new THREE.GridHelper(
        12,8,0x76d7ff,0x31546c
      );

      grid.position.y=2.0;
      scene.add(grid);

      const beam = new THREE.Mesh(
        new THREE.PlaneGeometry(12,0.06),
        new THREE.MeshBasicMaterial({
          color:0xa7eaff,
          side:THREE.DoubleSide
        })
      );

      beam.rotation.x=-Math.PI/2;
      beam.position.y=2.07;
      scene.add(beam);

      const controls = new OrbitControls(
        camera,renderer.domElement
      );

      controls.enableDamping=true;
      controls.enablePan=false;
      controls.minDistance=2.0;
      controls.maxDistance=13.0;
      controls.maxPolarAngle=Math.PI/2.1;

      function resize(){
        const w=root.clientWidth || 800;
        renderer.setSize(w,540);
        camera.aspect=w/540;
        camera.updateProjectionMatrix();
      }

      window.addEventListener("resize",resize);
      resize();

      function animate(){
        requestAnimationFrame(animate);
        beam.position.z=
          -6 + (performance.now()%4500)/4500*12;
        controls.update();
        renderer.render(scene,camera);
      }

      animate();
      </script>
    </body>
    </html>
    """

    code = code.replace(
        "__HEIGHTS__",
        json.dumps(data)
    )

    components.html(
        code,
        height=545,
        scrolling=False
    )


# =====================================================
# NASA HORIZONS — SUN AND EARTH
# =====================================================

@st.cache_data(ttl=21600, show_spinner=False)
def get_horizons(body, lat, lon, start_text, hours):
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
        API, params=params, timeout=60
    )

    response.raise_for_status()

    result = response.json()["result"]

    if "$$SOE" not in result:
        raise ValueError(
            "NASA returned no data: " + result[:300]
        )

    block = (
        result.split("$$SOE",1)[1]
        .split("$$EOE",1)[0]
    )

    rows = []

    for line in block.splitlines():
        p = [x.strip() for x in line.split(",")]

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

    return pd.DataFrame(rows)


def analyze(lat, lon, start, hours):
    text = start.strftime("%Y-%m-%d %H:%M")

    sun = get_horizons(
        "10", lat, lon, text, hours
    )

    earth = get_horizons(
        "399", lat, lon, text, hours
    )

    df = sun[
        ["time","elevation"]
    ].merge(
        earth[["time","elevation"]],
        on="time",
        suffixes=("_sun","_earth")
    ).sort_values("time")

    df = df.iloc[:-1].copy()

    if len(df) != hours:
        raise ValueError(
            "Incomplete hourly ephemeris."
        )

    df["Sun"] = df.elevation_sun > 0
    df["Earth"] = df.elevation_earth > 0
    df["Both"] = df.Sun & df.Earth

    return df


def metrics(df):
    return {
        "Sun": int(df.Sun.sum()),
        "Earth": int(df.Earth.sum()),
        "Both": int(df.Both.sum())
    }


def visibility_chart(df):
    fig = go.Figure()

    for name, column, color in [
        ("Sun","elevation_sun","#ffce73"),
        ("Earth","elevation_earth","#75c5ff")
    ]:
        fig.add_trace(go.Scatter(
            x=df.time,
            y=df[column],
            name=name,
            mode="lines",
            line=dict(
                color=color,
                width=3
            )
        ))

    fig.add_hline(
        y=0,
        line_dash="dash",
        line_color="#e77a88"
    )

    fig.update_layout(
        title="Sun and Earth above the horizon",
        template="plotly_dark",
        xaxis_title="Time (UTC)",
        yaxis_title="Elevation (degrees)",
        height=410,
        hovermode="x unified"
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )


# =====================================================
# NAVIGATION
# =====================================================

with st.sidebar:
    st.markdown("## أُفُق | OFOQ")
    st.caption("LUNAR MISSION CONTROL")

    section = st.radio(
        "Navigation",
        [
            "01 — Explore & Choose",
            "02 — Terrain Scanner",
            "03 — Lander Camera",
            "04 — Sun & Earth",
            "05 — Mission Plan B",
            "06 — Science & Sources"
        ]
    )

    st.divider()

    st.caption("YOUR SELECTED LOCATION")

    st.write(
        f"Latitude: **{st.session_state.lat:.5f}°**"
    )

    st.write(
        f"Longitude: **{st.session_state.lon:.5f}°**"
    )

    st.divider()

    selected_date = st.date_input(
        "Mission date (UTC)",
        value=date(2026,11,14)
    )

    hours = st.slider(
        "Mission duration (hours)",
        24,96,48,12
    )

# =====================================================
# SECTION 1: EXPLORATION AND SITE SELECTION
# =====================================================

if section == "01 — Explore & Choose":
    st.header("Explore the Moon")

    st.write(
        "Choose 2D to select a landing point "
        "by clicking directly on the map. "
        "Choose 3D to rotate and explore the Moon."
    )

    mode = st.radio(
        "View mode",
        ["2D Map — Select Point", "3D Moon — Explore"],
        horizontal=True
    )

    if mode.startswith("2D"):
        st.subheader("Click where you want to investigate")

        show_clickable_map()

        st.caption(
            "The map is restricted to the lunar "
            "south-pole region. Positions are "
            "investigation points, not approved "
            "landing locations."
        )

    else:
        try:
            show_3d_moon()
        except Exception as error:
            st.error(str(error))

        st.info(
            "The 3D globe is for visual exploration. "
            "Switch to 2D to click and save "
            "your exact investigation point."
        )

# =====================================================
# SECTION 2: REGIONAL TERRAIN SCANNER
# =====================================================

elif section == "02 — Terrain Scanner":
    st.header("Regional Terrain Scanner")

    st.write(
        "OFOQ automatically loads NASA LOLA "
        "global elevation data and examines "
        "the region around your selected point."
    )

    st.warning(
        "This is a REGIONAL elevation scan, "
        "not a certified landing-hazard scan. "
        "Small rocks, craters, and slopes may "
        "not be resolved by this DEM."
    )

    try:
        with st.spinner(
            "Loading NASA lunar elevation data..."
        ):
            axis, z, ppd = sample_lunar_terrain(
                st.session_state.lat,
                st.session_state.lon
            )

        st.success(
            f"NASA terrain data loaded: "
            f"{ppd} pixels per degree."
        )

        cells = create_scan_cells(z)

        show_scanner(cells)

        c1,c2,c3 = st.columns(3)

        c1.metric(
            "Minimum elevation",
            f"{np.nanmin(z):.0f} m"
        )

        c2.metric(
            "Maximum elevation",
            f"{np.nanmax(z):.0f} m"
        )

        c3.metric(
            "Regional relief",
            f"{np.nanmax(z)-np.nanmin(z):.0f} m"
        )

        st.info(
            "Blue shades describe relative "
            "elevation only. They are NOT "
            "landing-safety scores."
        )

        st.download_button(
            "Download measured regional grid",
            data=pd.DataFrame(
                cells
            ).to_csv(index=False),
            file_name="OFOQ_terrain.csv",
            mime="text/csv"
        )

    except Exception as error:
        st.error(
            "NASA elevation model unavailable."
        )
        st.code(str(error))

# =====================================================
# SECTION 3: LANDER CAMERA
# =====================================================

elif section == "03 — Lander Camera":
    st.header("Virtual Lander Camera")

    st.write(
        "This view looks across reconstructed "
        "lunar terrain, instead of showing "
        "another overhead map."
    )

    st.info(
        "The landscape is a visual simulation "
        "based on NASA elevations. "
        "It is NOT real lander camera footage. "
        "Terrain height is exaggerated."
    )

    try:
        with st.spinner(
            "Building virtual terrain..."
        ):
            axis, z, ppd = sample_lunar_terrain(
                st.session_state.lat,
                st.session_state.lon
            )

        show_lander_camera(z)

        st.caption(
            "Source: NASA LOLA global DEM. "
            "This model has regional-scale detail "
            "only; it cannot show individual "
            "small rocks or certify landing safety."
        )

    except Exception as error:
        st.error(
            "Virtual terrain could not load."
        )
        st.code(str(error))

# =====================================================
# SECTION 4: MISSION WINDOWS
# =====================================================

elif section == "04 — Sun & Earth":
    st.header("Can the lander see the Sun and Earth?")

    st.write(
        "The Sun affects lighting and possible "
        "solar power. Earth visibility affects "
        "whether direct communication may be possible."
    )

    if st.button(
        "Analyze NASA mission conditions",
        type="primary"
    ):
        start = datetime.combine(
            selected_date, time(0,0)
        )

        try:
            with st.spinner(
                "Reading NASA JPL Horizons..."
            ):
                df = analyze(
                    st.session_state.lat,
                    st.session_state.lon,
                    start,
                    hours
                )

            st.session_state.visibility_result = (
                df,
                (
                    st.session_state.lat,
                    st.session_state.lon,
                    selected_date,
                    hours
                )
            )

        except Exception as error:
            st.error(str(error))

    result = st.session_state.visibility_result

    current = (
        st.session_state.lat,
        st.session_state.lon,
        selected_date,
        hours
    )

    if result is not None and result[1] == current:
        df = result[0]
        values = metrics(df)

        a,b,c = st.columns(3)

        a.metric(
            "Sun above horizon",
            f"{values['Sun']} h"
        )

        b.metric(
            "Earth above horizon",
            f"{values['Earth']} h"
        )

        c.metric(
            "Both at once",
            f"{values['Both']} h"
        )

        visibility_chart(df)

        if values["Both"] == 0:
            st.warning(
                "No simultaneous visibility was "
                "found during the sampled hours."
            )
        else:
            st.success(
                "This site has approximately "
                f"{values['Both']} sampled hours "
                "when both objects are above "
                "the geometric horizon."
            )

        st.caption(
            "Hourly estimates, using a geometric "
            "horizon. Terrain blocking and actual "
            "radio-link performance are not modeled."
        )

    else:
        st.info(
            "Select a point on the map, "
            "then press Analyze."
        )

# =====================================================
# SECTION 5: PLAN B
# =====================================================

elif section == "05 — Mission Plan B":
    st.header("What if the mission plan changes?")

    comparison = st.radio(
        "Compare",
        [
            "Same location, different date",
            "Different location, same date"
        ]
    )

    start = datetime.combine(
        selected_date,time(0,0)
    )

    lat_b = st.session_state.lat
    lon_b = st.session_state.lon
    start_b = start

    if comparison.startswith("Same"):
        delay = st.slider(
            "Mission delay (hours)",
            0,168,48,12
        )

        start_b = (
            start + timedelta(hours=delay)
        )

    else:
        lat_b = st.number_input(
            "Alternative latitude",
            -90.0,-75.0,-85.0
        )

        lon_b = st.number_input(
            "Alternative longitude",
            -180.0,180.0,0.0
        )

    if st.button(
        "Compare both mission plans",
        type="primary"
    ):
        try:
            with st.spinner(
                "Comparing NASA mission data..."
            ):
                first = analyze(
                    st.session_state.lat,
                    st.session_state.lon,
                    start,hours
                )

                second = analyze(
                    lat_b,lon_b,
                    start_b,hours
                )

            a = metrics(first)
            b = metrics(second)

            left,right = st.columns(2)

            with left:
                st.subheader("Original mission")
                for name,value in a.items():
                    st.metric(
                        name,f"{value} hours"
                    )

            with right:
                st.subheader("Alternative")
                for name,value in b.items():
                    st.metric(
                        name,
                        f"{value} hours",
                        delta=b[name]-a[name]
                    )

            chart = go.Figure()

            chart.add_trace(go.Bar(
                name="Original",
                x=list(a.keys()),
                y=list(a.values())
            ))

            chart.add_trace(go.Bar(
                name="Alternative",
                x=list(b.keys()),
                y=list(b.values())
            ))

            chart.update_layout(
                template="plotly_dark",
                barmode="group",
                title="Visibility comparison",
                yaxis_title="Sampled hours"
            )

            st.plotly_chart(
                chart,use_container_width=True
            )

            st.caption(
                "Only one factor changes "
                "at a time: location or date."
            )

        except Exception as error:
            st.error(str(error))

# =====================================================
# SECTION 6: SCIENCE AND TRANSPARENCY
# =====================================================

else:
    st.header("Science Behind OFOQ")

    st.markdown("""
### What is real?

**Moon imagery:** NASA LRO / Moon Trek.

**Regional terrain heights:** NASA LOLA global DEM.

**Sun and Earth positions:** NASA JPL Horizons.

### What is simulated?

The 3D globe and the lander camera are
visualizations. They are not live spacecraft video.

### What is not established yet?

The scanner cannot certify a landing site as safe.

A proper landing hazard assessment needs
much finer terrain data, boulder detection,
spacecraft dimensions, slope limits, and
mission-specific engineering criteria.

### Official resources

- [NASA Moon Trek](https://trek.nasa.gov/moon/)
- [NASA Horizons](https://ssd.jpl.nasa.gov/horizons/)
- [NASA CGI Moon Kit](https://svs.gsfc.nasa.gov/4720/)
- [NASA Polar LOLA Data](https://pgda.gsfc.nasa.gov/products/78/)
    """)

st.divider()

st.caption(
    "OFOQ | NASA Space Apps Challenge 2026 "
    "— Independent educational and mission "
    "exploration prototype. Not NASA-certified."
)
