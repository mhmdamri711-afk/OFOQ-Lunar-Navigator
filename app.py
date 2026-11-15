import base64
import json
from datetime import datetime, date, timedelta
from io import BytesIO

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import rasterio
import requests
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image, ImageDraw, ImageEnhance
from pyproj import CRS, Transformer
from rasterio.windows import Window
from streamlit_image_coordinates import streamlit_image_coordinates

# ============================================================
# OFOQ v8
# ============================================================

st.set_page_config(
    page_title="OFOQ | أُفُق",
    page_icon="🌙",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ------------------------------------------------------------
# CONSTANTS
# ------------------------------------------------------------

NASA_MOON_TEXTURE = (
    "https://svs.gsfc.nasa.gov/vis/a000000/"
    "a004700/a004720/lroc_color_2k.jpg"
)

NASA_SLOPE_COG = (
    "https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/"
    "LDSM_80S_80MPP_ADJ.TIF"
)

HORIZONS_API = "https://ssd.jpl.nasa.gov/api/horizons.api"

MOON_GEO_CRS = CRS.from_proj4(
    "+proj=longlat +a=1737400 +b=1737400 +no_defs"
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

# ------------------------------------------------------------
# SESSION STATE
# ------------------------------------------------------------

defaults = {
    "lang": "العربية",
    "page": "explore",
    "view_mode": "2D",
    "lat": -89.0,
    "lon": 0.0,
    "backup_site": None,
    "last_3d_pick_id": None,
    "scan_result": None,
    "visibility_result": None,
}

for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ------------------------------------------------------------
# BILINGUAL TEXT
# ------------------------------------------------------------

TXT = {
    "explore": ("استكشف القمر", "Explore the Moon"),
    "scan": ("كاميرا الهبوط وتحليل سطح الموقع", "Lander Camera & Landing Scan"),
    "sun": ("الشمس والاتصال", "Sun & Communication"),
    "compare": ("المقارنة والخطة البديلة", "Compare & Plan B"),
    "selected_site": ("الموقع الحالي", "Current site"),
    "lat": ("خط العرض", "Latitude"),
    "lon": ("خط الطول", "Longitude"),
    "save_backup": ("حفظ الموقع كخطة بديلة", "Save as Backup Site"),
    "choose_site": (
        "اختر موقعك بالضغط على القمر",
        "Choose your site by clicking the Moon",
    ),
    "explore_note": (
        "في وضع 2D اختر نقطة مباشرة من الخريطة. "
        "وفي وضع 3D يمكنك تدوير القمر والضغط على المكان المطلوب.",
        "In 2D, choose a point directly from the map. "
        "In 3D, rotate the Moon and click the desired location.",
    ),
    "start_scan": ("ابدأ تحليل الموقع", "Start Site Analysis"),
    "scan_note": (
        "يعرض هذا القسم صورة علوية لسطح القمر مع شبكة تقييم للهبوط. "
        "كل خلية تعرض لونها ورقم تقييمها مباشرة.",
        "This section shows a top-down lunar surface view with a landing evaluation grid. "
        "Each cell shows its color and score directly.",
    ),
    "best_areas": ("أفضل أماكن الهبوط", "Best Landing Areas"),
    "legend": ("مفتاح الألوان", "Color Legend"),
    "green": ("مناسب أكثر للهبوط", "More suitable for landing"),
    "yellow": ("يحتاج حذرًا", "Needs caution"),
    "red": ("أعلى خطورة", "Higher risk"),
    "gray": ("بيانات غير كافية", "Insufficient data"),
    "scan_loaded": ("تم تحليل التضاريس بنجاح", "Terrain analysis completed"),
    "scan_failed": (
        "تعذر تحميل بيانات الميل من NASA لهذا الموقع. "
        "ستظهر الشبكة باللون الرمادي.",
        "Could not load NASA slope data for this site. "
        "The grid will appear gray.",
    ),
    "date": ("تاريخ المهمة UTC", "Mission date UTC"),
    "duration": ("مدة المهمة بالساعات", "Mission duration in hours"),
    "run_visibility": ("احسب ظروف المهمة", "Calculate Mission Conditions"),
    "sun_hours": ("ساعات ظهور الشمس", "Sun visibility hours"),
    "earth_hours": ("ساعات ظهور الأرض", "Earth visibility hours"),
    "both_hours": ("ظهورهما معًا", "Both visible hours"),
    "compare_title": (
        "ماذا يحدث إذا تغيرت الخطة؟",
        "What happens if the plan changes?",
    ),
    "same_site": ("نفس الموقع، وقت مختلف", "Same site, different time"),
    "other_site": ("موقع آخر، نفس الوقت", "Different site, same time"),
    "delay_hours": ("التأخير بالساعات", "Delay in hours"),
    "run_compare": ("قارن الخطتين", "Compare Plans"),
    "original": ("الخطة الأصلية", "Original Plan"),
    "alternative": ("الخطة البديلة", "Alternative Plan"),
    "sources": ("المصادر والحدود العلمية", "Sources and Scientific Limitations"),
}

def tr(key):
    a, b = TXT.get(key, (key, key))
    return a if st.session_state.lang == "العربية" else b

def is_ar():
    return st.session_state.lang == "العربية"

def set_site(lat, lon):
    lat = max(-90.0, min(90.0, float(lat)))
    lon = ((float(lon) + 180.0) % 360.0) - 180.0

    st.session_state.lat = round(lat, 5)
    st.session_state.lon = round(lon, 5)
    st.session_state.scan_result = None
    st.session_state.visibility_result = None

# ------------------------------------------------------------
# STYLING
# ------------------------------------------------------------

st.markdown(
    """
<style>
.stApp {
    background:
      radial-gradient(circle at 80% 0%, #18314A 0%, #10243A 34%, #050B16 78%) !important;
    color: #DCECF7;
}
[data-testid="stHeader"] {
    background: transparent !important;
}
[data-testid="stSidebar"] {
    background: #081522 !important;
    border-right: 1px solid #294962;
}
.block-container {
    max-width: 1550px;
    padding-top: 1rem;
    padding-bottom: 3rem;
}
h1, h2, h3, p, label, div {
    color: #DCECF7;
}
[data-testid="stMetric"] {
    background: #10243A;
    border: 1px solid #375873;
    border-radius: 16px;
    padding: 16px;
}
[data-testid="stMetricValue"] {
    color: #DCECF7;
}
.stButton > button {
    min-height: 50px;
    border-radius: 14px !important;
    background: #10243A !important;
    color: #DCECF7 !important;
    border: 1px solid #375873 !important;
    font-weight: 700 !important;
}
.stButton > button:hover {
    border-color: #76C5F5 !important;
    background: #17324B !important;
}
.stButton > button[kind="primary"] {
    background: #76C5F5 !important;
    color: #050B16 !important;
    border-color: #76C5F5 !important;
}
.hero {
    border: 1px solid #375873;
    border-radius: 24px;
    padding: 28px 34px;
    margin-bottom: 18px;
    background:
      radial-gradient(circle at 78% 34%, rgba(118,197,245,.18), transparent 22%),
      linear-gradient(120deg, #050B16, #10243A);
    box-shadow: 0 20px 55px rgba(0,0,0,.35);
}
.hero h1 {
    margin: 8px 0;
    font-size: clamp(38px, 5vw, 64px);
    letter-spacing: 2px;
    font-weight: 850;
}
.hero .eyebrow {
    color: #76C5F5;
    font-size: 12px;
    letter-spacing: 2px;
    font-weight: 700;
}
.hero .sub {
    color: #DCECF7;
    opacity: .9;
    font-size: 16px;
}
.sidebar-title {
    font-size: 28px;
    font-weight: 800;
    margin-bottom: 2px;
}
.sidebar-sub {
    color: #76C5F5;
    font-size: 12px;
    letter-spacing: 1px;
    margin-bottom: 12px;
}
.nav-hint {
    color: #76C5F5;
    font-size: 12px;
    letter-spacing: 1px;
    margin: 10px 0 6px;
}
.info-card {
    background: #10243A;
    border: 1px solid #375873;
    border-radius: 16px;
    padding: 15px 18px;
}
.legend-box {
    background: #10243A;
    border: 1px solid #375873;
    border-radius: 16px;
    padding: 14px 16px;
}
.legend-row {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 10px;
}
.legend-color {
    width: 14px;
    height: 14px;
    border-radius: 3px;
}
.best-card {
    background: #10243A;
    border: 1px solid #375873;
    border-radius: 14px;
    padding: 12px 14px;
    margin-bottom: 10px;
}
.small-note {
    color: #BFD7E8;
    font-size: 13px;
    line-height: 1.8;
}
</style>
""",
    unsafe_allow_html=True,
)

# ------------------------------------------------------------
# IMAGE HELPERS
# ------------------------------------------------------------

@st.cache_data(ttl=86400, show_spinner=False)
def load_image_from_url(url):
    response = requests.get(url, timeout=40)
    response.raise_for_status()
    image = Image.open(BytesIO(response.content)).convert("RGB")
    return image

def pil_to_data_url(img):
    buf = BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

# ------------------------------------------------------------
# MOON 2D MAP
# ------------------------------------------------------------

@st.cache_data(ttl=86400, show_spinner=False)
def get_global_moon_texture():
    return load_image_from_url(NASA_MOON_TEXTURE)

def build_2d_map_with_marker(lat, lon):
    img = get_global_moon_texture().copy().resize((1200, 600))
    draw = ImageDraw.Draw(img)

    x = int((lon + 180) / 360 * img.width)
    y = int((90 - lat) / 180 * img.height)

    r = 10
    draw.ellipse((x-r, y-r, x+r, y+r), outline=COLORS["ice"], width=4)
    draw.ellipse((x-4, y-4, x+4, y+4), fill="white")

    return img

# ------------------------------------------------------------
# 3D MOON PICKER COMPONENT
# ------------------------------------------------------------

HAS_V2 = hasattr(st.components, "v2") and hasattr(st.components.v2, "component")

if HAS_V2:
    MOON_3D_HTML = """
    <div class="moon3d-root">
      <div class="moon3d-stage"></div>
      <div class="moon3d-hint"></div>
    </div>
    """

    MOON_3D_CSS = """
    .moon3d-root {
      width: 100%;
      border: 1px solid #375873;
      border-radius: 16px;
      overflow: hidden;
      background: #050B16;
      position: relative;
    }
    .moon3d-stage {
      width: 100%;
      height: 540px;
      background: #050B16;
    }
    .moon3d-hint {
      position: absolute;
      left: 14px;
      bottom: 14px;
      background: rgba(8,21,34,.88);
      border: 1px solid #375873;
      border-radius: 10px;
      color: #DCECF7;
      padding: 10px 12px;
      font: 13px Arial;
      z-index: 4;
    }
    """

    MOON_3D_JS = """
    export default function(component) {
      const { data, parentElement, setTriggerValue } = component;

      const stage = parentElement.querySelector(".moon3d-stage");
      const hint = parentElement.querySelector(".moon3d-hint");
      stage.replaceChildren();

      hint.textContent = data.ar
        ? "اسحب لتدوير القمر واضغط لاختيار الموقع"
        : "Drag to rotate the Moon and click to choose a location";

      let disposed = false;
      let cleanup = () => {};

      (async () => {
        try {
          const THREE = await import("https://esm.sh/three@0.160.0");
          const addon = await import("https://esm.sh/three@0.160.0/examples/jsm/controls/OrbitControls.js");

          if (disposed) return;

          const scene = new THREE.Scene();
          scene.background = new THREE.Color(0x050B16);

          const camera = new THREE.PerspectiveCamera(44, 1, 0.1, 100);
          camera.position.set(0, 0, 4.9);

          const renderer = new THREE.WebGLRenderer({ antialias: true });
          renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
          stage.appendChild(renderer.domElement);

          const texture = new THREE.TextureLoader().load(data.texture);
          texture.colorSpace = THREE.SRGBColorSpace;

          const moon = new THREE.Mesh(
            new THREE.SphereGeometry(1.65, 96, 64),
            new THREE.MeshStandardMaterial({ map: texture, roughness: 1.0 })
          );
          scene.add(moon);

          scene.add(new THREE.AmbientLight(0xffffff, 1.5));
          const light = new THREE.DirectionalLight(0xffffff, 2.0);
          light.position.set(4, 3, 6);
          scene.add(light);

          const controls = new addon.OrbitControls(camera, renderer.domElement);
          controls.enableDamping = true;
          controls.enablePan = false;
          controls.minDistance = 2.1;
          controls.maxDistance = 8;

          const marker = new THREE.Mesh(
            new THREE.SphereGeometry(0.05, 16, 16),
            new THREE.MeshBasicMaterial({ color: 0x76C5F5 })
          );
          scene.add(marker);

          function setMarker(lat, lon) {
            const u = (lon + 180) / 360;
            const phi = u * Math.PI * 2;
            const a = lat * Math.PI / 180;
            marker.position.set(
              -1.7 * Math.cos(phi) * Math.cos(a),
               1.7 * Math.sin(a),
               1.7 * Math.sin(phi) * Math.cos(a)
            );
          }

          setMarker(data.lat, data.lon);

          const raycaster = new THREE.Raycaster();
          const mouse = new THREE.Vector2();
          let down = null;

          function onDown(e) {
            down = { x: e.clientX, y: e.clientY };
          }

          function onUp(e) {
            if (!down) return;
            const dist = Math.hypot(e.clientX - down.x, e.clientY - down.y);
            down = null;
            if (dist > 6) return;

            const rect = renderer.domElement.getBoundingClientRect();
            mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
            mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

            raycaster.setFromCamera(mouse, camera);
            const hits = raycaster.intersectObject(moon);

            if (!hits.length || !hits[0].uv) return;

            const uv = hits[0].uv;
            const lon = uv.x * 360 - 180;
            const lat = uv.y * 180 - 90;

            setMarker(lat, lon);

            setTriggerValue("picked", {
              lat: Number(lat.toFixed(5)),
              lon: Number(lon.toFixed(5)),
              pick_id: Date.now() + Math.random()
            });
          }

          renderer.domElement.addEventListener("pointerdown", onDown);
          renderer.domElement.addEventListener("pointerup", onUp);

          function resize() {
            const w = stage.clientWidth || 900;
            const h = 540;
            renderer.setSize(w, h);
            camera.aspect = w / h;
            camera.updateProjectionMatrix();
          }

          const observer = new ResizeObserver(resize);
          observer.observe(stage);
          resize();

          let frame = null;
          function animate() {
            if (disposed) return;
            frame = requestAnimationFrame(animate);
            controls.update();
            renderer.render(scene, camera);
          }
          animate();

          cleanup = () => {
            observer.disconnect();
            if (frame) cancelAnimationFrame(frame);
            controls.dispose();
            renderer.dispose();
          };
        } catch (err) {
          hint.textContent = "3D Error: " + String(err);
        }
      })();

      return () => {
        disposed = true;
        cleanup();
        stage.replaceChildren();
      };
    }
    """

    MOON_3D = st.components.v2.component(
        "ofoq_moon_3d_v8",
        html=MOON_3D_HTML,
        css=MOON_3D_CSS,
        js=MOON_3D_JS,
    )
else:
    MOON_3D = None

# ------------------------------------------------------------
# LOCAL SURFACE IMAGE FOR LANDING SCAN
# ------------------------------------------------------------

def build_local_surface_image(lat, lon, span_deg=8):
    """
    Create a realistic top-down local patch from NASA's global moon texture.
    This is visual context only.
    """
    global_img = get_global_moon_texture()
    W, H = global_img.size

    cx = (lon + 180) / 360 * W
    cy = (90 - lat) / 180 * H

    crop_w = max(120, int(W * span_deg / 360))
    crop_h = max(120, int(H * span_deg / 180))

    left = int(max(0, min(W - crop_w, cx - crop_w / 2)))
    top = int(max(0, min(H - crop_h, cy - crop_h / 2)))
    right = left + crop_w
    bottom = top + crop_h

    patch = global_img.crop((left, top, right, bottom)).resize((900, 900), Image.Resampling.LANCZOS)

    # Visual enhancement for more "camera-like" feeling.
    patch = ImageEnhance.Contrast(patch).enhance(1.2)
    patch = ImageEnhance.Sharpness(patch).enhance(1.4)
    patch = ImageEnhance.Color(patch).enhance(0.85)

    return patch

# ------------------------------------------------------------
# NASA SLOPE WINDOW
# ------------------------------------------------------------

@st.cache_data(ttl=3600, show_spinner=False)
def get_slope_window(lat, lon):
    if lat > -80:
        raise ValueError("Polar slope data used here covers 80°S to 90°S.")

    with rasterio.Env(
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        GDAL_HTTP_TIMEOUT="20",
        GDAL_HTTP_MAX_RETRY="1",
    ):
        with rasterio.open("/vsicurl/" + NASA_SLOPE_COG) as src:
            transformer = Transformer.from_crs(
                MOON_GEO_CRS, src.crs, always_xy=True
            )

            x, y = transformer.transform(lon, lat)
            row, col = src.index(x, y)

            half = 32
            if not (half <= row < src.height - half and half <= col < src.width - half):
                raise ValueError("Selected point is outside the available raster.")

            window = Window(col - half, row - half, 64, 64)

            arr = src.read(1, window=window, masked=True)
            slope = np.ma.array(arr, dtype=float).filled(np.nan)

            if src.nodata is not None:
                slope[slope == src.nodata] = np.nan

            resolution = max(abs(src.transform.a), abs(src.transform.e))
            return slope, resolution

# ------------------------------------------------------------
# CELL SCORING
# ------------------------------------------------------------

def cell_id(r, c):
    return f"{chr(65 + r)}{c + 1}"

def slope_to_score(slope_value):
    """
    Convert slope (degrees) to a landing suitability score from 0 to 100.
    Prototype rule:
    0 deg slope -> 100
    20 deg slope -> 0
    """
    score = 100 - (slope_value / 20.0) * 100
    return int(round(max(0, min(100, score))))

def score_to_status(score):
    if score >= 75:
        return "green"
    elif score >= 50:
        return "yellow"
    else:
        return "red"

def reason_text(status, lang_ar=True):
    if lang_ar:
        if status == "green":
            return "سطح أكثر استواءً وميل منخفض"
        if status == "yellow":
            return "منطقة متوسطة وتحتاج حذرًا"
        if status == "red":
            return "ميل أعلى أو تضاريس أصعب"
        return "لا توجد بيانات كافية"
    else:
        if status == "green":
            return "Flatter terrain with lower slope"
        if status == "yellow":
            return "Moderate area and needs caution"
        if status == "red":
            return "Higher slope or rougher terrain"
        return "Insufficient data"

def build_scan_cells(slope=None):
    cells = []

    for r in range(8):
        for c in range(8):
            entry = {
                "id": cell_id(r, c),
                "row": r,
                "col": c,
                "score": None,
                "status": "gray",
                "slope_p90": None,
                "coverage": 0.0,
            }

            if slope is not None:
                block = slope[r*8:(r+1)*8, c*8:(c+1)*8]
                valid = block[np.isfinite(block)]
                coverage = len(valid) / block.size
                entry["coverage"] = round(coverage * 100, 1)

                if coverage >= 0.75:
                    p90 = float(np.percentile(valid, 90))
                    score = slope_to_score(p90)

                    entry["slope_p90"] = round(p90, 2)
                    entry["score"] = score
                    entry["status"] = score_to_status(score)

            cells.append(entry)

    return cells

def best_cells(cells, n=5):
    valid = [c for c in cells if c["score"] is not None]
    valid = sorted(valid, key=lambda x: x["score"], reverse=True)
    return valid[:n]

# ------------------------------------------------------------
# UNIFIED LANDING SCAN HTML
# ------------------------------------------------------------

def render_landing_scan(surface_img, cells, lang_ar=True):
    image_url = pil_to_data_url(surface_img)
    cell_json = json.dumps(cells, ensure_ascii=False)

    title_text = "OFOQ / LANDING SCAN" if not lang_ar else "أُفُق / تحليل الهبوط"
    default_details = (
        "اضغط على أي خلية لمعرفة سبب التقييم."
        if lang_ar else
        "Click any cell to see why it received this score."
    )

    html_code = f"""
    <div id="ofoq-scan-root">
      <div class="scan-wrapper">
        <div class="scan-badge">{title_text}</div>
        <div class="scan-image" id="scan-image"></div>
        <div class="scan-grid" id="scan-grid"></div>
        <div class="scan-beam"></div>
        <div class="scan-details" id="scan-details">{default_details}</div>
      </div>
    </div>

    <style>
      #ofoq-scan-root * {{
        box-sizing: border-box;
        font-family: Arial, sans-serif;
      }}
      .scan-wrapper {{
        position: relative;
        width: 100%;
        max-width: 900px;
        height: 900px;
        border-radius: 18px;
        overflow: hidden;
        border: 1px solid #375873;
        background: #050B16;
        box-shadow: 0 18px 45px rgba(0,0,0,.30);
      }}
      .scan-image {{
        position: absolute;
        inset: 0;
        background-image:
          linear-gradient(to bottom, rgba(5,11,22,.18), rgba(5,11,22,.06)),
          url('{image_url}');
        background-size: cover;
        background-position: center center;
        filter: contrast(1.08) brightness(.96);
      }}
      .scan-grid {{
        position: absolute;
        inset: 0;
        display: grid;
        grid-template-columns: repeat(8, 1fr);
        grid-template-rows: repeat(8, 1fr);
        z-index: 3;
      }}
      .scan-cell {{
        border: 1px solid rgba(220,236,247,.5);
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        backdrop-filter: blur(1px);
        cursor: pointer;
        font-weight: 700;
        text-align: center;
        padding: 4px;
        line-height: 1.2;
      }}
      .scan-cell .id {{
        font-size: 13px;
        color: #ffffff;
        text-shadow: 0 1px 2px rgba(0,0,0,.7);
      }}
      .scan-cell .score {{
        margin-top: 4px;
        font-size: 18px;
        color: #ffffff;
        text-shadow: 0 1px 2px rgba(0,0,0,.7);
      }}
      .scan-cell.green {{
        background: rgba(53,183,122,.42);
      }}
      .scan-cell.yellow {{
        background: rgba(227,184,78,.45);
      }}
      .scan-cell.red {{
        background: rgba(217,104,104,.45);
      }}
      .scan-cell.gray {{
        background: rgba(109,122,138,.32);
      }}
      .scan-cell:hover {{
        outline: 2px solid #DCECF7;
        z-index: 5;
      }}
      .scan-badge {{
        position: absolute;
        top: 14px;
        left: 14px;
        z-index: 5;
        background: rgba(8,21,34,.88);
        color: #DCECF7;
        border: 1px solid #375873;
        border-radius: 10px;
        padding: 10px 14px;
        font-size: 13px;
        font-weight: 700;
      }}
      .scan-details {{
        position: absolute;
        right: 14px;
        bottom: 14px;
        z-index: 5;
        width: min(340px, 44%);
        background: rgba(8,21,34,.88);
        color: #DCECF7;
        border: 1px solid #375873;
        border-radius: 12px;
        padding: 14px 15px;
        font-size: 13px;
        line-height: 1.7;
      }}
      .scan-beam {{
        position: absolute;
        left: 0;
        right: 0;
        height: 3px;
        background: rgba(118,197,245,.95);
        box-shadow: 0 0 18px rgba(118,197,245,.9);
        animation: scanmove 4.2s linear infinite;
        z-index: 4;
      }}
      @keyframes scanmove {{
        from {{ top: 0%; }}
        to {{ top: 100%; }}
      }}
    </style>

    <script>
      const cells = {cell_json};
      const grid = document.getElementById("scan-grid");
      const details = document.getElementById("scan-details");
      const langAr = {str(lang_ar).lower()};

      function reason(status) {{
        if (langAr) {{
          if (status === "green") return "سطح أكثر استواءً وميل منخفض";
          if (status === "yellow") return "منطقة متوسطة وتحتاج حذرًا";
          if (status === "red") return "ميل أعلى أو تضاريس أصعب";
          return "لا توجد بيانات كافية";
        }} else {{
          if (status === "green") return "Flatter terrain with lower slope";
          if (status === "yellow") return "Moderate area and needs caution";
          if (status === "red") return "Higher slope or rougher terrain";
          return "Insufficient data";
        }}
      }}

      cells.forEach(cell => {{
        const el = document.createElement("div");
        el.className = "scan-cell " + cell.status;

        const scoreText = cell.score === null ? "--" : String(cell.score);

        el.innerHTML = `
          <div class="id">${{cell.id}}</div>
          <div class="score">${{scoreText}}</div>
        `;

        el.onclick = () => {{
          const slopeText = cell.slope_p90 === null ? "--" : cell.slope_p90 + "°";
          const coverageText = cell.coverage + "%";
          const statusText = cell.status.toUpperCase();

          details.innerHTML = langAr
            ? `
              <b>الخلية: ${{cell.id}}</b><br>
              التقييم: <b>${{scoreText}}</b><br>
              الميل المرجعي (P90): <b>${{slopeText}}</b><br>
              نسبة البيانات الصالحة: <b>${{coverageText}}</b><br>
              السبب: <b>${{reason(cell.status)}}</b>
            `
            : `
              <b>Cell: ${{cell.id}}</b><br>
              Score: <b>${{scoreText}}</b><br>
              Reference slope (P90): <b>${{slopeText}}</b><br>
              Valid data coverage: <b>${{coverageText}}</b><br>
              Reason: <b>${{reason(cell.status)}}</b>
            `;
        }};

        grid.appendChild(el);
      }});
    </script>
    """

    components.html(html_code, height=920, scrolling=False)

# ------------------------------------------------------------
# HORIZONS HELPERS
# ------------------------------------------------------------

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_horizons(body_code, lat, lon, start_text, hours):
    start = datetime.strptime(start_text, "%Y-%m-%d %H:%M")
    end = start + timedelta(hours=hours)

    params = {
        "format": "json",
        "COMMAND": f"'{body_code}'",
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
        "APPARENT": "'AIRLESS'",
    }

    response = requests.get(HORIZONS_API, params=params, timeout=60)
    response.raise_for_status()
    text = response.json()["result"]

    if "$$SOE" not in text or "$$EOE" not in text:
        raise ValueError(text[:400])

    block = text.split("$$SOE")[1].split("$$EOE")[0]
    rows = []

    for line in block.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 5:
            continue

        try:
            rows.append(
                {
                    "time": pd.to_datetime(parts[0], format="%Y-%b-%d %H:%M"),
                    "elevation": float(parts[4]),
                }
            )
        except ValueError:
            continue

    if not rows:
        raise ValueError("No valid Horizons records found.")

    return pd.DataFrame(rows)

def get_visibility(lat, lon, start_dt, hours):
    start_text = start_dt.strftime("%Y-%m-%d %H:%M")

    sun = fetch_horizons("10", lat, lon, start_text, hours)
    earth = fetch_horizons("399", lat, lon, start_text, hours)

    df = sun.merge(earth, on="time", suffixes=("_sun", "_earth")).sort_values("time")
    df = df.iloc[:-1].copy()

    df["Sun"] = df["elevation_sun"] > 0
    df["Earth"] = df["elevation_earth"] > 0
    df["Both"] = df["Sun"] & df["Earth"]

    return df

def visibility_metrics(df):
    return {
        "Sun": int(df["Sun"].sum()),
        "Earth": int(df["Earth"].sum()),
        "Both": int(df["Both"].sum()),
    }

# ------------------------------------------------------------
# SIDEBAR
# ------------------------------------------------------------

with st.sidebar:
    st.markdown('<div class="sidebar-title">أُفُق | OFOQ</div>', unsafe_allow_html=True)
    st.markdown('<div class="sidebar-sub">BEYOND THE HORIZON</div>', unsafe_allow_html=True)

    st.selectbox(
        "Language",
        ["العربية", "English"],
        key="lang",
        label_visibility="collapsed",
    )

    st.markdown('<div class="nav-hint">MISSION NAVIGATION</div>', unsafe_allow_html=True)

    nav_items = [
        ("explore", "◉ " + tr("explore")),
        ("scan", "▦ " + tr("scan")),
        ("sun", "☼ " + tr("sun")),
        ("compare", "◇ " + tr("compare")),
    ]

    for key, label in nav_items:
        if st.button(
            label,
            key=f"nav_{key}",
            type="primary" if st.session_state.page == key else "secondary",
            use_container_width=True,
        ):
            st.session_state.page = key
            st.rerun()

    st.divider()

    st.write(f"**{tr('selected_site')}**")
    st.write(f"{tr('lat')}: **{st.session_state.lat:.5f}°**")
    st.write(f"{tr('lon')}: **{st.session_state.lon:.5f}°**")

    if st.button(tr("save_backup"), use_container_width=True):
        st.session_state.backup_site = (st.session_state.lat, st.session_state.lon)
        st.success("✓")

# ------------------------------------------------------------
# HERO
# ------------------------------------------------------------

st.markdown(
    f"""
    <div class="hero" dir="{'rtl' if is_ar() else 'ltr'}">
      <div class="eyebrow">NASA SPACE APPS CHALLENGE 2026</div>
      <h1>أُفُق | OFOQ</h1>
      <div class="eyebrow">BEYOND THE HORIZON, TOWARD THE MOON.</div>
      <p class="sub">
        {"استكشف القمر، اختر موقعًا، وحلل ظروف المهمة بصورة واضحة وسهلة."
         if is_ar() else
         "Explore the Moon, choose a site, and analyze mission conditions clearly and simply."}
      </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ------------------------------------------------------------
# PAGE 1 — EXPLORE
# ------------------------------------------------------------

if st.session_state.page == "explore":
    st.header(tr("explore"))
    st.write(tr("choose_site"))
    st.caption(tr("explore_note"))

    a, b = st.columns(2)

    with a:
        if st.button(
            "2D MAP",
            type="primary" if st.session_state.view_mode == "2D" else "secondary",
            use_container_width=True,
        ):
            st.session_state.view_mode = "2D"
            st.rerun()

    with b:
        if st.button(
            "3D MOON",
            type="primary" if st.session_state.view_mode == "3D" else "secondary",
            use_container_width=True,
        ):
            st.session_state.view_mode = "3D"
            st.rerun()

    if st.session_state.view_mode == "2D":
        moon_map = build_2d_map_with_marker(st.session_state.lat, st.session_state.lon)
        click = streamlit_image_coordinates(moon_map, width=1200, key="moon_map_2d")

        if click is not None:
            x = click["x"]
            y = click["y"]

            lon = x / 1200 * 360 - 180
            lat = 90 - y / 600 * 180

            set_site(lat, lon)
            st.rerun()

    else:
        if MOON_3D is not None:
            texture_url = pil_to_data_url(get_global_moon_texture())
            result = MOON_3D(
                data={
                    "texture": texture_url,
                    "lat": st.session_state.lat,
                    "lon": st.session_state.lon,
                    "ar": is_ar(),
                },
                key="moon_3d_component",
                on_picked_change=lambda: None,
            )

            pick = getattr(result, "picked", None)
            if pick and pick.get("pick_id") != st.session_state.last_3d_pick_id:
                st.session_state.last_3d_pick_id = pick["pick_id"]
                set_site(pick["lat"], pick["lon"])
                st.rerun()
        else:
            st.warning(
                "3D selection is not available in this Streamlit version. Use 2D."
            )

    c1, c2 = st.columns(2)
    c1.metric(tr("lat"), f"{st.session_state.lat:.5f}°")
    c2.metric(tr("lon"), f"{st.session_state.lon:.5f}°")

# ------------------------------------------------------------
# PAGE 2 — LANDER CAMERA & LANDING SCAN
# ------------------------------------------------------------

elif st.session_state.page == "scan":
    st.header(tr("scan"))
    st.write(tr("scan_note"))

    current_signature = (st.session_state.lat, st.session_state.lon)

    if st.button(tr("start_scan"), type="primary"):
        try:
            with st.spinner("NASA LOLA"):
                slope, resolution = get_slope_window(*current_signature)
            cells = build_scan_cells(slope)
            st.session_state.scan_result = {
                "signature": current_signature,
                "cells": cells,
                "resolution": resolution,
                "ok": True,
            }
        except Exception as err:
            cells = build_scan_cells(None)
            st.session_state.scan_result = {
                "signature": current_signature,
                "cells": cells,
                "ok": False,
                "error": str(err),
            }

    scan = st.session_state.scan_result
    if scan and scan["signature"] == current_signature:
        cells = scan["cells"]
    else:
        cells = build_scan_cells(None)

    surface_img = build_local_surface_image(st.session_state.lat, st.session_state.lon)

    left, right = st.columns([3, 1], gap="large")

    with left:
        render_landing_scan(surface_img, cells, lang_ar=is_ar())

    with right:
        st.markdown(
            f"""
            <div class="legend-box">
              <h4 style="margin-top:0;">{tr("legend")}</h4>
              <div class="legend-row">
                <div class="legend-color" style="background:{COLORS['green']};"></div>
                <div>{tr("green")}</div>
              </div>
              <div class="legend-row">
                <div class="legend-color" style="background:{COLORS['yellow']};"></div>
                <div>{tr("yellow")}</div>
              </div>
              <div class="legend-row">
                <div class="legend-color" style="background:{COLORS['red']};"></div>
                <div>{tr("red")}</div>
              </div>
              <div class="legend-row" style="margin-bottom:0;">
                <div class="legend-color" style="background:{COLORS['gray']};"></div>
                <div>{tr("gray")}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("### " + tr("best_areas"))

        top_cells = best_cells(cells, n=5)
        if top_cells:
            for i, item in enumerate(top_cells, start=1):
                status_label = {
                    "green": tr("green"),
                    "yellow": tr("yellow"),
                    "red": tr("red"),
                    "gray": tr("gray"),
                }.get(item["status"], tr("gray"))

                reason = reason_text(item["status"], lang_ar=is_ar())

                st.markdown(
                    f"""
                    <div class="best-card">
                      <b>#{i} — {item['id']}</b><br>
                      {"التقييم" if is_ar() else "Score"}: <b>{item['score']}</b><br>
                      {"الميل P90" if is_ar() else "Slope P90"}: <b>{item['slope_p90']}°</b><br>
                      {"الحالة" if is_ar() else "Status"}: <b>{status_label}</b><br>
                      <span class="small-note">{reason}</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.info(tr("gray"))

    if scan and scan["signature"] == current_signature:
        if scan["ok"]:
            st.success(tr("scan_loaded"))
            st.caption(f"NASA LOLA slope raster — {scan['resolution']:.0f} m/pixel")
        else:
            st.warning(tr("scan_failed"))
            with st.expander("Technical details"):
                st.code(scan.get("error", ""))

    st.caption(
        "هذا العرض يستخدم صورة محلية من نسيج القمر الخاص بـ NASA لعرض المنطقة بصريًا، "
        "أما التقييمات اللونية والدرجات فمبنية على بيانات الميل حيثما تتوفر."
        if is_ar()
        else
        "This view uses a local patch from NASA's Moon texture for visual context, "
        "while the color classes and scores are based on slope data when available."
    )

# ------------------------------------------------------------
# PAGE 3 — SUN & COMMUNICATION
# ------------------------------------------------------------

elif st.session_state.page == "sun":
    st.header(tr("sun"))

    mission_date = st.date_input(tr("date"), value=date(2026, 11, 15))
    duration = st.slider(tr("duration"), 24, 96, 48, 12)

    signature = (st.session_state.lat, st.session_state.lon, mission_date, duration)

    if st.button(tr("run_visibility"), type="primary"):
        try:
            start_dt = datetime.combine(mission_date, datetime.min.time())
            with st.spinner("NASA Horizons"):
                df = get_visibility(st.session_state.lat, st.session_state.lon, start_dt, duration)
            st.session_state.visibility_result = (signature, df)
        except Exception as err:
            st.error(str(err))

    saved = st.session_state.visibility_result
    if saved and saved[0] == signature:
        df = saved[1]
        m = visibility_metrics(df)

        a, b, c = st.columns(3)
        a.metric(tr("sun_hours"), f"{m['Sun']} h")
        b.metric(tr("earth_hours"), f"{m['Earth']} h")
        c.metric(tr("both_hours"), f"{m['Both']} h")

        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=df["time"],
                y=df["elevation_sun"],
                name="Sun",
                line=dict(color="#DCECF7", width=3),
            )
        )
        fig.add_trace(
            go.Scatter(
                x=df["time"],
                y=df["elevation_earth"],
                name="Earth",
                line=dict(color="#76C5F5", width=3),
            )
        )
        fig.add_hline(y=0, line_dash="dash", line_color="#6D7A8A")
        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="#081522",
            plot_bgcolor="#081522",
            font=dict(color="#DCECF7"),
            height=420,
            xaxis_title="UTC",
            yaxis_title="Elevation (°)",
        )
        st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------------------------
# PAGE 4 — COMPARE
# ------------------------------------------------------------

elif st.session_state.page == "compare":
    st.header(tr("compare_title"))

    mission_date = st.date_input(tr("date"), value=date(2026, 11, 15), key="cmp_date")
    duration = st.slider(tr("duration"), 24, 96, 48, 12, key="cmp_duration")

    mode = st.radio(
        "Mode",
        ["delay", "site"],
        format_func=lambda x: tr("same_site") if x == "delay" else tr("other_site"),
        horizontal=True,
    )

    start_a = datetime.combine(mission_date, datetime.min.time())
    start_b = start_a

    lat_b = st.session_state.lat
    lon_b = st.session_state.lon

    if mode == "delay":
        delay = st.slider(tr("delay_hours"), 0, 168, 48, 24)
        start_b += timedelta(hours=delay)
    else:
        if st.session_state.backup_site is not None:
            lat_b, lon_b = st.session_state.backup_site
            st.info(f"{tr('lat')}: {lat_b:.5f}° | {tr('lon')}: {lon_b:.5f}°")
        else:
            st.warning(
                "احفظ أولًا موقعًا بديلًا من صفحة الاستكشاف."
                if is_ar() else
                "First save a backup site from the Explore page."
            )

    if st.button(
        tr("run_compare"),
        type="primary",
        disabled=(mode == "site" and st.session_state.backup_site is None),
    ):
        try:
            with st.spinner("NASA Horizons"):
                first = get_visibility(st.session_state.lat, st.session_state.lon, start_a, duration)
                second = get_visibility(lat_b, lon_b, start_b, duration)

            n1 = visibility_metrics(first)
            n2 = visibility_metrics(second)

            left, right = st.columns(2)

            with left:
                st.subheader(tr("original"))
                for k, v in n1.items():
                    st.metric(k, f"{v} h")

            with right:
                st.subheader(tr("alternative"))
                for k, v in n2.items():
                    st.metric(k, f"{v} h", delta=v - n1[k])

            fig = go.Figure()
            fig.add_trace(
                go.Bar(
                    x=list(n1.keys()),
                    y=list(n1.values()),
                    name=tr("original"),
                    marker_color="#6D7A8A",
                )
            )
            fig.add_trace(
                go.Bar(
                    x=list(n2.keys()),
                    y=list(n2.values()),
                    name=tr("alternative"),
                    marker_color="#76C5F5",
                )
            )
            fig.update_layout(
                barmode="group",
                template="plotly_dark",
                paper_bgcolor="#081522",
                plot_bgcolor="#081522",
                font=dict(color="#DCECF7"),
                height=360,
            )
            st.plotly_chart(fig, use_container_width=True)

        except Exception as err:
            st.error(str(err))

# ------------------------------------------------------------
# SOURCES
# ------------------------------------------------------------

st.divider()

with st.expander(tr("sources")):
    st.markdown(
        """
**NASA Moon texture (visual context)**  
https://svs.gsfc.nasa.gov/4720/

**NASA LOLA slope data**  
https://pgda.gsfc.nasa.gov/products/90

**NASA JPL Horizons**  
https://ssd-api.jpl.nasa.gov/doc/horizons.html

**Important limitations**
- The landing scan scores are a prototype suitability indicator.
- Scores are mainly derived from slope information.
- Score thresholds used in this prototype:
  - 75+ = Green
  - 50–74 = Yellow
  - below 50 = Red
- Gray means data were unavailable or insufficient.
- OFOQ does not certify a real lunar landing.
"""
    )

st.caption("TEAM OFOQ | NASA SPACE APPS CHALLENGE 2026")
