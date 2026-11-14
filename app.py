import streamlit as st
import streamlit.components.v1 as components

import requests
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import rasterio
import tifffile

from PIL import Image, ImageDraw
from io import BytesIO
from datetime import datetime, date, timedelta
from pyproj import CRS, Transformer
from rasterio.windows import Window
from rasterio.enums import Resampling
from streamlit_image_coordinates import streamlit_image_coordinates

import base64
import json


# ==================================================
# OFOQ V5 | LUNAR MISSION EXPERIENCE
# ==================================================

st.set_page_config(
    page_title="OFOQ | أُفُق",
    page_icon="🌙",
    layout="wide",
    initial_sidebar_state="collapsed"
)

NASA_TEXTURE = (
    "https://svs.gsfc.nasa.gov/vis/a000000/"
    "a004700/a004720/lroc_color_2k.jpg"
)

NASA_GLOBAL_DEM = (
    "https://svs.gsfc.nasa.gov/vis/a000000/"
    "a004700/a004720/ldem_4.tif"
)

NASA_POLAR_DEM = (
    "https://pgda.gsfc.nasa.gov/data/"
    "LOLA_20mpp/LDEM_80S_80MPP_ADJ.TIF"
)

NASA_POLAR_SLOPE = (
    "https://pgda.gsfc.nasa.gov/data/"
    "LOLA_20mpp/LDSM_80S_80MPP_ADJ.TIF"
)

HORIZONS = "https://ssd.jpl.nasa.gov/api/horizons.api"

MOON_RADIUS = 1737400.0

MOON_GEO = CRS.from_proj4(
    "+proj=longlat +a=1737400 +b=1737400 "
    "+no_defs"
)


# ==================================================
# STATE
# ==================================================

defaults = {
    "language": "العربية",
    "page": "explore",
    "lat": -89.0,
    "lon": 0.0,
    "last_click": None,
    "last_visibility": None
}

for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ==================================================
# TRANSLATION
# ==================================================

TEXT = {
    "tagline": (
        "ما وراء الأفق، نحو القمر",
        "Beyond the horizon, toward the Moon"
    ),
    "description": (
        "استكشف القمر، واختر موقعًا، وافهم ظروف الهبوط "
        "باستخدام بيانات علمية من NASA.",
        "Explore the Moon, select a location and "
        "understand mission conditions using NASA data."
    ),
    "explore": (
        "استكشف واختر",
        "Explore & Select"
    ),
    "surface": (
        "كاميرا المركبة والمسح",
        "Lander Camera & Scan"
    ),
    "visibility": (
        "الشمس والأرض",
        "Sun & Earth"
    ),
    "compare": (
        "المقارنة والخطة البديلة",
        "Compare & Plan B"
    ),
    "view": (
        "طريقة العرض",
        "View mode"
    ),
    "twoD": (
        "خريطة القمر 2D",
        "2D Moon Map"
    ),
    "threeD": (
        "القمر ثلاثي الأبعاد 3D",
        "3D Moon"
    ),
    "click": (
        "اضغط على المكان الذي تريد دراسته",
        "Click the place you want to investigate"
    ),
    "zoom": (
        "مستوى التكبير",
        "Zoom level"
    ),
    "selected": (
        "الموقع الذي اخترته",
        "Your selected location"
    ),
    "latitude": (
        "خط العرض",
        "Latitude"
    ),
    "longitude": (
        "خط الطول",
        "Longitude"
    ),
    "south_warning": (
        "هذا الموقع خارج نطاق تحليل التضاريس القطبية الحالي. "
        "اختر موقعًا جنوب خط عرض 80° جنوبًا.",
        "This point is outside the current polar "
        "terrain-analysis region. Choose a point "
        "south of 80°S."
    ),
    "map_note": (
        "اضغط مباشرة على الصورة لتغيير الموقع. "
        "يمكنك التكبير دون الخروج من حدود الخريطة.",
        "Click directly on the image to change the site. "
        "Zooming stays inside the map boundaries."
    ),
    "surface_title": (
        "انظر إلى السطح من منظور المركبة",
        "Explore the surface from a lander's viewpoint"
    ),
    "surface_description": (
        "شاهد نموذجًا افتراضيًا للتضاريس، ثم افحص "
        "المربعات التي تغطي منطقة الدراسة.",
        "Explore a virtual terrain view and inspect "
        "the cells covering the selected area."
    ),
    "scan_button": (
        "ابدأ مسح التضاريس",
        "Start Terrain Scan"
    ),
    "scan_unavailable": (
        "تعذر تحميل بيانات الانحدار التفصيلية من NASA. "
        "ستبقى نتائج الخلايا غير محددة.",
        "Detailed NASA slope data could not be loaded. "
        "Cell assessments remain unavailable."
    ),
    "scan_loaded": (
        "تم استخراج بيانات انحدار حقيقية من NASA.",
        "Real NASA slope measurements were retrieved."
    ),
    "scan_limit": (
        "هذا مسح أولي للانحدار، وليس تصريحًا بأن "
        "المركبة تستطيع الهبوط بأمان.",
        "This is preliminary slope screening, "
        "not certification of landing safety."
    ),
    "camera_note": (
        "هذا منظور افتراضي مبني على بيانات ارتفاعات القمر، "
        "وليس بثًا مباشرًا من مركبة فضائية.",
        "This is a virtual view based on lunar elevation "
        "data, not live spacecraft footage."
    ),
    "mission_date": (
        "تاريخ المهمة بتوقيت UTC",
        "Mission date (UTC)"
    ),
    "duration": (
        "مدة المهمة بالساعات",
        "Mission duration (hours)"
    ),
    "calculate": (
        "احسب ظروف المهمة",
        "Calculate Mission Conditions"
    ),
    "sun": (
        "ساعات ظهور الشمس",
        "Sun visibility hours"
    ),
    "earth": (
        "ساعات ظهور الأرض",
        "Earth visibility hours"
    ),
    "both": (
        "ساعات ظهور الشمس والأرض معًا",
        "Simultaneous visibility hours"
    ),
    "horizon": (
        "ارتفاع الشمس والأرض بالنسبة للأفق",
        "Sun and Earth elevation above the horizon"
    ),
    "no_earth": (
        "قد لا يتمكن الموقع من رؤية الأرض مباشرة "
        "خلال الفترة المختارة.",
        "The location may not have direct visibility "
        "of Earth during the selected period."
    ),
    "visibility_note": (
        "النتائج تقريبية لكل ساعة، ولا تحسب حجب الجبال "
        "أو جودة الاتصال اللاسلكي.",
        "Hourly estimates exclude terrain obstruction "
        "and radio-link performance."
    ),
    "compare_title": (
        "ماذا يحدث إذا تغيرت خطة الهبوط؟",
        "What if the landing plan changes?"
    ),
    "same_site": (
        "نفس الموقع، موعد مختلف",
        "Same site, different date"
    ),
    "other_site": (
        "موقع مختلف، نفس الموعد",
        "Different site, same date"
    ),
    "delay": (
        "التأخير بالساعات",
        "Delay in hours"
    ),
    "compare_button": (
        "قارن الخطتين",
        "Compare Mission Plans"
    ),
    "original": (
        "الخطة الأصلية",
        "Original plan"
    ),
    "alternative": (
        "الخطة البديلة",
        "Alternative plan"
    ),
    "science": (
        "المصادر والحدود العلمية",
        "Sources & Scientific Limitations"
    ),
    "error": (
        "تعذر الحصول على البيانات",
        "Could not retrieve the data"
    ),
}


def tr(key):
    pair = TEXT.get(key, (key, key))
    return pair[0] if st.session_state.language == "العربية" else pair[1]


def is_ar():
    return st.session_state.language == "العربية"


# ==================================================
# VISUAL DESIGN
# ==================================================

st.markdown("""
<style>
:root {
  --space: #050B16;
  --night: #0C1B2F;
  --blue: #76C5F5;
  --silver: #DCECF7;
}

html, body, .stApp {
  background: #050B16 !important;
  color: #E6F3FF;
}

.stApp {
  background:
    radial-gradient(
      ellipse at 83% 8%,
      rgba(49, 108, 154, .25),
      transparent 39%
    ),
    radial-gradient(
      ellipse at 8% 80%,
      rgba(20, 58, 98, .19),
      transparent 40%
    ),
    #050B16 !important;
}

[data-testid="stHeader"] {
  background: transparent !important;
}

[data-testid="stSidebar"] {
  display: none;
}

.block-container {
  max-width: 1440px;
  padding-top: 1.2rem;
  padding-bottom: 4rem;
}

h1, h2, h3, p, label {
  color: #EDF7FF !important;
}

h1 {
  letter-spacing: .02em;
}

[data-testid="stMetric"] {
  background: linear-gradient(
    145deg, #122A44, #0B1B30
  );
  padding: 19px 20px;
  border: 1px solid #385775;
  border-radius: 16px;
}

[data-testid="stMetricValue"] {
  color: #DFF5FF;
}

[data-testid="stMetricLabel"] {
  color: #A9D7F1;
}

.stButton button[kind="primary"],
.stDownloadButton button {
  background: #76C5F5 !important;
  color: #071323 !important;
  border-radius: 12px !important;
  border: 0 !important;
  font-weight: 750 !important;
}

.stButton button {
  border-radius: 12px !important;
  border: 1px solid #365875;
}

[data-testid="stSegmentedControl"] {
  border-radius: 13px;
}

[data-testid="stAlert"] {
  border-radius: 12px;
}

.ofoq-hero {
  position: relative;
  overflow: hidden;
  min-height: 225px;
  padding: 31px 38px;
  border-radius: 24px;
  border: 1px solid rgba(139, 204, 244, .34);
  background:
    radial-gradient(
      circle at 82% 48%,
      rgba(121, 200, 253, .22),
      transparent 19%
    ),
    radial-gradient(
      1px 1px at 15% 22%, white, transparent
    ),
    radial-gradient(
      2px 2px at 75% 18%, #A5D8FF, transparent
    ),
    radial-gradient(
      1px 1px at 54% 72%, white, transparent
    ),
    linear-gradient(110deg, #091523, #163450);
  box-shadow: 0 24px 70px #00000054;
  margin-bottom: 20px;
}

.ofoq-hero:after {
  content: "";
  position: absolute;
  width: 300px;
  height: 300px;
  border: 2px solid rgba(110, 200, 255, .45);
  border-radius: 50%;
  top: -150px;
  right: 65px;
  box-shadow: 0 0 44px rgba(110, 200, 255, .15);
}

.ofoq-small {
  color: #8ED5FC;
  letter-spacing: .20em;
  font-size: 11px;
  font-weight: 750;
}

.ofoq-logo {
  font-size: clamp(38px, 5vw, 68px);
  color: #E5F2FD;
  font-weight: 850;
  letter-spacing: .07em;
  text-shadow: 0 0 28px #76C5F53F;
  margin: 6px 0;
}

.ofoq-desc {
  color: #CAE0F0;
  font-size: 16px;
  max-width: 760px;
  line-height: 1.8;
}

.ofoq-card {
  background: #0B2034;
  border: 1px solid #31516B;
  border-radius: 18px;
  padding: 17px 20px;
  margin: 9px 0 16px;
}

.ofoq-chip {
  display: inline-block;
  color: #95DBFF;
  border: 1px solid #477A9C;
  border-radius: 100px;
  padding: 7px 12px;
  font-size: 12px;
}

hr {
  border-color: #27445E !important;
}
</style>
""", unsafe_allow_html=True)


# ==================================================
# LANGUAGE AND NAVIGATION
# ==================================================

top_left, top_right = st.columns([5, 1])

with top_right:
    st.segmented_control(
        "Language",
        ["العربية", "English"],
        key="language",
        default="العربية",
        label_visibility="collapsed"
    )

direction = "rtl" if is_ar() else "ltr"

st.markdown(
    f"""
    <div class="ofoq-hero" dir="{direction}">
       <div class="ofoq-small">
         NASA SPACE APPS CHALLENGE 2026
       </div>
       <div class="ofoq-logo">أُفُق | OFOQ</div>
       <div class="ofoq-small">{tr("tagline")}</div>
       <p class="ofoq-desc">
           {tr("description")}
       </p>
       <span class="ofoq-chip">
           LUNAR MISSION INTELLIGENCE
       </span>
    </div>
    """,
    unsafe_allow_html=True
)

PAGES = ["explore", "surface", "visibility", "compare"]

page = st.segmented_control(
    "Navigation",
    PAGES,
    format_func=tr,
    key="page",
    default="explore",
    label_visibility="collapsed"
)

if page is None:
    page = "explore"


# ==================================================
# REAL NASA MOON IMAGE
# ==================================================

@st.cache_data(ttl=86400, show_spinner=False)
def get_texture_bytes():
    r = requests.get(NASA_TEXTURE, timeout=35)
    r.raise_for_status()
    return r.content


@st.cache_data(ttl=86400, show_spinner=False)
def get_texture_image():
    return Image.open(
        BytesIO(get_texture_bytes())
    ).convert("RGB")


def selected_position_card():
    a, b = st.columns(2)

    a.metric(
        tr("latitude"),
        f"{st.session_state.lat:.5f}°"
    )

    b.metric(
        tr("longitude"),
        f"{st.session_state.lon:.5f}°"
    )


def moon_2d():
    st.subheader(tr("click"))

    zoom = st.slider(
        tr("zoom"),
        min_value=1,
        max_value=6,
        value=1
    )

    source = get_texture_image()
    W, H = source.size

    crop_w = W / zoom
    crop_h = H / zoom

    center_x = (
        st.session_state.lon + 180
    ) / 360 * W

    center_y = (
        90 - st.session_state.lat
    ) / 180 * H

    if zoom == 1:
        left, top = 0, 0
        right, bottom = W, H
    else:
        left = max(
            0, min(W - crop_w, center_x - crop_w / 2)
        )
        top = max(
            0, min(H - crop_h, center_y - crop_h / 2)
        )
        right = left + crop_w
        bottom = top + crop_h

    image = source.crop(
        (
            int(left),
            int(top),
            int(right),
            int(bottom)
        )
    ).resize(
        (1024, 512),
        Image.Resampling.LANCZOS
    )

    draw = ImageDraw.Draw(image)

    px = (
        center_x - left
    ) / (right - left) * 1024

    py = (
        center_y - top
    ) / (bottom - top) * 512

    if 0 <= px < 1024 and 0 <= py < 512:
        draw.ellipse(
            (px - 9, py - 9, px + 9, py + 9),
            outline="#76C5F5",
            width=4
        )
        draw.ellipse(
            (px - 3, py - 3, px + 3, py + 3),
            fill="#FFFFFF"
        )

    click = streamlit_image_coordinates(
        image,
        width=1024,
        key=f"ofoq_click_{zoom}"
    )

    if click is not None:
        signature = (
            click.get("unix_time"),
            click.get("x"),
            click.get("y"),
            zoom
        )

        if signature != st.session_state.last_click:
            st.session_state.last_click = signature

            x = max(0, min(1023, click["x"]))
            y = max(0, min(511, click["y"]))

            true_x = left + x / 1024 * (right - left)
            true_y = top + y / 512 * (bottom - top)

            lon = true_x / W * 360 - 180
            lat = 90 - true_y / H * 180

            st.session_state.lat = round(
                float(lat), 5
            )
            st.session_state.lon = round(
                float(lon), 5
            )

            st.rerun()

    st.caption(tr("map_note"))
    selected_position_card()


# ==================================================
# 3D MOON GLOBE
# ==================================================

def moon_3d():
    texture = (
        "data:image/jpeg;base64,"
        + base64.b64encode(
            get_texture_bytes()
        ).decode("ascii")
    )

    page_html = """
    <html>
    <head>
    <style>
      body {
        margin:0;
        overflow:hidden;
        background:#060D19;
      }
      #scene {width:100%;height:530px;}
      .hud {
        position:absolute;
        bottom:15px;
        left:15px;
        color:#D9F3FF;
        background:#10273CCC;
        border:1px solid #477A9C;
        border-radius:10px;
        padding:12px;
        font:13px Arial;
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
    <div class="hud">
       DRAG TO ROTATE · SCROLL TO ZOOM
    </div>
    <script type="module">
    import * as THREE from "three";
    import { OrbitControls } from
      "three/addons/controls/OrbitControls.js";

    const el = document.getElementById("scene");
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x060d19);

    const camera = new THREE.PerspectiveCamera(
      43,1,.1,100
    );
    camera.position.set(0,0,5);

    const renderer = new THREE.WebGLRenderer({
      antialias:true
    });
    renderer.setPixelRatio(
      Math.min(window.devicePixelRatio,2)
    );
    el.appendChild(renderer.domElement);

    const texture = new THREE.TextureLoader().load(
      __TEXTURE__
    );

    texture.colorSpace = THREE.SRGBColorSpace;

    const globe = new THREE.Mesh(
      new THREE.SphereGeometry(1.7,96,64),
      new THREE.MeshStandardMaterial({
        map:texture,roughness:1
      })
    );

    scene.add(globe);
    scene.add(new THREE.AmbientLight(0xffffff,1.3));

    const light = new THREE.DirectionalLight(
      0xffffff,2
    );
    light.position.set(5,3,6);
    scene.add(light);

    const controls = new OrbitControls(
      camera,renderer.domElement
    );
    controls.enableDamping=true;
    controls.enablePan=false;
    controls.minDistance=2.2;
    controls.maxDistance=8;

    function resize(){
      const w=el.clientWidth || 800;
      renderer.setSize(w,530);
      camera.aspect=w/530;
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

    components.html(
        page_html.replace(
            "__TEXTURE__",
            json.dumps(texture)
        ),
        height=535,
        scrolling=False
    )


# ==================================================
# REAL NASA TERRAIN
# ==================================================

def read_remote_cog(url, lat, lon, size=96):
    """
    Read only a small window from NASA polar COG.
    Never download the entire large GeoTIFF.
    """

    with rasterio.Env(
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        GDAL_HTTP_TIMEOUT="15",
        GDAL_HTTP_MAX_RETRY="1"
    ):
        with rasterio.open(
            "/vsicurl/" + url
        ) as src:

            if src.crs is None:
                raise ValueError(
                    "NASA raster has no CRS"
                )

            transformer = Transformer.from_crs(
                MOON_GEO,
                src.crs,
                always_xy=True
            )

            x, y = transformer.transform(lon, lat)

            row, col = src.index(x, y)

            half = size // 2

            if (
                row - half < 0
                or col - half < 0
                or row + half >= src.height
                or col + half >= src.width
            ):
                raise ValueError(
                    "Point outside raster coverage"
                )

            window = Window(
                col - half,
                row - half,
                size,
                size
            )

            a = src.read(
                1,
                window=window,
                out_shape=(65, 65),
                resampling=Resampling.bilinear,
                masked=True
            )

            data = np.ma.array(
                a.astype(float)
            ).filled(np.nan)

            if np.isinf(data).any():
                data[~np.isfinite(data)] = np.nan

            pixel_m = max(
                abs(src.transform.a),
                abs(src.transform.e)
            )

            return data, pixel_m


@st.cache_data(ttl=3600, show_spinner=False)
def get_polar_scan(lat, lon):
    dem, resolution = read_remote_cog(
        NASA_POLAR_DEM, lat, lon
    )

    slope, _ = read_remote_cog(
        NASA_POLAR_SLOPE, lat, lon
    )

    return dem, slope, resolution


@st.cache_data(ttl=86400, show_spinner=False)
def get_global_dem():
    r = requests.get(
        NASA_GLOBAL_DEM,
        timeout=45
    )
    r.raise_for_status()

    return tifffile.imread(
        BytesIO(r.content)
    ).astype(float) * 1000.0


def coarse_virtual_terrain(lat, lon):
    """
    Global NASA DEM for regional illustration only.
    It is too coarse for landing safety screening.
    """

    source = get_global_dem()
    H, W = source.shape

    stere = CRS.from_proj4(
        "+proj=stere +lat_0=-90 +lat_ts=-90 "
        "+lon_0=0 +a=1737400 +b=1737400 "
        "+units=m +no_defs"
    )

    fwd = Transformer.from_crs(
        MOON_GEO, stere, always_xy=True
    )

    inv = Transformer.from_crs(
        stere, MOON_GEO, always_xy=True
    )

    cx, cy = fwd.transform(lon, lat)

    axis = np.linspace(-25000, 25000, 65)

    xx, yy = np.meshgrid(
        cx + axis,
        cy + axis
    )

    glon, glat = inv.transform(xx, yy)

    col = np.clip(
        np.round(
            (glon + 180) / 360 * (W - 1)
        ).astype(int),
        0, W - 1
    )

    row = np.clip(
        np.round(
            (90 - glat) / 180 * (H - 1)
        ).astype(int),
        0, H - 1
    )

    return source[row, col]


def make_cells(slope):
    cells = []

    for r in range(8):
        for c in range(8):
            block = slope[
                r * 8:(r + 1) * 8,
                c * 8:(c + 1) * 8
            ]

            valid = block[np.isfinite(block)]
            coverage = len(valid) / block.size

            cell = {
                "id": f"{r + 1}-{c + 1}",
                "value": None,
                "status": "unknown",
                "coverage": round(
                    coverage * 100, 1
                )
            }

            if coverage >= 0.75:
                # 90th percentile highlights
                # steeper portions of the cell.
                p90 = float(
                    np.percentile(valid, 90)
                )

                cell["value"] = round(p90, 2)

                if p90 <= 5:
                    cell["status"] = "gentle"
                elif p90 <= 12:
                    cell["status"] = "review"
                else:
                    cell["status"] = "steep"

            cells.append(cell)

    return cells


def render_lander_scene(dem, cells, source_label):
    values = np.asarray(dem, dtype=float)

    if not np.isfinite(values).any():
        raise ValueError("No valid DEM elevations")

    median = np.nanmedian(values)

    values = np.nan_to_num(
        values,
        nan=median
    )

    # Visual vertical exaggeration.
    relative = np.clip(
        (values - median) / 300.0,
        -2.2,
        2.2
    )

    data = relative.tolist()

    scene_html = """
    <html>
    <head>
    <style>
      * {box-sizing:border-box;}
      body{
        margin:0;
        background:#040B15;
        font-family:Arial,sans-serif;
        overflow:hidden;
        color:#DDF5FF;
      }
      #stage{height:560px;width:100%;}
      .hud{
        position:absolute;
        top:16px;left:16px;
        border:1px solid #76C5F577;
        background:#0B1D32D9;
        padding:13px 17px;
        border-radius:12px;
        font-size:12px;
        letter-spacing:1px;
        z-index:9;
      }
      .beam{
        position:absolute;
        pointer-events:none;
        left:0;right:0;
        top:0;height:2px;
        background:#9DE5FF;
        box-shadow:0 0 25px #76C5F5;
        animation:scan 5s linear infinite;
        z-index:5;
        opacity:.55;
      }
      @keyframes scan{
        from{top:0%}
        to{top:100%}
      }
      .cross{
        position:absolute;
        left:50%;top:50%;
        width:26px;height:26px;
        transform:translate(-50%,-50%);
        border:1px solid #9EDFFF;
        border-radius:50%;
        pointer-events:none;
      }
      .bottom{
        position:absolute;
        left:16px;bottom:15px;
        max-width:370px;
        background:#081B30E8;
        border:1px solid #3B698B;
        border-radius:12px;
        padding:14px 17px;
        font-size:13px;
        line-height:1.6;
      }
      #detail{
        color:#E6F7FF;
      }
      #detail small{
        color:#9ECBE7;
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
      <div id="stage"></div>
      <div class="beam"></div>
      <div class="cross"></div>
      <div class="hud">
        OFOQ / LUNAR TERRAIN RECON<br>
        VIRTUAL LANDER PERSPECTIVE
      </div>
      <div class="bottom" id="detail">
        Click a terrain cell to inspect it.<br>
        <small>__SOURCE__</small>
      </div>

      <script type="module">
      import * as THREE from "three";
      import {OrbitControls} from
        "three/addons/controls/OrbitControls.js";

      const heights=__HEIGHTS__;
      const cells=__CELLS__;
      const n=heights.length;

      const host=document.getElementById("stage");
      const detail=document.getElementById("detail");

      const scene=new THREE.Scene();
      scene.background=new THREE.Color(0x081322);

      const camera=new THREE.PerspectiveCamera(
        65,1,.1,100
      );
      camera.position.set(0,3.5,12);

      const renderer=new THREE.WebGLRenderer({
        antialias:true
      });
      renderer.setPixelRatio(
        Math.min(window.devicePixelRatio,2)
      );
      host.appendChild(renderer.domElement);

      const terrainGeometry=new THREE.PlaneGeometry(
        16,16,n-1,n-1
      );

      const positions=terrainGeometry.attributes.position;

      for(let y=0;y<n;y++){
        for(let x=0;x<n;x++){
          const index=y*n+x;
          positions.setZ(index,heights[y][x]);
        }
      }

      terrainGeometry.computeVertexNormals();

      const surface=new THREE.Mesh(
        terrainGeometry,
        new THREE.MeshStandardMaterial({
          color:0x929BA8,
          roughness:1,
          side:THREE.DoubleSide,
          flatShading:false
        })
      );

      const group=new THREE.Group();
      group.add(surface);

      // 8 x 8 clickable scan cells
      const squares=[];
      const size=2;

      cells.forEach((cell,index)=>{
        const row=Math.floor(index/8);
        const col=index%8;

        const x0=-8+col*size;
        const y0=8-row*size;

        const sample=(r,c)=>{
          r=Math.min(64,Math.max(0,r));
          c=Math.min(64,Math.max(0,c));
          return heights[r][c]+0.045;
        };

        const r0=row*8;
        const c0=col*8;

        const vertices=new Float32Array([
          x0,      y0,      sample(r0,c0),
          x0+size, y0,      sample(r0,c0+8),
          x0,      y0-size, sample(r0+8,c0),

          x0+size, y0,      sample(r0,c0+8),
          x0+size, y0-size, sample(r0+8,c0+8),
          x0,      y0-size, sample(r0+8,c0)
        ]);

        const geometry=new THREE.BufferGeometry();

        geometry.setAttribute(
          "position",
          new THREE.BufferAttribute(vertices,3)
        );
        geometry.computeVertexNormals();

        let color=0x93A2B3;

        if(cell.status==="gentle")
          color=0x5CBEED;
        if(cell.status==="review")
          color=0xD8B770;
        if(cell.status==="steep")
          color=0x64758C;

        const tile=new THREE.Mesh(
          geometry,
          new THREE.MeshBasicMaterial({
            color:color,
            transparent:true,
            opacity:.25,
            side:THREE.DoubleSide,
            depthWrite:false
          })
        );

        tile.userData=cell;
        group.add(tile);
        squares.push(tile);

        const wire=new THREE.LineSegments(
          new THREE.EdgesGeometry(geometry),
          new THREE.LineBasicMaterial({
            color:0xA8E5FF,
            transparent:true,
            opacity:.62
          })
        );

        group.add(wire);
      });

      group.rotation.x=-Math.PI/2;
      scene.add(group);

      scene.add(
        new THREE.AmbientLight(0xBFD8F5,1.4)
      );

      const sunlight=new THREE.DirectionalLight(
        0xF2F5FF,3.1
      );
      sunlight.position.set(-5,8,5);
      scene.add(sunlight);

      const controls=new OrbitControls(
        camera,renderer.domElement
      );

      controls.enableDamping=true;
      controls.enablePan=false;
      controls.minDistance=2.5;
      controls.maxDistance=19;
      controls.target.set(0,0,0);

      const raycaster=new THREE.Raycaster();
      const mouse=new THREE.Vector2();

      renderer.domElement.addEventListener(
        "pointerdown",event=>{
          const rect=
            renderer.domElement.getBoundingClientRect();

          mouse.x=(
            (event.clientX-rect.left)/rect.width
          )*2-1;

          mouse.y=-(
            (event.clientY-rect.top)/rect.height
          )*2+1;

          raycaster.setFromCamera(mouse,camera);

          const hits=raycaster.intersectObjects(
            squares,false
          );

          if(hits.length){
            const c=hits[0].object.userData;

            const measured=c.value===null
              ? "Not available"
              : c.value+"°";

            detail.innerHTML=
              "<b>GRID CELL "+c.id+"</b><br>"+
              "Slope (90th percentile): "+measured+
              "<br>Coverage: "+c.coverage+"%"+
              "<br><small>Screening: "+
              c.status+
              " — not a safe-landing verdict</small>";
          }
        }
      );

      function resize(){
        const w=host.clientWidth||850;
        renderer.setSize(w,560);
        camera.aspect=w/560;
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

    scene_html = (
        scene_html
        .replace("__HEIGHTS__", json.dumps(data))
        .replace("__CELLS__", json.dumps(cells))
        .replace("__SOURCE__", source_label)
    )

    components.html(
        scene_html,
        height=565,
        scrolling=False
    )


# ==================================================
# NASA HORIZONS
# ==================================================

@st.cache_data(ttl=3600, show_spinner=False)
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

    r = requests.get(
        HORIZONS,
        params=params,
        timeout=60
    )
    r.raise_for_status()

    text = r.json()["result"]

    if "$$SOE" not in text or "$$EOE" not in text:
        raise ValueError(
            text[:350]
        )

    block = (
        text.split("$$SOE", 1)[1]
        .split("$$EOE", 1)[0]
    )

    rows = []

    for line in block.splitlines():
        p = [
            item.strip()
            for item in line.split(",")
        ]

        if len(p) < 5:
            continue

        try:
            rows.append({
                "time": pd.to_datetime(
                    p[0],
                    format="%Y-%b-%d %H:%M"
                ),
                "az": float(p[3]),
                "el": float(p[4])
            })
        except ValueError:
            continue

    if not rows:
        raise ValueError(
            "No numeric records received"
        )

    return pd.DataFrame(rows)


def mission_data(lat, lon, start, hours):
    text = start.strftime("%Y-%m-%d %H:%M")

    sun = get_horizons(
        "10", lat, lon, text, hours
    )

    earth = get_horizons(
        "399", lat, lon, text, hours
    )

    df = sun[["time", "el"]].merge(
        earth[["time", "el"]],
        on="time",
        suffixes=("_sun", "_earth")
    ).sort_values("time")

    df = df.iloc[:-1].copy()

    if len(df) != hours:
        raise ValueError(
            "Incomplete hourly NASA data"
        )

    df["Sun"] = df.el_sun > 0
    df["Earth"] = df.el_earth > 0
    df["Both"] = df.Sun & df.Earth

    return df


def mission_numbers(df):
    return {
        "Sun": int(df.Sun.sum()),
        "Earth": int(df.Earth.sum()),
        "Both": int(df.Both.sum())
    }


def draw_visibility(df):
    numbers = mission_numbers(df)

    a, b, c = st.columns(3)

    a.metric(
        tr("sun"),
        f"{numbers['Sun']} h"
    )

    b.metric(
        tr("earth"),
        f"{numbers['Earth']} h"
    )

    c.metric(
        tr("both"),
        f"{numbers['Both']} h"
    )

    if numbers["Earth"] == 0:
        st.info(tr("no_earth"))

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df.time,
        y=df.el_sun,
        name="Sun",
        line=dict(
            color="#F1CE8C",
            width=3
        )
    ))

    fig.add_trace(go.Scatter(
        x=df.time,
        y=df.el_earth,
        name="Earth",
        line=dict(
            color="#76C5F5",
            width=3
        )
    ))

    fig.add_hline(
        y=0,
        line_dash="dash",
        line_color="#C8D4E4"
    )

    fig.update_layout(
        title=tr("horizon"),
        template="plotly_dark",
        paper_bgcolor="#091625",
        plot_bgcolor="#091625",
        font=dict(color="#DCECF7"),
        xaxis_title="UTC",
        yaxis_title=(
            "الارتفاع بالدرجات"
            if is_ar()
            else "Elevation (degrees)"
        ),
        hovermode="x unified",
        height=400
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )

    st.caption(tr("visibility_note"))


# ==================================================
# PAGE: EXPLORE
# ==================================================

if page == "explore":
    st.header(tr("explore"))

    view = st.segmented_control(
        tr("view"),
        ["2D", "3D"],
        default="2D",
        key="view_mode"
    )

    if view == "3D":
        try:
            moon_3d()
        except Exception as error:
            st.error(str(error))

        st.info(
            "للاختيار الدقيق اضغط على وضع 2D."
            if is_ar()
            else "Use 2D mode to select a precise location."
        )

    else:
        try:
            moon_2d()
        except Exception as error:
            st.error(
                tr("error") + ": " + str(error)
            )


# ==================================================
# PAGE: LANDER CAMERA + SCAN
# ==================================================

elif page == "surface":
    st.header(tr("surface_title"))

    st.write(tr("surface_description"))
    selected_position_card()

    if st.session_state.lat > -80:
        st.warning(tr("south_warning"))

    if st.button(
        tr("scan_button"),
        type="primary"
    ):
        st.session_state[
            "scan_requested"
        ] = (
            st.session_state.lat,
            st.session_state.lon
        )

    requested = st.session_state.get(
        "scan_requested"
    )

    current = (
        st.session_state.lat,
        st.session_state.lon
    )

    if requested == current:
        dem = None
        cells = None
        high_resolution = False
        source_label = "NASA LOLA"

        if st.session_state.lat <= -80:
            try:
                with st.spinner(
                    "NASA LOLA / Terrain Data"
                ):
                    dem, slope, pixel = get_polar_scan(
                        *current
                    )

                cells = make_cells(slope)
                high_resolution = True

                source_label = (
                    f"NASA LOLA COG | {pixel:.0f} m/pixel"
                )

            except Exception:
                st.warning(tr("scan_unavailable"))

        if dem is None:
            try:
                dem = coarse_virtual_terrain(
                    *current
                )

                source_label = (
                    "NASA LOLA global DEM — "
                    "regional visual only"
                )
            except Exception as error:
                st.error(
                    tr("error") + ": " + str(error)
                )

        if dem is not None:
            if cells is None:
                cells = [
                    {
                        "id": f"{r + 1}-{c + 1}",
                        "value": None,
                        "status": "unknown",
                        "coverage": 0
                    }
                    for r in range(8)
                    for c in range(8)
                ]

            render_lander_scene(
                dem,
                cells,
                source_label
            )

            st.caption(tr("camera_note"))
            st.info(tr("scan_limit"))

            if high_resolution:
                st.success(tr("scan_loaded"))

                valid = [
                    c for c in cells
                    if c["value"] is not None
                ]

                if valid:
                    best = min(
                        valid,
                        key=lambda c: c["value"]
                    )

                    if is_ar():
                        st.write(
                            "**أقل ميل مقاس في الشبكة:** "
                            f"الخلية {best['id']} "
                            f"({best['value']}°). "
                            "هذا لا يعني أنها آمنة للهبوط."
                        )
                    else:
                        st.write(
                            "**Lowest measured screening slope:** "
                            f"Cell {best['id']} "
                            f"({best['value']}°). "
                            "This does not certify landing safety."
                        )

                st.download_button(
                    "تحميل نتائج المسح"
                    if is_ar()
                    else "Download Scan Data",
                    pd.DataFrame(cells).to_csv(
                        index=False
                    ),
                    file_name="OFOQ_terrain_scan.csv",
                    mime="text/csv"
                )


# ==================================================
# PAGE: SUN AND EARTH
# ==================================================

elif page == "visibility":
    st.header(tr("visibility"))

    selected_position_card()

    mission_date = st.date_input(
        tr("mission_date"),
        value=date(2026, 11, 14),
        key="mission_date"
    )

    duration = st.slider(
        tr("duration"),
        min_value=24,
        max_value=96,
        value=48,
        step=12,
        key="duration"
    )

    signature = (
        st.session_state.lat,
        st.session_state.lon,
        mission_date,
        duration
    )

    if st.button(
        tr("calculate"),
        type="primary"
    ):
        try:
            with st.spinner(
                "NASA JPL Horizons"
            ):
                start = datetime.combine(
                    mission_date,
                    datetime.min.time()
                )

                df = mission_data(
                    st.session_state.lat,
                    st.session_state.lon,
                    start,
                    duration
                )

            st.session_state.last_visibility = (
                signature, df
            )

        except Exception as error:
            st.error(
                tr("error") + ": " + str(error)
            )

    previous = st.session_state.last_visibility

    if previous and previous[0] == signature:
        draw_visibility(previous[1])


# ==================================================
# PAGE: COMPARE
# ==================================================

elif page == "compare":
    st.header(tr("compare_title"))

    selected_position_card()

    mission_date = st.date_input(
        tr("mission_date"),
        date(2026, 11, 14),
        key="compare_date"
    )

    duration = st.slider(
        tr("duration"),
        24, 96, 48, 12,
        key="compare_duration"
    )

    compare_type = st.segmented_control(
        tr("compare"),
        ["delay", "location"],
        format_func=lambda x: (
            tr("same_site")
            if x == "delay"
            else tr("other_site")
        ),
        default="delay",
        key="compare_type"
    )

    start_a = datetime.combine(
        mission_date,
        datetime.min.time()
    )

    start_b = start_a

    lat_b = st.session_state.lat
    lon_b = st.session_state.lon

    if compare_type == "delay":
        delay = st.slider(
            tr("delay"),
            0, 168, 48, 24
        )

        start_b += timedelta(
            hours=delay
        )

    else:
        st.caption(
            "اختر النقطة البديلة من خريطة القمر أولًا "
            "أو أدخل إحداثياتها هنا للمقارنة."
            if is_ar()
            else "Select a backup point on the map "
            "or enter backup coordinates here."
        )

        lat_b = st.number_input(
            tr("latitude"),
            -90.0, 90.0, -85.0,
            key="alt_lat"
        )

        lon_b = st.number_input(
            tr("longitude"),
            -180.0, 180.0, 0.0,
            key="alt_lon"
        )

    if st.button(
        tr("compare_button"),
        type="primary"
    ):
        try:
            with st.spinner("NASA Horizons"):
                original = mission_data(
                    st.session_state.lat,
                    st.session_state.lon,
                    start_a,
                    duration
                )

                alternative = mission_data(
                    lat_b, lon_b,
                    start_b, duration
                )

            first = mission_numbers(original)
            second = mission_numbers(alternative)

            left, right = st.columns(2)

            with left:
                st.subheader(tr("original"))

                for k, v in first.items():
                    st.metric(k, f"{v} h")

            with right:
                st.subheader(tr("alternative"))

                for k, v in second.items():
                    st.metric(
                        k,
                        f"{v} h",
                        delta=second[k] - first[k]
                    )

            fig = go.Figure()

            fig.add_trace(go.Bar(
                x=list(first.keys()),
                y=list(first.values()),
                name=tr("original"),
                marker_color="#588EB9"
            ))

            fig.add_trace(go.Bar(
                x=list(second.keys()),
                y=list(second.values()),
                name=tr("alternative"),
                marker_color="#B9DCEF"
            ))

            fig.update_layout(
                template="plotly_dark",
                paper_bgcolor="#091625",
                plot_bgcolor="#091625",
                barmode="group",
                title=tr("compare_title"),
                yaxis_title="Hours"
            )

            st.plotly_chart(
                fig,
                use_container_width=True
            )

            st.caption(tr("visibility_note"))

        except Exception as error:
            st.error(
                tr("error") + ": " + str(error)
            )


# ==================================================
# SOURCES
# ==================================================

st.divider()

with st.expander(tr("science")):
    st.markdown(
        """
        **NASA Scientific Visualization Studio**
        — Lunar imagery and global elevation models.

        https://svs.gsfc.nasa.gov/4720/

        **NASA LOLA South Pole COG**
        — Measured lunar elevation and slope.

        https://pgda.gsfc.nasa.gov/products/90

        **NASA JPL Horizons**
        — Sun and Earth apparent positions.

        https://ssd-api.jpl.nasa.gov/doc/horizons.html

        **Important limitations**

        - No certified safe-landing prediction.
        - The 3D lander view is virtual.
        - Terrain cells use an illustrative
          5° / 12° screening threshold,
          not NASA-approved safety limits.
        - Small boulders may be unresolved.
        - Horizons estimates use a geometric horizon.
        - Actual power and radio links are not modeled.
        """
    )

st.caption(
    "OFOQ | NASA SPACE APPS CHALLENGE 2026 | "
    "Independent research prototype | "
    "Not NASA-endorsed"
)
