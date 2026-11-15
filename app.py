import base64
import html
from datetime import date, datetime, timedelta
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

# =========================================================
# CONFIG
# =========================================================

st.set_page_config(
    page_title="أُفُق | OFOQ",
    page_icon="🌙",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =========================================================
# CONSTANTS
# =========================================================

MOON_TEXTURE_URL = (
    "https://svs.gsfc.nasa.gov/vis/a000000/a004700/"
    "a004720/lroc_color_2k.jpg"
)

NASA_BASE = "https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/"
SLOPE_FILE = "LDSM_80S_80MPP_ADJ.TIF"
HEIGHT_FILE = "LDEM_80S_80MPP_ADJ.TIF"

HORIZONS_API = "https://ssd.jpl.nasa.gov/api/horizons.api"

LUNAR_GEO_CRS = CRS.from_proj4(
    "+proj=longlat +a=1737400 +b=1737400 +no_defs"
)

COLORS = {
    "space": "#050B16",
    "navy": "#10243A",
    "panel": "#0D1B2A",
    "ice": "#76C5F5",
    "silver": "#DCECF7",
    "green": "#35B77A",
    "yellow": "#E3B84E",
    "red": "#D96868",
    "gray": "#6D7A8A",
    "border": "#35536B",
}

# =========================================================
# SESSION
# =========================================================

DEFAULTS = {
    "language": "العربية",
    "page": "explore",
    "lat": -89.0,
    "lon": 0.0,
    "backup_site": None,
    "terrain_cache": None,
    "mission_cache": None,
}

for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# =========================================================
# LANGUAGE
# =========================================================

TXT = {
    "explore": ("استكشف واختر", "Explore & Select"),
    "views": ("رؤى الهبوط", "Landing Views"),
    "sunearth": ("الشمس والأرض", "Sun & Earth"),
    "compare": ("خطة بديلة", "Plan B"),
    "choose_site": (
        "اضغط على سطح القمر لتحديد موقعك",
        "Click the Moon to choose your site",
    ),
    "selected_site": ("الموقع المختار", "Selected site"),
    "lat": ("خط العرض", "Latitude"),
    "lon": ("خط الطول", "Longitude"),
    "save_backup": ("حفظ كموقع بديل", "Save as backup site"),
    "hero_desc": (
        "أداة تساعد على اختيار مواقع هبوط قمرية بشكل أوضح وأسهل.",
        "A clearer and easier tool for choosing lunar landing sites.",
    ),
    "side_view": ("منظر المركبة", "Lander View"),
    "camera_view": ("منظر الكاميرا", "Camera View"),
    "camera_desc": (
        "منظر علوي لسطح القمر مع 9 مناطق فقط. كل منطقة تعرض النسبة مباشرة.",
        "A top-down lunar surface view with only 9 regions. Each region shows its percentage directly.",
    ),
    "best_spot": ("أفضل موقع للهبوط", "Best landing spot"),
    "legend": ("دليل الألوان", "Color legend"),
    "legend_green": ("أخضر: 75% – 100%", "Green: 75% – 100%"),
    "legend_yellow": ("أصفر: 50% – 74%", "Yellow: 50% – 74%"),
    "legend_red": ("أحمر: 0% – 49%", "Red: 0% – 49%"),
    "legend_gray": ("رمادي: لا توجد بيانات", "Gray: no data"),
    "rank_note": (
        "يعتمد هذا المؤشر على انحدار السطح فقط.",
        "This index is based on surface slope only.",
    ),
    "real_note": (
        "هذا عرض بصري مبني على بيانات NASA، وليس صورة حقيقية من مركبة هبوط.",
        "This is a visual view built from NASA data, not real lander footage.",
    ),
    "date": ("تاريخ المهمة (UTC)", "Mission date (UTC)"),
    "hours": ("مدة المهمة بالساعات", "Mission duration (hours)"),
    "analyze": ("احسب ظروف المهمة", "Analyze mission"),
    "sun_vis": ("ساعات ظهور الشمس", "Sun visible hours"),
    "earth_vis": ("ساعات ظهور الأرض", "Earth visible hours"),
    "both_vis": ("ظهورهما معًا", "Both visible hours"),
    "same_site_delay": ("نفس الموقع، وقت مختلف", "Same site, different time"),
    "different_site": ("موقع مختلف، نفس الوقت", "Different site, same time"),
    "delay_hours": ("ساعات التأخير", "Delay hours"),
    "run_compare": ("قارن", "Compare"),
    "original": ("الخطة الأصلية", "Original plan"),
    "alternative": ("الخطة البديلة", "Alternative plan"),
    "sources": ("المصادر وحدود الدقة", "Sources & accuracy"),
}

def tr(key):
    ar, en = TXT.get(key, (key, key))
    return ar if st.session_state.language == "العربية" else en

def is_ar():
    return st.session_state.language == "العربية"

def dir_attr():
    return "rtl" if is_ar() else "ltr"

# =========================================================
# STYLE
# =========================================================

st.markdown(
    """
<style>
.stApp {
    background:
      radial-gradient(circle at 82% 0%, #17324B 0%, #10243A 32%, #050B16 78%) !important;
    color: #DCECF7;
}
[data-testid="stHeader"] { background: transparent !important; }
[data-testid="stSidebar"] {
    background: #081522 !important;
    border-right: 1px solid #35536B;
}
.block-container {
    max-width: 1560px;
    padding-top: 1rem;
    padding-bottom: 3rem;
}
h1,h2,h3,h4,p,label,div,span { color: #DCECF7 !important; }
.stButton button {
    min-height: 50px;
    border-radius: 14px !important;
    background: #10243A !important;
    border: 1px solid #35536B !important;
    color: #DCECF7 !important;
    font-weight: 700 !important;
}
.stButton button:hover {
    background: #17324B !important;
    border-color: #76C5F5 !important;
}
.stButton button[kind="primary"] {
    background: #76C5F5 !important;
    color: #050B16 !important;
    border-color: #76C5F5 !important;
}
[data-testid="stMetric"] {
    background: #10243A;
    border: 1px solid #35536B;
    border-radius: 16px;
    padding: 16px;
}
.ofoq-hero {
    border: 1px solid #35536B;
    border-radius: 24px;
    padding: 28px 32px;
    margin-bottom: 20px;
    background:
      radial-gradient(circle at 80% 40%, rgba(118,197,245,.16), transparent 26%),
      linear-gradient(120deg, #050B16, #10243A);
    box-shadow: 0 18px 45px rgba(0,0,0,.35);
}
.ofoq-eyebrow {
    color: #76C5F5 !important;
    font-size: 12px;
    letter-spacing: 2px;
    font-weight: 700;
}
.ofoq-title {
    font-size: clamp(38px, 5vw, 62px);
    font-weight: 850;
    margin: 6px 0;
}
.ofoq-card {
    border: 1px solid #35536B;
    border-radius: 16px;
    background: #10243A;
    padding: 15px;
}
.ofoq-muted {
    color: #BFD7E8 !important;
    font-size: 13px;
    line-height: 1.7;
}
.small-caption {
    color: #BFD7E8 !important;
    font-size: 12px;
    line-height: 1.6;
}
</style>
""",
    unsafe_allow_html=True,
)

# =========================================================
# IMAGE HELPERS
# =========================================================

@st.cache_data(ttl=86400, show_spinner=False)
def load_global_moon_texture():
    response = requests.get(MOON_TEXTURE_URL, timeout=40)
    response.raise_for_status()
    return Image.open(BytesIO(response.content)).convert("RGB")

def pil_to_data_url(img):
    buf = BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

def set_site(lat, lon):
    lat = max(-90.0, min(90.0, float(lat)))
    lon = ((float(lon) + 180.0) % 360.0) - 180.0
    st.session_state.lat = round(lat, 5)
    st.session_state.lon = round(lon, 5)
    st.session_state.terrain_cache = None
    st.session_state.mission_cache = None

# =========================================================
# EXPLORE MAP
# =========================================================

def build_clickable_moon(lat, lon):
    img = load_global_moon_texture().copy().resize((1200, 600))
    draw = ImageDraw.Draw(img)

    x = int((lon + 180.0) / 360.0 * img.width)
    y = int((90.0 - lat) / 180.0 * img.height)

    r = 12
    draw.ellipse((x-r, y-r, x+r, y+r), outline=COLORS["ice"], width=4)
    draw.ellipse((x-4, y-4, x+4, y+4), fill="white")

    return img

def render_decorative_3d_moon():
    texture = pil_to_data_url(load_global_moon_texture())
    html_code = f"""
    <div style="
        position:relative;
        width:100%;
        height:420px;
        display:flex;
        align-items:center;
        justify-content:center;
        border:1px solid #35536B;
        border-radius:18px;
        overflow:hidden;
        background: radial-gradient(circle at 50% 50%, #10243A, #050B16);
    ">
      <div style="
        width:320px;height:320px;border-radius:50%;
        background-image:url('{texture}');
        background-size:cover;
        background-position:center;
        box-shadow:
          inset -40px -25px 70px rgba(0,0,0,.55),
          0 0 65px rgba(118,197,245,.18);
      "></div>
    </div>
    """
    components.html(html_code, height=430, scrolling=False)

# =========================================================
# NASA DATA
# =========================================================

def read_nasa_window(filename, lat, lon, size=48):
    url = NASA_BASE + filename

    with rasterio.Env(
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        GDAL_HTTP_TIMEOUT="18",
        GDAL_HTTP_MAX_RETRY="1",
        CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".TIF",
    ):
        with rasterio.open("/vsicurl/" + url) as src:
            transformer = Transformer.from_crs(
                LUNAR_GEO_CRS, src.crs, always_xy=True
            )
            x, y = transformer.transform(lon, lat)
            row, col = src.index(x, y)
            half = size // 2

            if not (
                half <= row < src.height - half
                and half <= col < src.width - half
            ):
                raise ValueError("Selected site outside available NASA raster")

            window = Window(col-half, row-half, size, size)
            arr = src.read(1, window=window, masked=True)
            values = np.ma.array(arr, dtype=float).filled(np.nan)

            if src.nodata is not None:
                values[np.isclose(values, src.nodata)] = np.nan

            pixel_size = max(abs(src.transform.a), abs(src.transform.e))
            return values, pixel_size

@st.cache_data(ttl=3600, show_spinner=False)
def get_site_terrain(lat, lon):
    if lat > -80:
        raise ValueError("This polar dataset covers 80°S to 90°S.")

    slope, pixel = read_nasa_window(SLOPE_FILE, lat, lon, size=48)
    height, _ = read_nasa_window(HEIGHT_FILE, lat, lon, size=48)

    if not np.isfinite(slope).any():
        raise ValueError("No valid slope measurements")
    if not np.isfinite(height).any():
        raise ValueError("No valid elevation measurements")

    return slope, height, pixel

# =========================================================
# TERRAIN VISUALS
# =========================================================

def create_top_terrain_image(height):
    z = np.asarray(height, dtype=float)
    finite = np.isfinite(z)
    if not finite.any():
        raise ValueError("No valid elevation")

    z = np.where(finite, z, np.nanmedian(z))
    dy, dx = np.gradient(z)

    normal_x = -dx
    normal_y = -dy
    normal_z = np.ones_like(z)

    norm = np.sqrt(normal_x**2 + normal_y**2 + normal_z**2)
    nx = normal_x / norm
    ny = normal_y / norm
    nz = normal_z / norm

    light = np.array([-0.7, -0.45, 0.56], dtype=float)
    light = light / np.linalg.norm(light)

    shade = nx * light[0] + ny * light[1] + nz * light[2]
    shade = np.clip(shade, 0, 1)

    gray = np.clip(50 + shade * 195, 0, 255).astype(np.uint8)
    rgb = np.stack([gray, gray, np.clip(gray * 1.02, 0, 255)], axis=-1).astype(np.uint8)

    img = Image.fromarray(rgb, "RGB").resize((1100, 1100), Image.Resampling.BICUBIC)
    img = ImageEnhance.Contrast(img).enhance(1.18)
    return img

def create_side_terrain_image(height):
    z = np.asarray(height, dtype=float)
    finite = np.isfinite(z)
    if not finite.any():
        raise ValueError("No valid elevation")

    z = np.where(finite, z, np.nanmedian(z))
    profile = np.nanmean(z[20:28, :], axis=0)

    profile = profile - np.nanmin(profile)
    if np.nanmax(profile) > 0:
        profile = profile / np.nanmax(profile)

    W, H = 1200, 520
    img = Image.new("RGB", (W, H), (5, 11, 22))
    draw = ImageDraw.Draw(img)

    # soft stars
    for i in range(55):
        x = int((i * 73) % W)
        y = int((i * 29) % 180)
        draw.ellipse((x, y, x+2, y+2), fill=(220, 236, 247))

    # terrain polygon
    points = []
    base_y = int(H * 0.80)
    amp = int(H * 0.20)

    for i, val in enumerate(profile):
        x = int(i / (len(profile)-1) * (W-1))
        y = base_y - int(val * amp)
        points.append((x, y))

    polygon = [(0, H), (0, points[0][1])] + points + [(W-1, H)]
    draw.polygon(polygon, fill=(166, 172, 178))

    # surface bright line
    draw.line(points, fill=(230, 236, 240), width=3)

    # subtle foreground shading
    overlay = Image.new("RGBA", (W, H), (0,0,0,0))
    od = ImageDraw.Draw(overlay)
    od.rectangle((0, int(H*0.62), W, H), fill=(0,0,0,45))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    return img

def fallback_surface_image(lat, lon):
    global_img = load_global_moon_texture()
    W, H = global_img.size
    x = int((lon + 180) / 360 * W)
    y = int((90 - lat) / 180 * H)

    size = 180
    left = max(0, min(W - size, x - size//2))
    top = max(0, min(H - size, y - size//2))

    patch = global_img.crop((left, top, left+size, top+size))
    return patch.resize((1100, 1100), Image.Resampling.BICUBIC)

# =========================================================
# 3x3 SCORE GRID
# =========================================================

def slope_to_score(slope_deg):
    # 0° => 100, 5° => 75, 10° => 50, 20° => 0
    return int(round(max(0, min(100, 100 - 5 * slope_deg))))

def score_to_class(score):
    if score is None:
        return "gray"
    if score >= 75:
        return "green"
    if score >= 50:
        return "yellow"
    return "red"

def position_name(r, c):
    names_ar = [
        ["أعلى اليسار", "أعلى الوسط", "أعلى اليمين"],
        ["وسط اليسار", "المنتصف", "وسط اليمين"],
        ["أسفل اليسار", "أسفل الوسط", "أسفل اليمين"],
    ]
    names_en = [
        ["Top left", "Top center", "Top right"],
        ["Middle left", "Center", "Middle right"],
        ["Bottom left", "Bottom center", "Bottom right"],
    ]
    return names_ar[r][c] if is_ar() else names_en[r][c]

def build_cells_3x3(slope):
    cells = []

    row_chunks = np.array_split(np.arange(slope.shape[0]), 3)
    col_chunks = np.array_split(np.arange(slope.shape[1]), 3)

    for r, rr in enumerate(row_chunks):
        for c, cc in enumerate(col_chunks):
            block = slope[np.ix_(rr, cc)]
            valid = block[np.isfinite(block)]
            coverage = len(valid) / block.size if block.size else 0.0

            item = {
                "row": r,
                "col": c,
                "score": None,
                "status": "gray",
                "slope": None,
                "coverage": round(coverage * 100, 1),
                "position": position_name(r, c),
            }

            if coverage >= 0.60 and len(valid) > 0:
                p90 = float(np.percentile(valid, 90))
                score = slope_to_score(p90)
                item["slope"] = round(p90, 2)
                item["score"] = score
                item["status"] = score_to_class(score)

            cells.append(item)

    return cells

def best_cell(cells):
    valid = [c for c in cells if c["score"] is not None]
    if not valid:
        return None
    return sorted(valid, key=lambda x: x["score"], reverse=True)[0]

# =========================================================
# VIEW RENDERERS
# =========================================================

def render_lander_view(side_img):
    img_url = pil_to_data_url(side_img)

    # simple inline lander SVG
    lander_svg = """
    <svg width="230" height="140" viewBox="0 0 230 140" xmlns="http://www.w3.org/2000/svg">
      <g>
        <ellipse cx="115" cy="55" rx="34" ry="22" fill="#DCECF7" stroke="#76C5F5" stroke-width="3"/>
        <rect x="101" y="37" width="28" height="20" rx="4" fill="#76C5F5"/>
        <line x1="88" y1="74" x2="62" y2="112" stroke="#DCECF7" stroke-width="4"/>
        <line x1="142" y1="74" x2="168" y2="112" stroke="#DCECF7" stroke-width="4"/>
        <line x1="96" y1="74" x2="86" y2="113" stroke="#DCECF7" stroke-width="4"/>
        <line x1="134" y1="74" x2="144" y2="113" stroke="#DCECF7" stroke-width="4"/>
        <line x1="48" y1="112" x2="77" y2="112" stroke="#DCECF7" stroke-width="5"/>
        <line x1="153" y1="112" x2="182" y2="112" stroke="#DCECF7" stroke-width="5"/>
      </g>
    </svg>
    """

    html_code = f"""
    <div style="
        position:relative;
        width:100%;
        height:760px;
        border:1px solid #35536B;
        border-radius:18px;
        overflow:hidden;
        background:linear-gradient(180deg,#050B16 0%, #081522 45%, #10243A 100%);
    ">
      <div style="
        position:absolute; inset:0;
        background-image:url('{img_url}');
        background-size:cover;
        background-position:center bottom;
        opacity:.95;
        top:180px;
      "></div>

      <div style="
        position:absolute; left:50%; top:55px; transform:translateX(-50%);
        filter:drop-shadow(0 0 18px rgba(118,197,245,.25));
      ">
        {lander_svg}
      </div>

      <div style="
        position:absolute; left:50%; top:170px; transform:translateX(-50%);
        width:2px; height:110px;
        background:linear-gradient(180deg, rgba(118,197,245,.9), rgba(118,197,245,0));
      "></div>

      <div style="
        position:absolute; left:16px; top:16px;
        background:rgba(5,11,22,.86);
        border:1px solid #76C5F5;
        border-radius:10px;
        padding:10px 14px;
        color:#DCECF7;
        font-size:13px;
        font-weight:700;
      ">
        {"أُفُق | منظر المركبة" if is_ar() else "OFOQ | Lander View"}
      </div>
    </div>
    """
    components.html(html_code, height=770, scrolling=False)

def render_camera_view(top_img, cells):
    img_url = pil_to_data_url(top_img)

    cells_html = []
    for cell in cells:
        value = "--" if cell["score"] is None else f"{cell['score']}%"
        cls = cell["status"]
        cells_html.append(
            f'<div class="scan-cell {cls}">{value}</div>'
        )

    html_code = f"""
    <div class="camera-root">
      <div class="camera-wrap">
        <div class="camera-bg"></div>
        <div class="camera-badge">
          {"أُفُق | كاميرا الهبوط" if is_ar() else "OFOQ | Landing Camera"}
        </div>
        <div class="camera-grid">
          {''.join(cells_html)}
        </div>
      </div>
    </div>

    <style>
      .camera-root * {{
        box-sizing:border-box;
        font-family:Arial,sans-serif;
      }}
      .camera-wrap {{
        position:relative;
        width:100%;
        height:840px;
        border:1px solid #35536B;
        border-radius:18px;
        overflow:hidden;
        background:#050B16;
      }}
      .camera-bg {{
        position:absolute;
        inset:0;
        background-image:
          linear-gradient(to bottom, rgba(0,0,0,.12), rgba(0,0,0,.06)),
          url('{img_url}');
        background-size:cover;
        background-position:center center;
      }}
      .camera-badge {{
        position:absolute;
        left:16px;
        top:16px;
        z-index:5;
        background:rgba(5,11,22,.86);
        border:1px solid #76C5F5;
        border-radius:10px;
        padding:10px 14px;
        color:#DCECF7;
        font-size:13px;
        font-weight:700;
      }}
      .camera-grid {{
        position:absolute;
        inset:10%;
        z-index:3;
        display:grid;
        grid-template-columns:repeat(3, 1fr);
        grid-template-rows:repeat(3, 1fr);
        gap:8px;
      }}
      .scan-cell {{
        display:flex;
        align-items:center;
        justify-content:center;
        border:1px solid rgba(255,255,255,.60);
        border-radius:10px;
        font-size:clamp(22px, 3vw, 36px);
        font-weight:800;
        color:white;
        text-shadow:0 2px 5px rgba(0,0,0,.8);
        backdrop-filter:blur(0.5px);
      }}
      .scan-cell.green {{
        background:rgba(53,183,122,.28);
      }}
      .scan-cell.yellow {{
        background:rgba(227,184,78,.28);
      }}
      .scan-cell.red {{
        background:rgba(217,104,104,.30);
      }}
      .scan-cell.gray {{
        background:rgba(109,122,138,.28);
      }}
    </style>
    """
    components.html(html_code, height=850, scrolling=False)

# =========================================================
# HORIZONS
# =========================================================

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_horizons(body_code, lat, lon, start_text, hours):
    start_dt = datetime.strptime(start_text, "%Y-%m-%d %H:%M")
    end_dt = start_dt + timedelta(hours=hours)

    params = {
        "format": "json",
        "COMMAND": f"'{body_code}'",
        "OBJ_DATA": "'NO'",
        "MAKE_EPHEM": "'YES'",
        "EPHEM_TYPE": "'OBSERVER'",
        "CENTER": "'coord@301'",
        "COORD_TYPE": "'GEODETIC'",
        "SITE_COORD": f"'{lon},{lat},0'",
        "START_TIME": f"'{start_dt:%Y-%m-%d %H:%M}'",
        "STOP_TIME": f"'{end_dt:%Y-%m-%d %H:%M}'",
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
            rows.append({
                "time": pd.to_datetime(parts[0], format="%Y-%b-%d %H:%M"),
                "elevation": float(parts[4]),
            })
        except ValueError:
            continue

    if not rows:
        raise ValueError("No valid NASA Horizons records found.")

    return pd.DataFrame(rows)

def compute_visibility(lat, lon, start_dt, hours):
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

# =========================================================
# SIDEBAR
# =========================================================

with st.sidebar:
    st.markdown("## أُفُق | OFOQ")
    st.caption("BEYOND THE HORIZON")

    st.selectbox(
        "Language",
        ["العربية", "English"],
        key="language",
        label_visibility="collapsed",
    )

    st.divider()

    items = [
        ("explore", tr("explore")),
        ("views", tr("views")),
        ("sunearth", tr("sunearth")),
        ("compare", tr("compare")),
    ]

    for key, label in items:
        if st.button(
            label,
            key=f"nav_{key}",
            type="primary" if st.session_state.page == key else "secondary",
            use_container_width=True,
        ):
            st.session_state.page = key
            st.rerun()

    st.divider()

    st.caption(tr("selected_site"))
    st.write(f"{tr('lat')}: **{st.session_state.lat:.5f}°**")
    st.write(f"{tr('lon')}: **{st.session_state.lon:.5f}°**")

    if st.button(tr("save_backup"), use_container_width=True):
        st.session_state.backup_site = (st.session_state.lat, st.session_state.lon)
        st.success("✓")

# =========================================================
# HERO
# =========================================================

st.markdown(
    f"""
    <div class="ofoq-hero" dir="{dir_attr()}">
      <div class="ofoq-eyebrow">NASA SPACE APPS CHALLENGE 2026</div>
      <div class="ofoq-title">أُفُق | OFOQ</div>
      <div class="ofoq-eyebrow">BEYOND THE HORIZON, TOWARD THE MOON.</div>
      <p>{tr('hero_desc')}</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# =========================================================
# PAGE 1 — EXPLORE
# =========================================================

if st.session_state.page == "explore":
    st.header(tr("explore"))
    st.write(tr("choose_site"))

    left, right = st.columns([2, 1], gap="large")

    with left:
        moon_img = build_clickable_moon(st.session_state.lat, st.session_state.lon)
        click = streamlit_image_coordinates(moon_img, width=1200, key="moon_click")

        if click is not None:
            lon = click["x"] / 1200 * 360 - 180
            lat = 90 - click["y"] / 600 * 180
            set_site(lat, lon)
            st.rerun()

    with right:
        render_decorative_3d_moon()

        st.markdown(
            f"""
            <div class="ofoq-card" dir="{dir_attr()}">
              <div class="ofoq-card-title">{tr("selected_site")}</div>
              <div class="ofoq-muted">
                {tr("lat")}: {st.session_state.lat:.5f}°<br>
                {tr("lon")}: {st.session_state.lon:.5f}°
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

# =========================================================
# PREP TERRAIN (shared for page 2)
# =========================================================

def ensure_terrain():
    site = (st.session_state.lat, st.session_state.lon)

    if (
        st.session_state.terrain_cache is not None
        and st.session_state.terrain_cache["site"] == site
    ):
        return st.session_state.terrain_cache

    try:
        slope, height, pixel = get_site_terrain(*site)
        top_img = create_top_terrain_image(height)
        side_img = create_side_terrain_image(height)
        cells = build_cells_3x3(slope)

        data = {
            "site": site,
            "ok": True,
            "pixel": pixel,
            "top_img": top_img,
            "side_img": side_img,
            "cells": cells,
            "best": best_cell(cells),
            "error": None,
        }
    except Exception as err:
        fallback = fallback_surface_image(*site)
        cells = [{
            "row": r,
            "col": c,
            "score": None,
            "status": "gray",
            "slope": None,
            "coverage": 0,
            "position": position_name(r, c),
        } for r in range(3) for c in range(3)]

        data = {
            "site": site,
            "ok": False,
            "pixel": None,
            "top_img": fallback,
            "side_img": create_side_terrain_image(np.random.rand(48, 48)),  # visual fallback
            "cells": cells,
            "best": None,
            "error": str(err),
        }

    st.session_state.terrain_cache = data
    return data

# =========================================================
# PAGE 2 — LANDING VIEWS
# =========================================================

elif st.session_state.page == "views":
    terrain = ensure_terrain()

    st.header(tr("views"))
    st.write(tr("camera_desc"))

    c1, c2 = st.columns(2)
    with c1:
        if st.button(
            tr("side_view"),
            type="primary" if st.session_state.get("view_mode", "side") == "side" else "secondary",
            use_container_width=True,
        ):
            st.session_state.view_mode = "side"
            st.rerun()

    with c2:
        if st.button(
            tr("camera_view"),
            type="primary" if st.session_state.get("view_mode", "side") == "camera" else "secondary",
            use_container_width=True,
        ):
            st.session_state.view_mode = "camera"
            st.rerun()

    if "view_mode" not in st.session_state:
        st.session_state.view_mode = "side"

    left, right = st.columns([3, 1], gap="large")

    with left:
        if st.session_state.view_mode == "side":
            render_lander_view(terrain["side_img"])
        else:
            render_camera_view(terrain["top_img"], terrain["cells"])

    with right:
        # best site
        best = terrain["best"]
        if best is not None:
            status_color = COLORS[best["status"]]
            st.markdown(
                f"""
                <div class="ofoq-card" dir="{dir_attr()}">
                  <div class="ofoq-card-title">{tr("best_spot")}</div>
                  <div style="font-size:34px;font-weight:850;color:{status_color};margin:6px 0;">
                    {best["score"]}%
                  </div>
                  <div class="ofoq-muted">
                    {best["position"]}<br>
                    {"ميل السطح" if is_ar() else "Slope"}: {best["slope']}°
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"""
                <div class="ofoq-card" dir="{dir_attr()}">
                  <div class="ofoq-card-title">{tr("best_spot")}</div>
                  <div class="ofoq-muted">{tr("legend_gray")}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # legend
        st.markdown(
            f"""
            <div class="ofoq-card" dir="{dir_attr()}">
              <div class="ofoq-card-title">{tr("legend")}</div>
              <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;">
                <span style="width:14px;height:14px;border-radius:3px;background:{COLORS['green']};display:inline-block;"></span>
                <span>{tr("legend_green")}</span>
              </div>
              <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;">
                <span style="width:14px;height:14px;border-radius:3px;background:{COLORS['yellow']};display:inline-block;"></span>
                <span>{tr("legend_yellow")}</span>
              </div>
              <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;">
                <span style="width:14px;height:14px;border-radius:3px;background:{COLORS['red']};display:inline-block;"></span>
                <span>{tr("legend_red")}</span>
              </div>
              <div style="display:flex;align-items:center;gap:10px;">
                <span style="width:14px;height:14px;border-radius:3px;background:{COLORS['gray']};display:inline-block;"></span>
                <span>{tr("legend_gray")}</span>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.caption(tr("rank_note"))

    if terrain["ok"]:
        st.success(
            "تم تحليل الموقع تلقائيًا"
            if is_ar() else
            "The site was analyzed automatically"
        )
        st.caption(
            f"NASA LOLA | {terrain['pixel']:.0f} m/pixel"
        )
    else:
        st.warning(
            "تعذر قراءة قياسات الموقع من NASA"
            if is_ar() else
            "Could not read NASA measurements for this site"
        )
        with st.expander("Technical details"):
            st.code(terrain["error"])

    st.caption(tr("real_note"))

# =========================================================
# PAGE 3 — SUN & EARTH
# =========================================================

elif st.session_state.page == "sunearth":
    st.header(tr("sunearth"))

    mission_date = st.date_input(tr("date"), value=date(2026, 11, 15))
    duration = st.slider(tr("hours"), 24, 96, 48, 12)

    signature = (
        st.session_state.lat,
        st.session_state.lon,
        mission_date,
        duration,
    )

    if st.button(tr("analyze"), type="primary"):
        try:
            start_dt = datetime.combine(mission_date, datetime.min.time())
            with st.spinner("NASA Horizons"):
                df = compute_visibility(st.session_state.lat, st.session_state.lon, start_dt, duration)
            st.session_state.mission_cache = (signature, df)
        except Exception as err:
            st.error(str(err))

    cache = st.session_state.mission_cache
    if cache and cache[0] == signature:
        df = cache[1]
        m = visibility_metrics(df)

        a, b, c = st.columns(3)
        a.metric(tr("sun_vis"), f"{m['Sun']} h")
        b.metric(tr("earth_vis"), f"{m['Earth']} h")
        c.metric(tr("both_vis"), f"{m['Both']} h")

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df["time"],
            y=df["elevation_sun"],
            name="Sun",
            line=dict(color="#DCECF7", width=3),
        ))
        fig.add_trace(go.Scatter(
            x=df["time"],
            y=df["elevation_earth"],
            name="Earth",
            line=dict(color="#76C5F5", width=3),
        ))
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

# =========================================================
# PAGE 4 — PLAN B
# =========================================================

elif st.session_state.page == "compare":
    st.header(tr("compare"))

    mission_date = st.date_input(tr("date"), value=date(2026, 11, 15), key="cmp_date")
    duration = st.slider(tr("hours"), 24, 96, 48, 12, key="cmp_hours")

    mode = st.radio(
        "Mode",
        ["delay", "site"],
        format_func=lambda x: tr("same_site_delay") if x == "delay" else tr("different_site"),
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
            st.info(f"{lat_b:.5f}°, {lon_b:.5f}°")
        else:
            st.warning(
                "احفظ موقعًا بديلًا أولًا من الصفحة الأولى."
                if is_ar() else
                "Save a backup site first from the first page."
            )

    if st.button(tr("run_compare"), type="primary", disabled=(mode == "site" and st.session_state.backup_site is None)):
        try:
            with st.spinner("NASA Horizons"):
                df1 = compute_visibility(st.session_state.lat, st.session_state.lon, start_a, duration)
                df2 = compute_visibility(lat_b, lon_b, start_b, duration)

            m1 = visibility_metrics(df1)
            m2 = visibility_metrics(df2)

            left, right = st.columns(2)
            with left:
                st.subheader(tr("original"))
                for k, v in m1.items():
                    st.metric(k, f"{v} h")
            with right:
                st.subheader(tr("alternative"))
                for k, v in m2.items():
                    st.metric(k, f"{v} h", delta=v - m1[k])

            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=list(m1.keys()),
                y=list(m1.values()),
                name=tr("original"),
                marker_color="#6D7A8A",
            ))
            fig.add_trace(go.Bar(
                x=list(m2.keys()),
                y=list(m2.values()),
                name=tr("alternative"),
                marker_color="#76C5F5",
            ))
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

# =========================================================
# SOURCES
# =========================================================

st.divider()

with st.expander(tr("sources")):
    st.markdown(
        """
**NASA Moon Visualization**
https://svs.gsfc.nasa.gov/4720/

**NASA LOLA polar data**
https://pgda.gsfc.nasa.gov/products/90

**NASA/JPL Horizons**
https://ssd-api.jpl.nasa.gov/doc/horizons.html

**Important note**
- Landing percentages shown here are a prototype suitability index based mainly on slope.
- Green = 75–100, Yellow = 50–74, Red = 0–49.
- Gray means no usable measurements were available.
- This is not a certified landing system.
"""
    )

st.caption("TEAM OFOQ | NASA SPACE APPS CHALLENGE 2026")
