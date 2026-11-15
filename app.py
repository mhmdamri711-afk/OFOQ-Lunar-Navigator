import base64
import html
import json
from datetime import date, datetime, timedelta
from io import BytesIO

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import rasterio
import requests
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image, ImageEnhance
from pyproj import CRS, Transformer
from rasterio.windows import Window


# ==========================================================
# OFOQ v9 — LUNAR MISSION NAVIGATOR
# ==========================================================

st.set_page_config(
    page_title="أُفُق | OFOQ",
    page_icon="🌙",
    layout="wide",
    initial_sidebar_state="expanded"
)

MOON_IMAGE = (
    "https://svs.gsfc.nasa.gov/vis/a000000/"
    "a004700/a004720/lroc_color_2k.jpg"
)

NASA_DATA = (
    "https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/"
)

SLOPE_FILE = "LDSM_80S_80MPP_ADJ.TIF"
HEIGHT_FILE = "LDEM_80S_80MPP_ADJ.TIF"

HORIZONS_API = (
    "https://ssd.jpl.nasa.gov/api/horizons.api"
)

LUNAR_CRS = CRS.from_proj4(
    "+proj=longlat +a=1737400 +b=1737400 "
    "+no_defs"
)

COLORS = {
    "space": "#050B16",
    "navy": "#10243A",
    "ice": "#76C5F5",
    "silver": "#DCECF7",
    "green": "#35B77A",
    "yellow": "#E3B84E",
    "red": "#D96868",
    "gray": "#6D7A8A",
}

# ==========================================================
# SESSION STATE
# ==========================================================

DEFAULTS = {
    "language": "العربية",
    "page": "explore",
    "view": "2D",
    "lat": -89.0,
    "lon": 0.0,
    "backup": None,
    "scan_result": None,
    "mission_result": None,
}

for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ==========================================================
# LANGUAGE
# ==========================================================

TEXT = {
    "explore": (
        "استكشف القمر",
        "Explore the Moon"
    ),
    "scan": (
        "كاميرا الهبوط وتحليل السطح",
        "Lander Camera & Landing Scan"
    ),
    "sun": (
        "الشمس والاتصال",
        "Sun & Communication"
    ),
    "compare": (
        "المقارنة والخطة البديلة",
        "Compare & Plan B"
    ),
    "choose": (
        "اختر الموقع بالضغط على سطح القمر",
        "Choose a site by clicking the Moon"
    ),
    "selected": (
        "الموقع المختار",
        "Selected location"
    ),
    "lat": ("خط العرض", "Latitude"),
    "lon": ("خط الطول", "Longitude"),
    "backup": (
        "احفظ الموقع للخطة البديلة",
        "Save backup site"
    ),
    "camera_title": (
        "كاميرا الهبوط الافتراضية",
        "Virtual Landing Camera"
    ),
    "camera_desc": (
        "منظر علوي يحاكي كاميرا المركبة قبل الهبوط. "
        "كل مربع يعرض مؤشر ملاءمة السطح مباشرة.",
        "A top-down simulated lander camera view. "
        "Each square displays a terrain suitability index."
    ),
    "best": (
        "أفضل المناطق في هذا المسح",
        "Best areas in this scan"
    ),
    "green": (
        "75% فأكثر — انحدار أقل",
        "75% or more — lower slope"
    ),
    "yellow": (
        "50% إلى أقل من 75% — يحتاج مراجعة",
        "50% to under 75% — review needed"
    ),
    "red": (
        "أقل من 50% — انحدار مرتفع",
        "Below 50% — higher slope"
    ),
    "gray": (
        "بيانات غير متاحة",
        "Data unavailable"
    ),
    "date": (
        "تاريخ المهمة (UTC)",
        "Mission date (UTC)"
    ),
    "hours": (
        "مدة المهمة بالساعات",
        "Mission duration (hours)"
    ),
    "analyze": (
        "احسب ظروف المهمة",
        "Analyze mission"
    ),
    "sunhours": (
        "ظهور الشمس",
        "Sun visible"
    ),
    "earthhours": (
        "ظهور الأرض",
        "Earth visible"
    ),
    "bothhours": (
        "الشمس والأرض معًا",
        "Sun and Earth together"
    ),
    "delay": (
        "تأخير الهبوط",
        "Landing delay"
    ),
    "different": (
        "موقع مختلف، نفس التاريخ",
        "Different site, same date"
    ),
    "same": (
        "نفس الموقع، تاريخ مختلف",
        "Same site, different date"
    ),
    "runcompare": (
        "قارن الخطتين",
        "Compare plans"
    ),
    "original": (
        "الخطة الأصلية",
        "Original plan"
    ),
    "alternative": (
        "الخطة البديلة",
        "Alternative plan"
    ),
    "sources": (
        "المصادر وحدود الدقة",
        "Sources and accuracy"
    ),
}


def tr(key):
    value = TEXT.get(key, (key, key))
    return (
        value[0]
        if st.session_state.language == "العربية"
        else value[1]
    )


def arabic():
    return st.session_state.language == "العربية"


def direction():
    return "rtl" if arabic() else "ltr"


def set_site(lat, lon):
    lat = max(-90.0, min(90.0, float(lat)))
    lon = ((float(lon) + 180) % 360) - 180

    st.session_state.lat = round(lat, 5)
    st.session_state.lon = round(lon, 5)
    st.session_state.scan_result = None
    st.session_state.mission_result = None


# ==========================================================
# DESIGN — OFOQ IDENTITY
# ==========================================================

st.markdown("""
<style>
.stApp {
    background:
      radial-gradient(
        circle at 82% 0%,
        #17324B 0%,
        #10243A 32%,
        #050B16 78%
      ) !important;
    color: #DCECF7;
}

[data-testid="stHeader"] {
    background: transparent !important;
}

[data-testid="stSidebar"] {
    background: #081522 !important;
    border-right: 1px solid #35536B;
}

.block-container {
    max-width: 1580px;
    padding-top: 1.1rem;
    padding-bottom: 3rem;
}

h1, h2, h3, p, label {
    color: #DCECF7 !important;
}

.stButton button {
    min-height: 52px;
    border-radius: 13px !important;
    background: #10243A !important;
    border: 1px solid #35536B !important;
    color: #DCECF7 !important;
    font-weight: 700 !important;
}

.stButton button:hover {
    background: #173A58 !important;
    border-color: #76C5F5 !important;
}

.stButton button[kind="primary"] {
    color: #050B16 !important;
    background: #76C5F5 !important;
    border-color: #76C5F5 !important;
}

[data-testid="stMetric"] {
    background: #10243A;
    border: 1px solid #35536B;
    border-radius: 16px;
    padding: 17px;
}

[data-testid="stMetricValue"] {
    color: #DCECF7;
}

.ofoq-hero {
    background:
      radial-gradient(
        circle at 80% 40%,
        #76C5F52E,
        transparent 27%
      ),
      linear-gradient(115deg,#050B16,#10243A);
    border: 1px solid #35536B;
    border-radius: 23px;
    padding: 28px 35px;
    margin-bottom: 20px;
    box-shadow: 0 18px 52px #00000055;
}

.ofoq-logo {
    font-size: clamp(38px,5vw,64px);
    font-weight: 850;
    color: #DCECF7;
    letter-spacing: 3px;
    margin: 5px 0;
}

.ofoq-tagline {
    font-size: 12px;
    letter-spacing: 2px;
    color: #76C5F5;
    font-weight: 700;
}

.ofoq-card {
    border: 1px solid #35536B;
    background: #10243A;
    border-radius: 16px;
    padding: 16px;
    margin-bottom: 13px;
}

.ofoq-card-title {
    color: #DCECF7;
    font-weight: 750;
    font-size: 16px;
    margin-bottom: 7px;
}

.ofoq-muted {
    color: #BBD2E1;
    font-size: 13px;
    line-height: 1.7;
}

[data-testid="stSidebar"] .stButton button {
    min-height: 64px;
    font-size: 15px;
    text-align: start;
}

hr {
    border-color: #35536B !important;
}
</style>
""", unsafe_allow_html=True)


# ==========================================================
# NASA IMAGE
# ==========================================================

@st.cache_data(ttl=86400, show_spinner=False)
def moon_texture():
    response = requests.get(MOON_IMAGE, timeout=35)
    response.raise_for_status()

    image = Image.open(
        BytesIO(response.content)
    ).convert("RGB")

    buffer = BytesIO()
    image.save(buffer, "JPEG", quality=90)

    return (
        "data:image/jpeg;base64,"
        + base64.b64encode(buffer.getvalue()).decode()
    )


def image_to_data_url(image):
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=92)

    return (
        "data:image/jpeg;base64,"
        + base64.b64encode(buffer.getvalue()).decode()
    )


# ==========================================================
# NASA POLAR TOPOGRAPHY — WINDOWED COG READING
# ==========================================================

def read_nasa_window(filename, lat, lon, size=48):
    url = NASA_DATA + filename

    with rasterio.Env(
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        GDAL_HTTP_TIMEOUT="18",
        GDAL_HTTP_MAX_RETRY="1",
        CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".TIF"
    ):
        with rasterio.open("/vsicurl/" + url) as src:
            if src.crs is None:
                raise ValueError("Missing lunar CRS")

            transformer = Transformer.from_crs(
                LUNAR_CRS,
                src.crs,
                always_xy=True
            )

            x, y = transformer.transform(lon, lat)
            row, col = src.index(x, y)

            half = size // 2

            if not (
                half <= row < src.height-half
                and half <= col < src.width-half
            ):
                raise ValueError(
                    "Selected point outside NASA coverage"
                )

            window = Window(
                col-half,
                row-half,
                size,
                size
            )

            result = src.read(
                1,
                window=window,
                masked=True
            )

            values = np.ma.array(
                result, dtype=float
            ).filled(np.nan)

            if src.nodata is not None:
                values[
                    np.isclose(values, src.nodata)
                ] = np.nan

            pixel_size = max(
                abs(src.transform.a),
                abs(src.transform.e)
            )

            return values, pixel_size


@st.cache_data(ttl=3600, show_spinner=False)
def get_terrain(lat, lon):
    if lat > -80:
        raise ValueError(
            "NASA polar dataset covers 80°S–90°S"
        )

    slope, pixel_size = read_nasa_window(
        SLOPE_FILE, lat, lon
    )

    elevation, _ = read_nasa_window(
        HEIGHT_FILE, lat, lon
    )

    if not np.isfinite(slope).any():
        raise ValueError("No valid slope measurements")

    if not np.isfinite(elevation).any():
        raise ValueError("No valid elevation measurements")

    return slope, elevation, pixel_size


# ==========================================================
# LUNAR TERRAIN IMAGE — FROM REAL NASA HEIGHTS
# ==========================================================

def create_lunar_relief(elevation, pixel_size):
    """
    A nadir-looking lunar terrain visualization
    generated from measured LOLA elevations.
    Not an actual spacecraft photograph.
    """

    z = np.asarray(elevation, dtype=float)
    finite = np.isfinite(z)

    if not finite.any():
        raise ValueError("No valid height samples")

    z = np.where(
        finite, z, np.nanmedian(z)
    )

    dy, dx = np.gradient(
        z, pixel_size, pixel_size
    )

    normal_x = -dx
    normal_y = -dy
    normal_z = np.ones_like(z)

    length = np.sqrt(
        normal_x**2
        + normal_y**2
        + normal_z**2
    )

    nx = normal_x / length
    ny = normal_y / length
    nz = normal_z / length

    # Low-angle illumination makes real terrain
    # relief visible, similar to orbital hillshade.
    light = np.array([-0.7, -0.45, 0.56])
    light = light / np.linalg.norm(light)

    illumination = (
        nx * light[0]
        + ny * light[1]
        + nz * light[2]
    )

    illumination = np.clip(
        illumination, 0, 1
    )

    gray = np.clip(
        45 + illumination * 200,
        0, 255
    ).astype(np.uint8)

    # Lunar silver-gray palette derived from
    # the OFOQ visual identity.
    rgb = np.stack([
        gray,
        np.clip(gray * 0.99, 0, 255),
        np.clip(gray * 1.02, 0, 255)
    ], axis=-1).astype(np.uint8)

    image = Image.fromarray(rgb, "RGB")

    image = image.resize(
        (1100, 1100),
        Image.Resampling.BICUBIC
    )

    return ImageEnhance.Contrast(image).enhance(1.2)


def fallback_moon_image(lat, lon):
    """
    Global NASA LRO texture fallback.
    This is NOT sufficiently detailed for
    site-specific landing hazard decisions.
    """
    response = requests.get(MOON_IMAGE, timeout=35)
    response.raise_for_status()

    image = Image.open(
        BytesIO(response.content)
    ).convert("RGB")

    width, height = image.size

    x = int((lon + 180) / 360 * width)
    y = int((90 - lat) / 180 * height)

    size = 170

    left = max(0, min(width-size, x-size//2))
    top = max(0, min(height-size, y-size//2))

    patch = image.crop(
        (left, top, left+size, top+size)
    )

    return patch.resize(
        (1100,1100),
        Image.Resampling.BICUBIC
    )


# ==========================================================
# 3×3 REAL SLOPE SCREENING
# ==========================================================

def slope_score(degrees):
    """
    OFOQ prototype slope-only screening index.

    0 degrees  -> 100%
    5 degrees  -> 75%
    10 degrees -> 50%
    20 degrees -> 0%

    This is NOT landing success probability.
    """
    return int(round(
        max(0, min(100, 100-5*degrees))
    ))


def score_class(score):
    if score is None:
        return "gray"

    if score >= 75:
        return "green"

    if score >= 50:
        return "yellow"

    return "red"


def position_name(row, col):
    arabic_names = [
        ["أعلى اليسار", "أعلى الوسط", "أعلى اليمين"],
        ["وسط اليسار", "المنتصف", "وسط اليمين"],
        ["أسفل اليسار", "أسفل الوسط", "أسفل اليمين"]
    ]

    english_names = [
        ["Top left", "Top center", "Top right"],
        ["Middle left", "Center", "Middle right"],
        ["Bottom left", "Bottom center", "Bottom right"]
    ]

    return (
        arabic_names[row][col]
        if arabic()
        else english_names[row][col]
    )


def create_cells(slope):
    cells = []

    for row in range(3):
        for col in range(3):

            cell = {
                "row": row,
                "col": col,
                "position": position_name(row, col),
                "score": None,
                "status": "gray",
                "slope": None,
                "coverage": 0
            }

            if slope is not None:
                block = slope[
                    row*16:(row+1)*16,
                    col*16:(col+1)*16
                ]

                valid = block[np.isfinite(block)]
                coverage = len(valid) / block.size

                cell["coverage"] = round(
                    coverage*100, 1
                )

                if coverage >= 0.75:
                    # 90th percentile of slope is
                    # a conservative cell descriptor.
                    p90 = float(
                        np.percentile(valid, 90)
                    )

                    score = slope_score(p90)

                    cell["score"] = score
                    cell["slope"] = round(p90, 2)
                    cell["status"] = score_class(score)

            cells.append(cell)

    return cells


def top_areas(cells):
    available = [
        cell for cell in cells
        if cell["score"] is not None
    ]

    return sorted(
        available,
        key=lambda cell:cell["score"],
        reverse=True
    )[:3]


# ==========================================================
# LANDER CAMERA — ONLY 9 SEMI-TRANSPARENT CELLS
# ==========================================================

def render_lander_camera(image, cells, pixel_size=None):
    image_data = image_to_data_url(image)
    cells_data = json.dumps(cells, ensure_ascii=False)

    title = (
        "أُفُق | كاميرا الهبوط الافتراضية"
        if arabic()
        else "OFOQ | Virtual Landing Camera"
    )

    unmeasured = (
        "غير متاح"
        if arabic()
        else "N/A"
    )

    # This view is 100% automatic.
    # No scan button and no cell IDs in the image.
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
    <style>
      * { box-sizing:border-box; }

      body {
        margin:0;
        background:#050B16;
        font-family:Arial,sans-serif;
      }

      .viewer {
        position:relative;
        width:100%;
        aspect-ratio:1/1;
        overflow:hidden;
        background:#050B16;
        border:1px solid #375873;
        border-radius:17px;
      }

      .terrain {
        position:absolute;
        inset:0;
        background-image:url('__IMAGE__');
        background-position:center;
        background-size:cover;
      }

      .shade {
        position:absolute;
        inset:0;
        background:linear-gradient(
          180deg,
          rgba(5,11,22,.26),
          transparent 27%,
          transparent 75%,
          rgba(5,11,22,.30)
        );
      }

      .grid {
        position:absolute;
        inset:8%;
        display:grid;
        grid-template-columns:repeat(3,1fr);
        grid-template-rows:repeat(3,1fr);
        gap:7px;
        z-index:2;
      }

      .cell {
        display:flex;
        align-items:center;
        justify-content:center;
        color:white;
        font-size:clamp(19px,3vw,38px);
        font-weight:800;
        text-shadow:
          0 2px 5px rgba(0,0,0,.9);
        border:1px solid rgba(255,255,255,.64);
        border-radius:9px;
        cursor:pointer;
        transition:filter .15s ease;
      }

      .cell:hover {
        filter:brightness(1.25);
        outline:2px solid white;
      }

      .green {
        background:rgba(53,183,122,.38);
      }

      .yellow {
        background:rgba(227,184,78,.38);
      }

      .red {
        background:rgba(217,104,104,.42);
      }

      .gray {
        background:rgba(109,122,138,.35);
      }

      .hud {
        position:absolute;
        left:16px;
        top:16px;
        z-index:5;
        border-radius:10px;
        padding:10px 14px;
        background:rgba(5,11,22,.85);
        border:1px solid #76C5F5;
        color:#DCECF7;
        font-size:12px;
        font-weight:700;
      }

      .detail {
        position:absolute;
        left:16px;
        right:16px;
        bottom:13px;
        z-index:5;
        border:1px solid #375873;
        background:rgba(5,11,22,.88);
        border-radius:11px;
        padding:12px 15px;
        color:#DCECF7;
        font-size:13px;
        line-height:1.6;
      }

      @media (max-width:600px) {
        .grid { gap:3px; inset:7%; }
        .cell { border-radius:5px; }
        .hud { font-size:10px; }
        .detail { font-size:11px; }
      }
    </style>
    </head>

    <body>
      <div class="viewer">
        <div class="terrain"></div>
        <div class="shade"></div>
        <div class="hud">__TITLE__</div>
        <div id="grid" class="grid"></div>
        <div id="detail" class="detail">
          __INSTRUCTION__
        </div>
      </div>

      <script>
        const cells=__CELLS__;
        const ar=__AR__;
        const grid=document.getElementById("grid");
        const detail=document.getElementById("detail");

        cells.forEach(cell=>{
          const el=document.createElement("div");
          el.className="cell "+cell.status;
          el.textContent=cell.score===null
            ? "--"
            : cell.score+"%";

          el.onclick=()=>{
            const score=cell.score===null
              ? "__MISSING__"
              : cell.score+"%";

            const slope=cell.slope===null
              ? "__MISSING__"
              : cell.slope+"°";

            detail.textContent=ar
              ? (
                cell.position+
                " | المؤشر: "+score+
                " | ميل السطح P90: "+slope+
                " | البيانات الصالحة: "+
                cell.coverage+"%"
              )
              : (
                cell.position+
                " | Index: "+score+
                " | Slope P90: "+slope+
                " | Valid data: "+
                cell.coverage+"%"
              );
          };

          grid.appendChild(el);
        });
      </script>
    </body>
    </html>
    """

    instruction = (
        "اضغط على أي مربع لعرض سبب تقييمه"
        if arabic()
        else "Click a square to inspect its measurement"
    )

    html_content = (
        html_content
        .replace("__IMAGE__", image_data)
        .replace("__TITLE__", html.escape(title))
        .replace("__INSTRUCTION__", instruction)
        .replace("__CELLS__", cells_data)
        .replace("__AR__", "true" if arabic() else "false")
        .replace("__MISSING__", unmeasured)
    )

    # Fixed viewer with responsive square layout.
    components.html(
        html_content,
        height=790,
        scrolling=False
    )


# ==========================================================
# MOON 2D / 3D PICKER — ONE VIEW AT A TIME
# ==========================================================

PICKER_HTML = """
<div class="moon-stage"></div>
"""

PICKER_CSS = """
.moon-stage {
  position:relative;
  width:100%;
  height:510px;
  overflow:hidden;
  background:#050B16;
  border:1px solid #375873;
  border-radius:18px;
}

.moon-stage canvas {
  width:100%;
  height:100%;
  display:block;
  cursor:crosshair;
  touch-action:none;
}
"""

PICKER_JS = """
export default function(component) {
  const {data,parentElement,setTriggerValue}=component;

  const stage=parentElement.querySelector(".moon-stage");
  stage.replaceChildren();

  let disposed=false;
  let cleanup=()=>{};

  function select(lat,lon) {
    lon=((lon+180)%360+360)%360-180;

    setTriggerValue("picked",{
      lat:Math.max(-90,Math.min(90,lat)),
      lon:lon,
      id:Date.now()+Math.random()
    });
  }

  // 2D: A SINGLE FULL MOON IMAGE.
  if(data.mode==="2D") {
    const canvas=document.createElement("canvas");
    canvas.width=1100;
    canvas.height=550;
    stage.appendChild(canvas);

    const ctx=canvas.getContext("2d");
    const image=new Image();

    let zoom=1;
    let cx=1024;
    let cy=512;
    let down=null;
    let dragging=false;

    function viewport(){
      const vw=image.width/zoom;
      const vh=image.height/zoom;

      return {
        x:Math.max(0,Math.min(image.width-vw,cx-vw/2)),
        y:Math.max(0,Math.min(image.height-vh,cy-vh/2)),
        w:vw,h:vh
      };
    }

    function draw(){
      if(!image.naturalWidth)return;

      const v=viewport();

      ctx.fillStyle="#050B16";
      ctx.fillRect(0,0,1100,550);

      ctx.drawImage(
        image,v.x,v.y,v.w,v.h,
        0,0,1100,550
      );

      const x0=(data.lon+180)/360*image.width;
      const y0=(90-data.lat)/180*image.height;

      const x=(x0-v.x)/v.w*1100;
      const y=(y0-v.y)/v.h*550;

      if(x>=0&&x<=1100&&y>=0&&y<=550){
        ctx.strokeStyle="#76C5F5";
        ctx.lineWidth=4;
        ctx.beginPath();
        ctx.arc(x,y,13,0,Math.PI*2);
        ctx.stroke();

        ctx.fillStyle="#DCECF7";
        ctx.beginPath();
        ctx.arc(x,y,4,0,Math.PI*2);
        ctx.fill();
      }
    }

    image.onload=()=>{
      cx=(data.lon+180)/360*image.width;
      cy=(90-data.lat)/180*image.height;
      draw();
    };

    image.src=data.texture;

    function point(e){
      const r=canvas.getBoundingClientRect();
      return {
        x:(e.clientX-r.left)/r.width*1100,
        y:(e.clientY-r.top)/r.height*550
      };
    }

    canvas.onpointerdown=e=>{
      down={...point(e),cx,cy};
      dragging=false;
      canvas.setPointerCapture(e.pointerId);
    };

    canvas.onpointermove=e=>{
      if(!down||!image.naturalWidth)return;

      const p=point(e);
      const dx=p.x-down.x;
      const dy=p.y-down.y;

      if(Math.hypot(dx,dy)>5)dragging=true;

      if(dragging){
        cx=down.cx-dx/1100*image.width/zoom;
        cy=down.cy-dy/550*image.height/zoom;
        draw();
      }
    };

    canvas.onpointerup=e=>{
      if(!down||!image.naturalWidth)return;

      if(!dragging){
        const p=point(e);
        const v=viewport();

        const ix=v.x+p.x/1100*v.w;
        const iy=v.y+p.y/550*v.h;

        const lat=90-iy/image.height*180;
        const lon=ix/image.width*360-180;

        data.lat=lat;
        data.lon=lon;
        draw();
        select(lat,lon);
      }

      down=null;
      dragging=false;
    };

    canvas.onwheel=e=>{
      e.preventDefault();
      zoom=Math.max(
        1,Math.min(7,zoom*(e.deltaY<0?1.2:1/1.2))
      );
      draw();
    };

  } else {
    // 3D: ONE ROTATABLE MOON GLOBE.
    (async()=>{
      try{
        const THREE=await import(
          "https://esm.sh/three@0.160.0"
        );
        const addon=await import(
          "https://esm.sh/three@0.160.0/examples/jsm/controls/OrbitControls.js"
        );

        if(disposed)return;

        const scene=new THREE.Scene();
        scene.background=new THREE.Color(0x050B16);

        const camera=new THREE.PerspectiveCamera(
          44,1,.1,100
        );
        camera.position.set(0,0,4.8);

        const renderer=new THREE.WebGLRenderer({
          antialias:true
        });

        renderer.setPixelRatio(
          Math.min(window.devicePixelRatio,2)
        );
        stage.appendChild(renderer.domElement);

        const tex=new THREE.TextureLoader().load(
          data.texture
        );
        tex.colorSpace=THREE.SRGBColorSpace;

        const globe=new THREE.Mesh(
          new THREE.SphereGeometry(1.65,96,64),
          new THREE.MeshStandardMaterial({
            map:tex,roughness:1
          })
        );

        scene.add(globe);
        scene.add(
          new THREE.AmbientLight(0xffffff,1.5)
        );

        const light=new THREE.DirectionalLight(
          0xffffff,2
        );
        light.position.set(4,3,6);
        scene.add(light);

        const controls=new addon.OrbitControls(
          camera,renderer.domElement
        );
        controls.enableDamping=true;
        controls.enablePan=false;
        controls.minDistance=2.1;
        controls.maxDistance=8;

        const marker=new THREE.Mesh(
          new THREE.SphereGeometry(.045,12,12),
          new THREE.MeshBasicMaterial({
            color:0x76C5F5
          })
        );
        scene.add(marker);

        function moveMarker(lat,lon){
          const phi=(lon+180)/360*Math.PI*2;
          const a=lat*Math.PI/180;

          marker.position.set(
            -1.7*Math.cos(phi)*Math.cos(a),
             1.7*Math.sin(a),
             1.7*Math.sin(phi)*Math.cos(a)
          );
        }

        moveMarker(data.lat,data.lon);

        const raycaster=new THREE.Raycaster();
        const mouse=new THREE.Vector2();
        let down=null;

        renderer.domElement.onpointerdown=e=>{
          down={x:e.clientX,y:e.clientY};
        };

        renderer.domElement.onpointerup=e=>{
          if(!down)return;

          const d=Math.hypot(
            e.clientX-down.x,
            e.clientY-down.y
          );
          down=null;
          if(d>6)return;

          const rect=
            renderer.domElement.getBoundingClientRect();

          mouse.x=((e.clientX-rect.left)/rect.width)*2-1;
          mouse.y=-((e.clientY-rect.top)/rect.height)*2+1;

          raycaster.setFromCamera(mouse,camera);

          const hits=raycaster.intersectObject(globe);

          if(!hits.length||!hits[0].uv)return;

          const lon=hits[0].uv.x*360-180;
          const lat=hits[0].uv.y*180-90;

          moveMarker(lat,lon);
          select(lat,lon);
        };

        function resize(){
          const w=stage.clientWidth||850;
          renderer.setSize(w,510);
          camera.aspect=w/510;
          camera.updateProjectionMatrix();
        }

        resize();

        let frame=null;
        function animate(){
          if(disposed)return;
          frame=requestAnimationFrame(animate);
          controls.update();
          renderer.render(scene,camera);
        }
        animate();

        cleanup=()=>{
          if(frame)cancelAnimationFrame(frame);
          controls.dispose();
          renderer.dispose();
          tex.dispose();
        };

      }catch(error){
        stage.textContent="3D: "+String(error);
      }
    })();
  }

  return()=>{
    disposed=true;
    cleanup();
    stage.replaceChildren();
  };
}
"""

MOON_PICKER = st.components.v2.component(
    "ofoq_moon_picker_v9",
    html=PICKER_HTML,
    css=PICKER_CSS,
    js=PICKER_JS
)


# ==========================================================
# NASA JPL HORIZONS
# ==========================================================

@st.cache_data(ttl=3600, show_spinner=False)
def horizons(body, lat, lon, start_text, hours):
    start = datetime.strptime(
        start_text,"%Y-%m-%d %H:%M"
    )

    end = start + timedelta(hours=hours)

    params = {
        "format":"json",
        "COMMAND":f"'{body}'",
        "OBJ_DATA":"'NO'",
        "MAKE_EPHEM":"'YES'",
        "EPHEM_TYPE":"'OBSERVER'",
        "CENTER":"'coord@301'",
        "COORD_TYPE":"'GEODETIC'",
        "SITE_COORD":f"'{lon},{lat},0'",
        "START_TIME":f"'{start:%Y-%m-%d %H:%M}'",
        "STOP_TIME":f"'{end:%Y-%m-%d %H:%M}'",
        "STEP_SIZE":"'1 h'",
        "QUANTITIES":"'4'",
        "CSV_FORMAT":"'YES'",
        "TIME_TYPE":"'UT'",
        "APPARENT":"'AIRLESS'"
    }

    response = requests.get(
        HORIZONS,
        params=params,
        timeout=60
    )

    response.raise_for_status()
    result = response.json()["result"]

    if "$$SOE" not in result or "$$EOE" not in result:
        raise ValueError(result[:350])

    block = (
        result.split("$$SOE",1)[1]
        .split("$$EOE",1)[0]
    )

    rows = []

    for line in block.splitlines():
        p = [x.strip() for x in line.split(",")]

        if len(p)<5:
            continue

        try:
            rows.append({
                "time":pd.to_datetime(
                    p[0],
                    format="%Y-%b-%d %H:%M"
                ),
                "elevation":float(p[4])
            })
        except ValueError:
            continue

    if not rows:
        raise ValueError(
            "No valid NASA ephemeris records"
        )

    return pd.DataFrame(rows)


def mission_analysis(lat, lon, start, hours):
    text = start.strftime("%Y-%m-%d %H:%M")

    sun = horizons("10",lat,lon,text,hours)
    earth = horizons("399",lat,lon,text,hours)

    df = sun.merge(
        earth,
        on="time",
        suffixes=("_sun","_earth")
    ).sort_values("time")

    df = df.iloc[:-1].copy()

    if len(df)!=hours:
        raise ValueError(
            "Incomplete hourly NASA data"
        )

    df["Sun"] = df.elevation_sun>0
    df["Earth"] = df.elevation_earth>0
    df["Both"] = df.Sun & df.Earth

    return df


def metrics(df):
    return {
        "Sun":int(df.Sun.sum()),
        "Earth":int(df.Earth.sum()),
        "Both":int(df.Both.sum())
    }


# ==========================================================
# SIDEBAR
# ==========================================================

with st.sidebar:
    st.markdown("## أُفُق | OFOQ")

    st.caption("BEYOND THE HORIZON")

    st.selectbox(
        "Language",
        ["العربية","English"],
        key="language",
        label_visibility="collapsed"
    )

    st.divider()

    sections = [
        ("explore","◉","explore"),
        ("scan","▦","scan"),
        ("sun","☼","sun"),
        ("compare","◇","compare")
    ]

    for key,icon,title in sections:
        if st.button(
            f"{icon}  {tr(title)}",
            key="nav_"+key,
            type=(
                "primary"
                if st.session_state.page==key
                else "secondary"
            ),
            use_container_width=True
        ):
            st.session_state.page=key
            st.rerun()

    st.divider()

    st.caption(tr("selected"))

    st.write(
        f"{tr('lat')}: **{st.session_state.lat:.5f}°**"
    )

    st.write(
        f"{tr('lon')}: **{st.session_state.lon:.5f}°**"
    )

    if st.button(
        tr("backup"),
        use_container_width=True
    ):
        st.session_state.backup=(
            st.session_state.lat,
            st.session_state.lon
        )
        st.success("✓")


# ==========================================================
# HERO
# ==========================================================

st.markdown(
    f"""
    <div class="ofoq-hero" dir="{direction()}">
      <div style="color:#76C5F5;font-size:12px;
                  letter-spacing:2px;font-weight:700;">
        NASA SPACE APPS CHALLENGE 2026
      </div>
      <div class="ofoq-logo">أُفُق | OFOQ</div>
      <div style="color:#76C5F5;font-size:12px;
                  letter-spacing:2px;">
        BEYOND THE HORIZON, TOWARD THE MOON.
      </div>
      <p>
        {"استكشف القمر، اختر موقعًا، وافحص ظروف المهمة."
         if arabic()
         else "Explore the Moon, choose a site, "
              "and investigate mission conditions."}
      </p>
    </div>
    """,
    unsafe_allow_html=True
)


# ==========================================================
# PAGE 1 — EXPLORE
# ==========================================================

if st.session_state.page=="explore":
    st.header(tr("explore"))
    st.write(tr("choose"))

    a,b=st.columns(2)

    with a:
        if st.button(
            "2D MAP",
            type=(
                "primary"
                if st.session_state.view=="2D"
                else "secondary"
            ),
            use_container_width=True
        ):
            st.session_state.view="2D"
            st.rerun()

    with b:
        if st.button(
            "3D MOON",
            type=(
                "primary"
                if st.session_state.view=="3D"
                else "secondary"
            ),
            use_container_width=True
        ):
            st.session_state.view="3D"
            st.rerun()

    try:
        result = MOON_PICKER(
            data={
                "mode":st.session_state.view,
                "texture":moon_texture(),
                "lat":st.session_state.lat,
                "lon":st.session_state.lon
            },
            key="ofoq_moon_view",
            on_picked_change=lambda:None
        )

        point=getattr(result,"picked",None)

        if point is not None:
            set_site(
                point["lat"],
                point["lon"]
            )
            st.rerun()

    except Exception as error:
        st.error(str(error))

    a,b=st.columns(2)

    a.metric(
        tr("lat"),f"{st.session_state.lat:.5f}°"
    )

    b.metric(
        tr("lon"),f"{st.session_state.lon:.5f}°"
    )


# ==========================================================
# PAGE 2 — LANDER CAMERA + 3x3 LANDING SCAN
# ==========================================================

elif st.session_state.page=="scan":
    st.header(tr("camera_title"))
    st.write(tr("camera_desc"))

    site = (
        st.session_state.lat,
        st.session_state.lon
    )

    if (
        st.session_state.scan_result is None
        or st.session_state.scan_result["site"] != site
    ):
        try:
            with st.spinner(
                "NASA LOLA / Real terrain analysis"
            ):
                slope,elevation,pixel_size=get_terrain(
                    *site
                )

                image=create_lunar_relief(
                    elevation,pixel_size
                )

                cells=create_cells(slope)

            st.session_state.scan_result={
                "site":site,
                "image":image,
                "cells":cells,
                "pixel":pixel_size,
                "real":True,
                "error":None
            }

        except Exception as error:
            try:
                image=fallback_moon_image(*site)
            except Exception:
                image=Image.new(
                    "RGB",(1100,1100),(45,49,56)
                )

            st.session_state.scan_result={
                "site":site,
                "image":image,
                "cells":create_cells(None),
                "pixel":None,
                "real":False,
                "error":str(error)
            }

    scan=st.session_state.scan_result
    cells=scan["cells"]

    left,right=st.columns([3,1],gap="large")

    with left:
        render_lander_camera(
            scan["image"],
            cells,
            scan["pixel"]
        )

    with right:
        st.markdown("### " + tr("best"))

        legend = [
            ("green",tr("green")),
            ("yellow",tr("yellow")),
            ("red",tr("red")),
            ("gray",tr("gray"))
        ]

        st.markdown(
            '<div class="ofoq-card">',
            unsafe_allow_html=True
        )

        for color,label in legend:
            st.markdown(
                f'<div style="display:flex;align-items:center;'
                f'gap:9px;margin-bottom:10px;">'
                f'<span style="width:14px;height:14px;'
                f'border-radius:3px;display:inline-block;'
                f'background:{COLORS[color]};"></span>'
                f'<span>{html.escape(label)}</span></div>',
                unsafe_allow_html=True
            )

        st.markdown(
            '</div>',
            unsafe_allow_html=True
        )

        ranked=top_areas(cells)

        if ranked:
            for index,cell in enumerate(ranked,1):
                st.markdown(
                    f"""
                    <div class="ofoq-card"
                         dir="{direction()}">
                      <div class="ofoq-card-title">
                        #{index} — {cell['position']}
                      </div>
                      <div style="color:#76C5F5;
                                  font-size:28px;
                                  font-weight:850;">
                        {cell['score']}%
                      </div>
                      <div class="ofoq-muted">
                        {"الميل المقاس" if arabic()
                         else "Measured slope"}:
                        {cell['slope']}°
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
        else:
            st.info(tr("gray"))

    if scan["real"]:
        st.success(
            "تم حساب الخلايا من قياسات NASA LOLA."
            if arabic()
            else "Cells were calculated using NASA LOLA."
        )

        cell_width=16*scan["pixel"]

        st.caption(
            f"Source resolution: {scan['pixel']:.0f} m/pixel "
            f"| Approximate cell width: {cell_width:.0f} m"
        )

        st.download_button(
            "تحميل النتائج"
            if arabic()
            else "Download results",
            data=pd.DataFrame(cells).to_csv(
                index=False
            ),
            file_name="OFOQ_landing_scan.csv",
            mime="text/csv"
        )

    else:
        st.warning(
            "تعذر تحميل قياسات التضاريس. لن تُعرض "
            "نسب مصطنعة؛ الخلايا الرمادية تعني "
            "أن البيانات غير متاحة."
            if arabic()
            else "Terrain measurements unavailable. "
                 "No fabricated scores are displayed."
        )

        with st.expander(
            "التفاصيل التقنية"
            if arabic()
            else "Technical details"
        ):
            st.code(scan["error"])

    st.caption(
        "الكاميرا هنا محاكاة عمودية من بيانات ارتفاعات "
        "القمر، وليست صورة التقطتها مركبة حقيقية. "
        "النسبة مؤشر قائم على الميل فقط وليست "
        "احتمال نجاح الهبوط."
        if arabic()
        else "The nadir camera view is simulated from "
             "lunar elevation data. Percentages are "
             "slope-based indices, not landing probabilities."
    )


# ==========================================================
# PAGE 3 — SUN & EARTH
# ==========================================================

elif st.session_state.page=="sun":
    st.header(tr("sun"))

    mission_date=st.date_input(
        tr("date"),
        value=date(2026,11,15)
    )

    hours=st.slider(
        tr("hours"),
        24,96,48,12
    )

    signature=(
        st.session_state.lat,
        st.session_state.lon,
        mission_date,
        hours
    )

    if st.button(
        tr("analyze"),type="primary"
    ):
        try:
            start=datetime.combine(
                mission_date,
                datetime.min.time()
            )

            with st.spinner("NASA Horizons"):
                df=mission_analysis(
                    st.session_state.lat,
                    st.session_state.lon,
                    start,hours
                )

            st.session_state.mission_result=(
                signature,df
            )

        except Exception as error:
            st.error(str(error))

    saved=st.session_state.mission_result

    if saved and saved[0]==signature:
        df=saved[1]
        n=metrics(df)

        a,b,c=st.columns(3)

        a.metric(tr("sunhours"),f"{n['Sun']} h")
        b.metric(tr("earthhours"),f"{n['Earth']} h")
        c.metric(tr("bothhours"),f"{n['Both']} h")

        fig=go.Figure()

        fig.add_trace(go.Scatter(
            x=df.time,
            y=df.elevation_sun,
            name="Sun",
            line=dict(color="#DCECF7",width=3)
        ))

        fig.add_trace(go.Scatter(
            x=df.time,
            y=df.elevation_earth,
            name="Earth",
            line=dict(color="#76C5F5",width=3)
        ))

        fig.add_hline(
            y=0,
            line_dash="dash",
            line_color="#6D7A8A"
        )

        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="#081522",
            plot_bgcolor="#081522",
            xaxis_title="UTC",
            yaxis_title="Elevation (°)",
            height=400
        )

        st.plotly_chart(
            fig,use_container_width=True
        )

        st.caption(
            "تقديرات هندسية كل ساعة، دون تأثير "
            "الجبال أو جودة الاتصال الفعلية."
            if arabic()
            else "Hourly geometric estimates only."
        )


# ==========================================================
# PAGE 4 — MISSION PLAN B
# ==========================================================

elif st.session_state.page=="compare":
    st.header(tr("compare"))

    mission_date=st.date_input(
        tr("date"),
        value=date(2026,11,15),
        key="compare_date"
    )

    hours=st.slider(
        tr("hours"),
        24,96,48,12,
        key="compare_hours"
    )

    mode=st.radio(
        "Comparison",
        ["delay","site"],
        format_func=lambda x:(
            tr("same")
            if x=="delay"
            else tr("different")
        )
    )

    start_a=datetime.combine(
        mission_date,
        datetime.min.time()
    )

    start_b=start_a
    lat_b=st.session_state.lat
    lon_b=st.session_state.lon

    if mode=="delay":
        delay=st.slider(
            tr("delay"),
            0,168,48,24
        )

        start_b+=timedelta(hours=delay)

    else:
        if st.session_state.backup:
            lat_b,lon_b=st.session_state.backup

            st.info(
                f"{lat_b:.5f}°, {lon_b:.5f}°"
            )
        else:
            st.warning(
                "احفظ موقعًا بديلًا من صفحة القمر أولًا."
                if arabic()
                else "Save a backup location first."
            )

    if st.button(
        tr("runcompare"),
        type="primary",
        disabled=(
            mode=="site"
            and st.session_state.backup is None
        )
    ):
        try:
            with st.spinner("NASA Horizons"):
                first=mission_analysis(
                    st.session_state.lat,
                    st.session_state.lon,
                    start_a,hours
                )

                second=mission_analysis(
                    lat_b,lon_b,start_b,hours
                )

            n1=metrics(first)
            n2=metrics(second)

            left,right=st.columns(2)

            with left:
                st.subheader(tr("original"))
                for key,value in n1.items():
                    st.metric(key,f"{value} h")

            with right:
                st.subheader(tr("alternative"))
                for key,value in n2.items():
                    st.metric(
                        key,
                        f"{value} h",
                        delta=value-n1[key]
                    )

            fig=go.Figure()

            fig.add_trace(go.Bar(
                x=list(n1),
                y=list(n1.values()),
                name=tr("original"),
                marker_color="#6D7A8A"
            ))

            fig.add_trace(go.Bar(
                x=list(n2),
                y=list(n2.values()),
                name=tr("alternative"),
                marker_color="#76C5F5"
            ))

            fig.update_layout(
                barmode="group",
                template="plotly_dark",
                paper_bgcolor="#081522",
                plot_bgcolor="#081522",
                height=350
            )

            st.plotly_chart(
                fig,use_container_width=True
            )

        except Exception as error:
            st.error(str(error))


# ==========================================================
# SOURCES
# ==========================================================

st.divider()

with st.expander(tr("sources")):
    st.markdown("""
**NASA Lunar Reconnaissance Orbiter / LOLA**

https://pgda.gsfc.nasa.gov/products/90

**NASA Moon Visualizations**

https://svs.gsfc.nasa.gov/4720/

**NASA/JPL Horizons**

https://ssd-api.jpl.nasa.gov/doc/horizons.html

**Scientific limitations**

- Scan values use measured slope where available.
- Score = max(0, min(100, 100 - 5 × slope P90)).
- Green: 75–100; Yellow: 50–74; Red: below 50.
- Gray: insufficient or unavailable data.
- This is not a percentage probability of landing success.
- Small obstacles may be unresolved.
- The camera is a height-map visualization.
- Solar/Earth visibility does not include terrain masking.
- OFOQ is not a NASA-certified landing system.
""")

st.caption(
    "TEAM OFOQ | NASA SPACE APPS CHALLENGE 2026"
)
