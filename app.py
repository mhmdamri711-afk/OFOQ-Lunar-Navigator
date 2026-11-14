import streamlit as st
import streamlit.components.v1 as components
import requests
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import rasterio

from datetime import datetime, date, timedelta
from PIL import Image, ImageOps
from io import BytesIO
from pyproj import CRS, Transformer
from rasterio.windows import Window
from rasterio.enums import Resampling

import base64
import json
import html


# ==========================================================
# OFOQ v6
# NASA SPACE APPS CHALLENGE 2026
# ==========================================================

st.set_page_config(
    page_title="أُفُق | OFOQ",
    page_icon="🌙",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Colors sampled/inspired by OFOQ team artwork.
SPACE = "#000103"
NAVY = "#081522"
DEEP = "#10243A"
ICE = "#76C5F5"
SILVER = "#DCEEFA"
MOON = "#616169"

TEXTURE_URL = (
    "https://svs.gsfc.nasa.gov/vis/a000000/"
    "a004700/a004720/lroc_color_2k.jpg"
)

# NASA Apollo 17 photograph — NOT selected-site imagery.
PHOTO_URL = (
    "https://assets.science.nasa.gov/content/dam/"
    "science/psd/lunar-science/2023/09/"
    "610213main_S73-22871_full-2.jpg"
)

PGDA = "https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/"

SLOPE_URL = PGDA + "LDSM_80S_80MPP_ADJ.TIF"
DEM_URL = PGDA + "LDEM_80S_80MPP_ADJ.TIF"

HORIZONS = "https://ssd.jpl.nasa.gov/api/horizons.api"

MOON_CRS = CRS.from_proj4(
    "+proj=longlat +a=1737400 +b=1737400 "
    "+no_defs +type=crs"
)

# ==========================================================
# STATE
# ==========================================================

DEFAULTS = {
    "language": "العربية",
    "page": "explore",
    "mode": "2D",
    "lat": -89.0,
    "lon": 0.0,
    "last_pick": None,
    "backup": None,
    "scan_result": None,
    "visibility_result": None,
}

for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ==========================================================
# LANGUAGE
# ==========================================================

WORDS = {
    "explore": ("استكشاف القمر", "Explore the Moon"),
    "surface": ("كاميرا المركبة والمسح", "Lander Camera & Scan"),
    "sun": ("الشمس والاتصال", "Sun & Communication"),
    "compare": ("المقارنة والخطة البديلة", "Compare & Plan B"),
    "lang": ("اللغة", "Language"),
    "site": ("الموقع المحدد", "Selected location"),
    "lat": ("خط العرض", "Latitude"),
    "lon": ("خط الطول", "Longitude"),
    "choose": (
        "اضغط على سطح القمر لتحديد الموقع",
        "Click the Moon to choose a location"
    ),
    "mapinfo": (
        "اضغط مرة واحدة لاختيار الموقع. اسحب للتحريك، "
        "واستخدم عجلة الماوس للتكبير.",
        "Click once to select a site. Drag to move "
        "and use the mouse wheel to zoom."
    ),
    "selected": (
        "تم اختيار الموقع",
        "Location selected"
    ),
    "savebackup": (
        "احفظ هذا الموقع للخطة البديلة",
        "Save this as backup location"
    ),
    "scanintro": (
        "شاهد سطح القمر من منظور افتراضي للمركبة، "
        "واكتشف معلومات التضاريس بالضغط على المربعات.",
        "View a virtual lander perspective and "
        "click cells to inspect terrain information."
    ),
    "scan": ("ابدأ المسح العلمي", "Start scientific scan"),
    "nasa": ("بيانات NASA", "NASA data"),
    "unknown": ("البيانات غير متاحة", "Data unavailable"),
    "pending": (
        "لم يبدأ تحليل هذا الموقع بعد.",
        "This location has not been analyzed yet."
    ),
    "scanok": (
        "تم تحميل قياسات الانحدار من NASA.",
        "NASA slope measurements loaded."
    ),
    "scanbad": (
        "لم نتمكن من قراءة قياسات الانحدار لهذا الموقع. "
        "ستبقى الخلايا دون تصنيف.",
        "Slope measurements could not be read for "
        "this site. Cells remain unclassified."
    ),
    "scanlimit": (
        "هذه مقارنة أولية لانحدار الأرض، وليست ضمانًا "
        "لسلامة الهبوط. الصورة الفوتوغرافية من Apollo 17 "
        "وليست من الموقع المختار.",
        "This is preliminary slope screening, not "
        "a landing safety guarantee. The photograph "
        "is from Apollo 17, not the selected site."
    ),
    "date": ("تاريخ المهمة (UTC)", "Mission date (UTC)"),
    "hours": ("مدة المهمة بالساعات", "Mission duration (hours)"),
    "run": ("احسب ظروف المهمة", "Analyze mission"),
    "sunhours": ("وقت ظهور الشمس", "Sun visible"),
    "earthhours": ("وقت ظهور الأرض", "Earth visible"),
    "bothhours": ("ظهورهما معًا", "Both visible"),
    "horizon": (
        "ارتفاع الشمس والأرض عن الأفق",
        "Sun and Earth above the horizon"
    ),
    "time": ("الوقت (UTC)", "Time (UTC)"),
    "angle": ("الزاوية بالدرجات", "Elevation (degrees)"),
    "sunname": ("الشمس", "Sun"),
    "earthname": ("الأرض", "Earth"),
    "comparetitle": (
        "ماذا يحدث إذا تغيرت خطة الهبوط؟",
        "What if the landing plan changes?"
    ),
    "delaymode": (
        "تأخير الهبوط في الموقع نفسه",
        "Delay at the same location"
    ),
    "sitemode": (
        "موقع آخر في التاريخ نفسه",
        "Alternative site, same date"
    ),
    "delay": ("التأخير بالساعات", "Delay (hours)"),
    "comparebutton": ("قارن الخطتين", "Compare plans"),
    "original": ("الخطة الأصلية", "Original plan"),
    "alternative": ("الخطة البديلة", "Alternative plan"),
    "help": ("كيف يعمل أُفُق؟", "How OFOQ works"),
    "source": ("المصادر العلمية", "Scientific sources"),
}


def t(key):
    value = WORDS.get(key, (key, key))
    return value[0] if st.session_state.language == "العربية" else value[1]


def arabic():
    return st.session_state.language == "العربية"


def direction():
    return "rtl" if arabic() else "ltr"


def apply_location(lat, lon):
    lat = max(-90, min(90, float(lat)))
    lon = ((float(lon) + 180) % 360) - 180

    st.session_state.lat = round(lat, 5)
    st.session_state.lon = round(lon, 5)
    st.session_state.scan_result = None
    st.session_state.visibility_result = None


# ==========================================================
# IMAGE LOADING
# ==========================================================

@st.cache_data(ttl=86400, show_spinner=False)
def image_data(url, width=None, height=None):
    response = requests.get(url, timeout=35)
    response.raise_for_status()

    image = Image.open(
        BytesIO(response.content)
    ).convert("RGB")

    if width and height:
        image = ImageOps.fit(
            image,
            (width, height),
            method=Image.Resampling.LANCZOS
        )

    buf = BytesIO()
    image.save(buf, format="JPEG", quality=85)

    return (
        "data:image/jpeg;base64,"
        + base64.b64encode(buf.getvalue()).decode()
    )


# ==========================================================
# VISUAL DESIGN
# ==========================================================

st.markdown("""
<style>
:root {
    --ofoq-space: #000103;
    --ofoq-navy: #081522;
    --ofoq-deep: #10243A;
    --ofoq-ice: #76C5F5;
    --ofoq-silver: #DCEEFA;
    --ofoq-moon: #616169;
}

.stApp {
    background:
      radial-gradient(
        ellipse at 85% 2%,
        #10243A 0%,
        #081522 34%,
        #000103 78%
      ) !important;
    color: #DCEEFA;
}

[data-testid="stHeader"] {
    background: transparent !important;
}

[data-testid="stSidebar"] {
    background: #06111F !important;
    border-right: 1px solid #29475D;
}

.block-container {
    max-width: 1600px;
    padding-top: 1rem;
    padding-bottom: 4rem;
}

h1, h2, h3, p, label {
    color: #DCEEFA !important;
}

.stButton button {
    min-height: 48px;
    border-radius: 12px !important;
    background: #10243A !important;
    border: 1px solid #35526C !important;
    color: #DCEEFA !important;
    font-weight: 650;
    transition: 0.15s;
}

.stButton button:hover {
    border-color: #76C5F5 !important;
    background: #18344E !important;
}

.stButton button[kind="primary"] {
    background: #76C5F5 !important;
    color: #000103 !important;
}

.stButton button[kind="primary"]:hover {
    background: #DCEEFA !important;
}

[data-testid="stMetric"] {
    background: #10243A;
    border: 1px solid #35526C;
    border-radius: 15px;
    padding: 17px;
}

[data-testid="stMetricValue"] {
    color: #DCEEFA;
}

[data-baseweb="slider"] [role="slider"] {
    background: #76C5F5 !important;
    border-color: #76C5F5 !important;
}

input, select {
    accent-color: #76C5F5;
}

.ofoq-hero {
    background:
      radial-gradient(
        circle at 78% 38%,
        #2858785E,
        transparent 29%
      ),
      linear-gradient(110deg, #000103, #10243A);
    border: 1px solid #35526C;
    border-radius: 24px;
    padding: 30px 38px;
    margin-bottom: 23px;
    box-shadow: 0 18px 60px #00000066;
}

.ofoq-eyebrow {
    color: #76C5F5;
    font-size: 12px;
    letter-spacing: 3px;
    font-weight: 700;
}

.ofoq-wordmark {
    font-size: clamp(42px, 5vw, 70px);
    color: #DCEEFA;
    font-weight: 800;
    letter-spacing: 5px;
    margin: 7px 0;
    text-shadow: 0 0 32px #76C5F54A;
}

.ofoq-arc {
    width: 240px;
    height: 30px;
    border-top: 2px solid #76C5F5;
    border-radius: 50% 50% 0 0;
    margin-top: 10px;
    box-shadow: 0 -8px 24px #76C5F51C;
}

.ofoq-subtitle {
    color: #DCEEFA;
    opacity: .85;
    font-size: 16px;
    margin-top: 10px;
}

.ofoq-sidebrand {
    text-align: center;
    padding: 16px 0 20px;
    border-bottom: 1px solid #35526C;
    margin-bottom: 16px;
}

.ofoq-sidebrand strong {
    font-size: 29px;
    letter-spacing: 2px;
    color: #DCEEFA;
}

.ofoq-sidebrand small {
    display: block;
    color: #76C5F5;
    margin-top: 5px;
    letter-spacing: 1px;
}

.ofoq-sideheading {
    color: #76C5F5;
    font-size: 12px;
    letter-spacing: 1px;
    margin: 18px 0 9px;
}

.ofoq-card {
    background: #10243A;
    border: 1px solid #35526C;
    border-radius: 16px;
    padding: 18px 22px;
    margin: 13px 0;
}

.ofoq-help {
    font-size: 14px;
    color: #DCEEFA;
    line-height: 1.9;
}
</style>
""", unsafe_allow_html=True)


# ==========================================================
# SIDEBAR NAVIGATION
# ==========================================================

with st.sidebar:
    st.markdown("""
    <div class="ofoq-sidebrand">
      <strong>أُفُق | OFOQ</strong>
      <small>BEYOND THE HORIZON</small>
    </div>
    """, unsafe_allow_html=True)

    st.selectbox(
        "Language",
        ["العربية", "English"],
        key="language",
        label_visibility="collapsed"
    )

    st.markdown(
        '<div class="ofoq-sideheading">'
        'MISSION NAVIGATION</div>',
        unsafe_allow_html=True
    )

    nav_items = [
        ("explore", "◉ " + t("explore")),
        ("surface", "▦ " + t("surface")),
        ("sun", "☼ " + t("sun")),
        ("compare", "◇ " + t("compare"))
    ]

    for key, label in nav_items:
        if st.button(
            label,
            key="nav_" + key,
            type=(
                "primary"
                if st.session_state.page == key
                else "secondary"
            ),
            use_container_width=True
        ):
            st.session_state.page = key
            st.rerun()

    st.divider()

    st.markdown(
        '<div class="ofoq-sideheading">'
        + t("site") + '</div>',
        unsafe_allow_html=True
    )

    st.write(
        f"{t('lat')}: **{st.session_state.lat:.5f}°**"
    )
    st.write(
        f"{t('lon')}: **{st.session_state.lon:.5f}°**"
    )

    if st.button(
        t("savebackup"),
        use_container_width=True
    ):
        st.session_state.backup = (
            st.session_state.lat,
            st.session_state.lon
        )
        st.success(
            "تم حفظ الموقع البديل."
            if arabic()
            else "Backup site saved."
        )

    st.divider()

    with st.expander(t("help")):
        if arabic():
            st.write(
                "1. اختر موقعًا بالضغط على القمر.\n\n"
                "2. افتح كاميرا المركبة وابدأ المسح.\n\n"
                "3. افحص الشمس والأرض.\n\n"
                "4. قارن بين خطتي هبوط."
            )
        else:
            st.write(
                "1. Click the Moon to choose a site.\n\n"
                "2. Open the lander view and scan.\n\n"
                "3. Analyze the Sun and Earth.\n\n"
                "4. Compare two landing plans."
            )


# ==========================================================
# HERO
# ==========================================================

st.markdown(
    f"""
    <div class="ofoq-hero" dir="{direction()}">
      <div class="ofoq-eyebrow">
        NASA SPACE APPS CHALLENGE 2026
      </div>
      <div class="ofoq-arc"></div>
      <div class="ofoq-wordmark">
        أُفُق | OFOQ
      </div>
      <div class="ofoq-eyebrow">
        BEYOND THE HORIZON, TOWARD THE MOON.
      </div>
      <div class="ofoq-subtitle">
        {"استكشف القمر، اختر موقعًا، وحلل ظروف المهمة."
         if arabic()
         else "Explore the Moon, choose a site, "
              "and analyze mission conditions."}
      </div>
    </div>
    """,
    unsafe_allow_html=True
)


# ==========================================================
# CLICKABLE MOON — 2D AND 3D
# Streamlit V2 component communicates clicks to Python.
# ==========================================================

MOON_PICKER_HTML = """
<div class="ofoq-picker-root">
  <div class="ofoq-picker-status"></div>
  <div class="ofoq-picker-stage"></div>
  <div class="ofoq-picker-hint"></div>
</div>
"""

MOON_PICKER_CSS = """
.ofoq-picker-root {
  position: relative;
  width: 100%;
  border: 1px solid #35526C;
  border-radius: 20px;
  overflow: hidden;
  background: #000103;
  color: #DCEEFA;
  font-family: Arial, sans-serif;
}

.ofoq-picker-stage {
  position: relative;
  width: 100%;
  height: 520px;
  background: #000103;
  overflow: hidden;
}

.ofoq-picker-stage canvas {
  display: block;
  width: 100%;
  height: 100%;
  cursor: crosshair;
  touch-action: none;
}

.ofoq-picker-status {
  position: absolute;
  left: 15px;
  top: 15px;
  z-index: 5;
  background: #081522E8;
  border: 1px solid #35526C;
  padding: 11px 15px;
  border-radius: 12px;
  font-size: 13px;
}

.ofoq-picker-hint {
  position: absolute;
  left: 15px;
  bottom: 15px;
  z-index: 5;
  background: #081522E8;
  border: 1px solid #35526C;
  padding: 10px 15px;
  border-radius: 10px;
  font-size: 12px;
  max-width: 85%;
}
"""

MOON_PICKER_JS = """
export default function(component) {
  const {
    data, parentElement, setTriggerValue
  } = component;

  const root = document.createElement("div");
  root.className = "ofoq-picker-root";
  root.innerHTML = `
    <div class="ofoq-picker-status"></div>
    <div class="ofoq-picker-stage"></div>
    <div class="ofoq-picker-hint"></div>
  `;

  parentElement.appendChild(root);

  const stage = root.querySelector(".ofoq-picker-stage");
  const status = root.querySelector(".ofoq-picker-status");
  const hint = root.querySelector(".ofoq-picker-hint");

  status.textContent = data.mode === "3D"
    ? "OFOQ / 3D LUNAR EXPLORER"
    : "OFOQ / 2D LUNAR EXPLORER";

  hint.textContent = data.language === "ar"
    ? "انقر لاختيار الموقع · اسحب للتحريك · عجلة الماوس للتكبير"
    : "Click to select · Drag to rotate/pan · Scroll to zoom";

  let disposed = false;
  let frameId = null;
  let cleanupMode = () => {};

  function pick(lat, lon) {
    lon = ((lon + 180) % 360 + 360) % 360 - 180;
    lat = Math.max(-90, Math.min(90, lat));

    setTriggerValue("picked", {
      lat: Number(lat.toFixed(5)),
      lon: Number(lon.toFixed(5)),
      nonce: Date.now() + Math.random()
    });
  }

  // --------------------- 2D MAP ---------------------
  if(data.mode === "2D") {
    const canvas = document.createElement("canvas");
    canvas.width = 1200;
    canvas.height = 600;
    stage.appendChild(canvas);

    const ctx = canvas.getContext("2d");
    const img = new Image();

    let zoom = 1;
    let centerX = 1024;
    let centerY = 512;

    let down = null;
    let dragging = false;

    const w = canvas.width;
    const h = canvas.height;

    function clampView() {
      if(!img.complete || !img.naturalWidth) return;

      const scale = (w / img.width) * zoom;
      const visibleW = w / scale;
      const visibleH = h / scale;

      centerX = Math.max(
        visibleW / 2,
        Math.min(img.width - visibleW / 2, centerX)
      );

      centerY = Math.max(
        visibleH / 2,
        Math.min(img.height - visibleH / 2, centerY)
      );
    }

    function draw() {
      if(!img.complete || !img.naturalWidth) return;

      clampView();

      const scale = (w / img.width) * zoom;
      const ox = w / 2 - centerX * scale;
      const oy = h / 2 - centerY * scale;

      ctx.fillStyle = "#000103";
      ctx.fillRect(0, 0, w, h);

      ctx.drawImage(
        img, ox, oy,
        img.width * scale,
        img.height * scale
      );

      const px = (data.lon + 180) / 360 * img.width;
      const py = (90 - data.lat) / 180 * img.height;

      const mx = ox + px * scale;
      const my = oy + py * scale;

      if(mx >= 0 && mx <= w && my >= 0 && my <= h) {
        ctx.strokeStyle = "#76C5F5";
        ctx.fillStyle = "#DCEEFA";
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.arc(mx, my, 12, 0, 2 * Math.PI);
        ctx.stroke();
        ctx.beginPath();
        ctx.arc(mx, my, 4, 0, 2 * Math.PI);
        ctx.fill();
      }
    }

    img.onload = () => {
      centerX = (data.lon + 180) / 360 * img.width;
      centerY = (90 - data.lat) / 180 * img.height;
      clampView();
      draw();
    };

    img.src = data.texture;

    function pos(event) {
      const rect = canvas.getBoundingClientRect();

      return {
        x: (event.clientX - rect.left) /
           rect.width * w,
        y: (event.clientY - rect.top) /
           rect.height * h
      };
    }

    function pointerDown(e) {
      const p = pos(e);
      down = {
        x:p.x, y:p.y,
        cx:centerX, cy:centerY
      };
      dragging = false;
      canvas.setPointerCapture(e.pointerId);
    }

    function pointerMove(e) {
      if(!down || !img.naturalWidth) return;

      const p = pos(e);
      const dx = p.x - down.x;
      const dy = p.y - down.y;

      if(Math.hypot(dx, dy) > 5) dragging = true;

      if(dragging) {
        const scale = w / img.width * zoom;
        centerX = down.cx - dx / scale;
        centerY = down.cy - dy / scale;
        draw();
      }
    }

    function pointerUp(e) {
      if(!down || !img.naturalWidth) return;

      const p = pos(e);

      if(!dragging) {
        const scale = w / img.width * zoom;
        const ox = w / 2 - centerX * scale;
        const oy = h / 2 - centerY * scale;

        const ix = (p.x - ox) / scale;
        const iy = (p.y - oy) / scale;

        const lat = 90 - iy / img.height * 180;
        const lon = ix / img.width * 360 - 180;

        pick(lat, lon);
      }

      down = null;
      dragging = false;
    }

    function wheel(e) {
      e.preventDefault();
      zoom = Math.max(
        1,
        Math.min(7, zoom * (e.deltaY < 0 ? 1.2 : 1/1.2))
      );
      draw();
    }

    canvas.addEventListener("pointerdown", pointerDown);
    canvas.addEventListener("pointermove", pointerMove);
    canvas.addEventListener("pointerup", pointerUp);
    canvas.addEventListener("wheel", wheel, {passive:false});

    cleanupMode = () => {
      canvas.removeEventListener("pointerdown", pointerDown);
      canvas.removeEventListener("pointermove", pointerMove);
      canvas.removeEventListener("pointerup", pointerUp);
      canvas.removeEventListener("wheel", wheel);
    };

  } else {

    // --------------------- 3D MOON ---------------------
    (async () => {
      try {
        const THREE = await import(
          "https://esm.sh/three@0.160.0"
        );

        const controlsModule = await import(
          "https://esm.sh/three@0.160.0/examples/jsm/controls/OrbitControls.js"
        );

        if(disposed) return;

        const OrbitControls = controlsModule.OrbitControls;

        const scene = new THREE.Scene();
        scene.background = new THREE.Color(0x000103);

        const camera = new THREE.PerspectiveCamera(
          45, 1, 0.1, 100
        );
        camera.position.set(0, 0, 4.7);

        const renderer = new THREE.WebGLRenderer({
          antialias:true
        });
        renderer.setPixelRatio(
          Math.min(window.devicePixelRatio, 2)
        );
        stage.appendChild(renderer.domElement);

        const texture = new THREE.TextureLoader().load(
          data.texture
        );
        texture.colorSpace = THREE.SRGBColorSpace;

        const moon = new THREE.Mesh(
          new THREE.SphereGeometry(1.65, 96, 64),
          new THREE.MeshStandardMaterial({
            map:texture,
            roughness:1
          })
        );
        scene.add(moon);

        scene.add(new THREE.AmbientLight(0xffffff,1.65));

        const light = new THREE.DirectionalLight(
          0xDCEEFA, 2.2
        );
        light.position.set(5,3,7);
        scene.add(light);

        // Marker position uses the same UV mapping
        // as THREE.SphereGeometry.
        const marker = new THREE.Mesh(
          new THREE.SphereGeometry(0.045,12,12),
          new THREE.MeshBasicMaterial({
            color:0x76C5F5
          })
        );

        const u = (data.lon + 180) / 360;
        const latRad = data.lat * Math.PI / 180;
        const phi = u * Math.PI * 2;

        marker.position.set(
          -1.69 * Math.cos(phi) * Math.cos(latRad),
           1.69 * Math.sin(latRad),
           1.69 * Math.sin(phi) * Math.cos(latRad)
        );
        scene.add(marker);

        const controls = new OrbitControls(
          camera, renderer.domElement
        );
        controls.enableDamping = true;
        controls.enablePan = false;
        controls.minDistance = 2.1;
        controls.maxDistance = 8;

        const raycaster = new THREE.Raycaster();
        const mouse = new THREE.Vector2();

        let pointerStart = null;

        function onDown(e) {
          pointerStart = {
            x:e.clientX,
            y:e.clientY
          };
        }

        function onUp(e) {
          if(!pointerStart) return;

          const d = Math.hypot(
            e.clientX - pointerStart.x,
            e.clientY - pointerStart.y
          );

          pointerStart = null;
          if(d > 6) return;

          const rect =
            renderer.domElement.getBoundingClientRect();

          mouse.x = (
            (e.clientX - rect.left) / rect.width
          ) * 2 - 1;

          mouse.y = -(
            (e.clientY - rect.top) / rect.height
          ) * 2 + 1;

          raycaster.setFromCamera(mouse, camera);

          const hits = raycaster.intersectObject(moon);

          if(!hits.length || !hits[0].uv) return;

          const uv = hits[0].uv;
          const lat = uv.y * 180 - 90;
          const lon = uv.x * 360 - 180;

          pick(lat, lon);
        }

        renderer.domElement.addEventListener(
          "pointerdown", onDown
        );
        renderer.domElement.addEventListener(
          "pointerup", onUp
        );

        function resize() {
          const w = stage.clientWidth || 900;
          const h = stage.clientHeight || 520;
          renderer.setSize(w,h);
          camera.aspect = w/h;
          camera.updateProjectionMatrix();
        }

        const observer = new ResizeObserver(resize);
        observer.observe(stage);
        resize();

        function animate() {
          if(disposed) return;
          frameId = requestAnimationFrame(animate);
          controls.update();
          renderer.render(scene,camera);
        }
        animate();

        cleanupMode = () => {
          observer.disconnect();
          controls.dispose();
          renderer.dispose();
          texture.dispose();
          moon.geometry.dispose();
          moon.material.dispose();
          marker.geometry.dispose();
          marker.material.dispose();
        };

      } catch(err) {
        status.textContent = "3D VIEW UNAVAILABLE";
        hint.textContent = String(err);
      }
    })();
  }

  return () => {
    disposed = true;
    if(frameId !== null) cancelAnimationFrame(frameId);
    cleanupMode();
    root.remove();
  };
}
"""

MOON_PICKER = st.components.v2.component(
    "ofoq_moon_picker_v6",
    html=MOON_PICKER_HTML,
    css=MOON_PICKER_CSS,
    js=MOON_PICKER_JS
)


# ==========================================================
# SCIENTIFIC TERRAIN SCAN — NASA COG
# ==========================================================

@st.cache_data(ttl=3600, show_spinner=False)
def read_terrain_window(lat, lon):
    if lat > -80:
        raise ValueError(
            "The polar dataset covers 80°S to 90°S."
        )

    results = []

    for url in [SLOPE_URL, DEM_URL]:
        with rasterio.Env(
            GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
            GDAL_HTTP_TIMEOUT="20",
            GDAL_HTTP_MAX_RETRY="1",
            CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".TIF"
        ):
            with rasterio.open("/vsicurl/" + url) as src:
                if src.crs is None:
                    raise ValueError(
                        "Missing lunar raster CRS"
                    )

                transformer = Transformer.from_crs(
                    MOON_CRS,
                    src.crs,
                    always_xy=True
                )

                x, y = transformer.transform(lon, lat)
                row, col = src.index(x,y)

                size = 64
                half = size // 2

                if not (
                    half <= row < src.height-half
                    and half <= col < src.width-half
                ):
                    raise ValueError(
                        "Location outside NASA raster"
                    )

                window = Window(
                    col-half,
                    row-half,
                    size,
                    size
                )

                arr = src.read(
                    1,
                    window=window,
                    masked=True
                ).astype(float).filled(np.nan)

                if src.nodata is not None:
                    arr[arr == src.nodata] = np.nan

                pixel = max(
                    abs(src.transform.a),
                    abs(src.transform.e)
                )

                results.append((arr,pixel))

    slope = results[0][0]
    dem = results[1][0]
    resolution = results[0][1]

    if not np.isfinite(slope).any():
        raise ValueError("No valid slope samples")

    return slope, dem, resolution


def classify_cells(slope=None):
    cells = []

    for row in range(8):
        for col in range(8):
            cell = {
                "id": f"{row+1}-{col+1}",
                "status": "unknown",
                "slope": None,
                "coverage": 0
            }

            if slope is not None:
                block = slope[
                    row*8:(row+1)*8,
                    col*8:(col+1)*8
                ]

                good = block[np.isfinite(block)]
                coverage = len(good) / block.size

                cell["coverage"] = round(
                    coverage * 100,1
                )

                if coverage >= 0.75:
                    p90 = float(
                        np.percentile(good,90)
                    )
                    cell["slope"] = round(p90,2)

                    # Prototype screening categories,
                    # NOT NASA landing safety criteria.
                    if p90 <= 5:
                        cell["status"] = "low"
                    elif p90 <= 12:
                        cell["status"] = "medium"
                    else:
                        cell["status"] = "high"

            cells.append(cell)

    return cells


# ==========================================================
# IMMERSIVE LANDER PHOTO + SCAN
# ==========================================================

def render_scanner(cells):
    photo = image_data(
        PHOTO_URL,
        width=1500,
        height=780
    )

    polygons = []

    # Perspective grid placed on the ground portion
    # of the reference photo.
    # This overlay is illustrative, not registered
    # to the Apollo image or selected site.
    def edge(row, side):
        t = row / 8
        y = 255 + (t ** 1.35)*265

        if side == "left":
            x = 300 - t*270
        else:
            x = 700 + t*270

        return x,y

    for row in range(8):
        for col in range(8):
            lx0,y0 = edge(row,"left")
            rx0,_ = edge(row,"right")

            lx1,y1 = edge(row+1,"left")
            rx1,_ = edge(row+1,"right")

            xa = lx0+(rx0-lx0)*col/8
            xb = lx0+(rx0-lx0)*(col+1)/8
            xc = lx1+(rx1-lx1)*col/8
            xd = lx1+(rx1-lx1)*(col+1)/8

            points = (
                f"{xa:.1f},{y0:.1f} "
                f"{xb:.1f},{y0:.1f} "
                f"{xd:.1f},{y1:.1f} "
                f"{xc:.1f},{y1:.1f}"
            )

            index = row*8+col

            polygons.append(
                f'<polygon points="{points}" '
                f'data-index="{index}" '
                f'class="scan-cell {cells[index]["status"]}"/>'
            )

    grid_markup = "\n".join(polygons)

    status_title = (
        "OFOQ / مسح التضاريس"
        if arabic()
        else "OFOQ / TERRAIN RECON"
    )

    source_message = (
        "صورة Apollo 17 للتوضيح، وليست للموقع المختار"
        if arabic()
        else "Apollo 17 reference photo — not the selected site"
    )

    starting_text = (
        "اضغط على أي مربع لعرض بياناته"
        if arabic()
        else "Click a cell to inspect its measurements"
    )

    page_html = """
    <html>
    <head>
    <style>
    * {box-sizing:border-box;}

    body {
      margin:0;
      background:#000103;
      color:#DCEEFA;
      font-family:Arial,sans-serif;
    }

    .camera {
      position:relative;
      height:565px;
      overflow:hidden;
      border-radius:18px;
      border:1px solid #35526C;
      background:#000103;
    }

    .photo {
      position:absolute;
      inset:0;
      background-image:
        linear-gradient(
          to bottom,
          #00010340,
          #00010300 42%,
          #000103A0 100%
        ),
        url('__PHOTO__');
      background-size:cover;
      background-position:center;
    }

    .scan-svg {
      position:absolute;
      width:100%;
      height:100%;
      inset:0;
      z-index:4;
    }

    .scan-cell {
      stroke:#DCEEFA;
      stroke-width:1.0;
      fill:#76C5F5;
      fill-opacity:.15;
      cursor:pointer;
      transition:fill-opacity .15s;
    }

    .scan-cell:hover {
      fill-opacity:.55;
      stroke-width:2.5;
    }

    .scan-cell.low {
      fill:#76C5F5;
      fill-opacity:.28;
    }

    .scan-cell.medium {
      fill:#616169;
      fill-opacity:.42;
    }

    .scan-cell.high {
      fill:#DCEEFA;
      fill-opacity:.55;
    }

    .scan-cell.unknown {
      fill:#10243A;
      fill-opacity:.15;
    }

    .scan-beam {
      stroke:#76C5F5;
      stroke-width:3;
      filter:drop-shadow(0 0 8px #76C5F5);
      animation:scanner 4.6s linear infinite;
    }

    @keyframes scanner {
      0% {transform:translateY(0px);}
      100% {transform:translateY(270px);}
    }

    .hud {
      position:absolute;
      left:18px;
      top:16px;
      background:#000103D9;
      color:#DCEEFA;
      border:1px solid #76C5F5;
      border-radius:11px;
      padding:11px 15px;
      font-size:12px;
      z-index:9;
    }

    .details {
      position:absolute;
      right:16px;
      bottom:16px;
      width:min(360px,50%);
      background:#081522ED;
      color:#DCEEFA;
      border:1px solid #35526C;
      border-radius:13px;
      padding:14px 16px;
      font-size:13px;
      line-height:1.8;
      z-index:9;
    }

    .source {
      position:absolute;
      left:15px;
      bottom:16px;
      max-width:310px;
      font-size:11px;
      line-height:1.5;
      background:#000103D9;
      padding:9px 11px;
      border-radius:9px;
      z-index:9;
    }
    </style>
    </head>
    <body>
      <div class="camera">
        <div class="photo"></div>
        <div class="hud">__TITLE__</div>

        <svg class="scan-svg"
             viewBox="0 0 1000 565"
             preserveAspectRatio="none">
          __GRID__
          <line class="scan-beam"
                x1="80" y1="255"
                x2="920" y2="255"/>
        </svg>

        <div class="details" id="details">
          __START__
        </div>

        <div class="source">
          __SOURCE__
        </div>
      </div>

      <script>
        const cells = __CELLS__;
        const language = "__LANG__";
        const output = document.getElementById("details");

        document.querySelectorAll(".scan-cell")
          .forEach(polygon=>{
            polygon.onclick=()=>{
              const index=Number(
                polygon.getAttribute("data-index")
              );

              const cell=cells[index];

              const slope=cell.slope===null
                ? (language==="ar"
                    ? "غير متاح"
                    : "Unavailable")
                : cell.slope+"°";

              if(language==="ar"){
                output.innerHTML=
                  "<b>الخلية "+cell.id+"</b><br>"+
                  "مؤشر الانحدار: "+slope+"<br>"+
                  "البيانات الصالحة: "+
                  cell.coverage+"%<br>"+
                  "التصنيف الأولي: "+
                  cell.status;
              }else{
                output.innerHTML=
                  "<b>CELL "+cell.id+"</b><br>"+
                  "Slope P90: "+slope+"<br>"+
                  "Valid coverage: "+
                  cell.coverage+"%<br>"+
                  "Preliminary class: "+
                  cell.status;
              }
            };
          });
      </script>
    </body>
    </html>
    """

    page_html = (
        page_html
        .replace("__PHOTO__", photo)
        .replace("__GRID__", grid_markup)
        .replace("__CELLS__", json.dumps(cells))
        .replace("__TITLE__", html.escape(status_title))
        .replace("__SOURCE__", html.escape(source_message))
        .replace("__START__", html.escape(starting_text))
        .replace("__LANG__", "ar" if arabic() else "en")
    )

    components.html(
        page_html,
        height=575,
        scrolling=False
    )


# ==========================================================
# NASA JPL HORIZONS
# ==========================================================

@st.cache_data(ttl=3600, show_spinner=False)
def horizons(body, lat, lon, start_text, hours):
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
        HORIZONS,
        params=params,
        timeout=60
    )
    response.raise_for_status()
    text = response.json()["result"]

    if "$$SOE" not in text or "$$EOE" not in text:
        raise ValueError(text[:350])

    block = text.split("$$SOE")[1].split("$$EOE")[0]

    records = []

    for line in block.splitlines():
        parts = [p.strip() for p in line.split(",")]

        if len(parts) < 5:
            continue

        try:
            records.append({
                "time": pd.to_datetime(
                    parts[0],
                    format="%Y-%b-%d %H:%M"
                ),
                "azimuth": float(parts[3]),
                "elevation": float(parts[4])
            })
        except ValueError:
            continue

    if not records:
        raise ValueError("No NASA ephemeris records")

    return pd.DataFrame(records)


def analyze(lat,lon,start,hours):
    start_text = start.strftime("%Y-%m-%d %H:%M")

    sun = horizons(
        "10",lat,lon,start_text,hours
    )
    earth = horizons(
        "399",lat,lon,start_text,hours
    )

    df = sun[["time","elevation"]].merge(
        earth[["time","elevation"]],
        on="time",
        suffixes=("_sun","_earth")
    ).sort_values("time")

    df = df.iloc[:-1].copy()

    if len(df) != hours:
        raise ValueError(
            "Incomplete hourly data"
        )

    df["Sun"] = df.elevation_sun > 0
    df["Earth"] = df.elevation_earth > 0
    df["Both"] = df.Sun & df.Earth

    return df


def numbers(df):
    return {
        "Sun": int(df["Sun"].sum()),
        "Earth": int(df["Earth"].sum()),
        "Both": int(df["Both"].sum())
    }


def show_results(df):
    n = numbers(df)

    cols = st.columns(3)

    cols[0].metric(t("sunhours"),f"{n['Sun']} h")
    cols[1].metric(t("earthhours"),f"{n['Earth']} h")
    cols[2].metric(t("bothhours"),f"{n['Both']} h")

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df.time,
        y=df.elevation_sun,
        name=t("sunname"),
        line=dict(
            color="#DCEEFA",
            width=3
        )
    ))

    fig.add_trace(go.Scatter(
        x=df.time,
        y=df.elevation_earth,
        name=t("earthname"),
        line=dict(
            color="#76C5F5",
            width=3
        )
    ))

    fig.add_hline(
        y=0,
        line_dash="dash",
        line_color="#616169"
    )

    fig.update_layout(
        title=t("horizon"),
        xaxis_title=t("time"),
        yaxis_title=t("angle"),
        template="plotly_dark",
        paper_bgcolor="#081522",
        plot_bgcolor="#081522",
        font=dict(color="#DCEEFA"),
        hovermode="x unified",
        height=400
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )

    st.caption(
        "تقديرات هندسية كل ساعة؛ لا تشمل حجب الجبال "
        "أو كفاءة الاتصال الفعلية."
        if arabic()
        else "Hourly geometric estimates. Terrain "
             "obstruction and radio-link quality "
             "are not modeled."
    )


# ==========================================================
# PAGE 1 — EXPLORE
# ==========================================================

if st.session_state.page == "explore":
    st.header(t("explore"))

    st.write(t("choose"))
    st.caption(t("mapinfo"))

    view = st.segmented_control(
        "View",
        ["2D","3D"],
        key="mode",
        label_visibility="collapsed"
    )

    if view is None:
        view = "2D"

    try:
        texture = image_data(TEXTURE_URL)

        picked = MOON_PICKER(
            data={
                "texture": texture,
                "mode": view,
                "lat": st.session_state.lat,
                "lon": st.session_state.lon,
                "language": "ar" if arabic() else "en"
            },
            key="moon_picker_component",
            on_picked_change=lambda: None
        )

        event = getattr(picked,"picked",None)

        if event:
            nonce = event.get("nonce")

            if nonce != st.session_state.last_pick:
                st.session_state.last_pick = nonce
                apply_location(
                    event["lat"],
                    event["lon"]
                )
                st.rerun()

    except Exception as error:
        st.error(str(error))

    col1,col2 = st.columns(2)

    col1.metric(
        t("lat"),
        f"{st.session_state.lat:.5f}°"
    )
    col2.metric(
        t("lon"),
        f"{st.session_state.lon:.5f}°"
    )

    if st.session_state.lat > -75:
        st.info(
            "يمكنك استكشاف الموقع، لكن تركيز تحليل "
            "الهبوط في هذا المشروع على القطب الجنوبي."
            if arabic()
            else "You may explore this location, but "
                 "the mission focuses on the lunar south pole."
        )


# ==========================================================
# PAGE 2 — LANDER + SCAN
# ==========================================================

elif st.session_state.page == "surface":
    st.header(t("surface"))
    st.write(t("scanintro"))

    a,b = st.columns(2)
    a.metric(t("lat"),f"{st.session_state.lat:.5f}°")
    b.metric(t("lon"),f"{st.session_state.lon:.5f}°")

    signature = (
        st.session_state.lat,
        st.session_state.lon
    )

    if st.button(t("scan"),type="primary"):
        st.session_state.scan_result = None

        try:
            with st.spinner(t("nasa")):
                slope, dem, resolution = read_terrain_window(
                    st.session_state.lat,
                    st.session_state.lon
                )

            cells = classify_cells(slope)

            st.session_state.scan_result = {
                "signature":signature,
                "cells":cells,
                "resolution":resolution,
                "measured":True
            }

        except Exception as error:
            st.session_state.scan_result = {
                "signature":signature,
                "cells":classify_cells(None),
                "resolution":None,
                "measured":False,
                "error":str(error)
            }

    scan = st.session_state.scan_result

    if scan and scan["signature"] == signature:
        cells = scan["cells"]
    else:
        cells = classify_cells(None)

    try:
        render_scanner(cells)
    except Exception as error:
        st.error(str(error))

    st.info(t("scanlimit"))

    if scan and scan["signature"] == signature:
        if scan["measured"]:
            st.success(t("scanok"))

            st.caption(
                f"NASA LOLA / "
                f"{scan['resolution']:.0f} m per pixel"
            )

            valid = [
                x for x in cells
                if x["slope"] is not None
            ]

            if valid:
                best = min(
                    valid,
                    key=lambda item:item["slope"]
                )

                if arabic():
                    st.write(
                        f"**أقل انحدار مقاس:** الخلية "
                        f"{best['id']}، مؤشر الميل "
                        f"{best['slope']}°. "
                        "هذه نتيجة فرز أولي، وليست "
                        "توصية هبوط نهائية."
                    )
                else:
                    st.write(
                        f"**Lowest screening slope:** "
                        f"Cell {best['id']}, "
                        f"{best['slope']}°. "
                        "This is not a certified "
                        "landing recommendation."
                    )

            st.download_button(
                "تحميل بيانات المسح"
                if arabic()
                else "Download scan results",
                data=pd.DataFrame(cells).to_csv(
                    index=False
                ),
                file_name="OFOQ_scan.csv",
                mime="text/csv"
            )

        else:
            st.warning(t("scanbad"))

            with st.expander(
                "التفاصيل التقنية"
                if arabic()
                else "Technical details"
            ):
                st.code(scan.get("error",""))


# ==========================================================
# PAGE 3 — SUN & EARTH
# ==========================================================

elif st.session_state.page == "sun":
    st.header(t("sun"))

    mission_date = st.date_input(
        t("date"),
        value=date(2026,11,14)
    )

    hours = st.slider(
        t("hours"),
        24,96,48,12
    )

    signature = (
        st.session_state.lat,
        st.session_state.lon,
        mission_date,
        hours
    )

    if st.button(t("run"),type="primary"):
        try:
            start = datetime.combine(
                mission_date,
                datetime.min.time()
            )

            with st.spinner(t("nasa")):
                df = analyze(
                    st.session_state.lat,
                    st.session_state.lon,
                    start,
                    hours
                )

            st.session_state.visibility_result = (
                signature,df
            )

        except Exception as error:
            st.error(str(error))

    saved = st.session_state.visibility_result

    if saved and saved[0] == signature:
        show_results(saved[1])


# ==========================================================
# PAGE 4 — COMPARE
# ==========================================================

elif st.session_state.page == "compare":
    st.header(t("comparetitle"))

    mission_date = st.date_input(
        t("date"),
        value=date(2026,11,14),
        key="compare_date"
    )

    hours = st.slider(
        t("hours"),
        24,96,48,12,
        key="compare_hours"
    )

    comparison = st.radio(
        t("compare"),
        ["delay","site"],
        format_func=lambda x: (
            t("delaymode")
            if x=="delay"
            else t("sitemode")
        )
    )

    start_a = datetime.combine(
        mission_date,
        datetime.min.time()
    )

    start_b = start_a
    lat_b = st.session_state.lat
    lon_b = st.session_state.lon

    if comparison == "delay":
        delay = st.slider(
            t("delay"),
            0,168,48,24
        )

        start_b += timedelta(
            hours=delay
        )

    else:
        backup = st.session_state.backup

        if backup:
            lat_b,lon_b = backup
            st.info(
                f"{lat_b:.5f}°, {lon_b:.5f}°"
            )
        else:
            st.warning(
                "احفظ أولًا موقعًا بديلًا من القائمة "
                "الجانبية في صفحة استكشاف القمر."
                if arabic()
                else "Save a backup location from "
                     "the Explore page first."
            )

    if st.button(
        t("comparebutton"),
        type="primary",
        disabled=(
            comparison == "site"
            and st.session_state.backup is None
        )
    ):
        try:
            with st.spinner(t("nasa")):
                first = analyze(
                    st.session_state.lat,
                    st.session_state.lon,
                    start_a,
                    hours
                )

                second = analyze(
                    lat_b,lon_b,
                    start_b,
                    hours
                )

            n1 = numbers(first)
            n2 = numbers(second)

            left,right = st.columns(2)

            with left:
                st.subheader(t("original"))
                st.metric(t("sunhours"),f"{n1['Sun']} h")
                st.metric(t("earthhours"),f"{n1['Earth']} h")
                st.metric(t("bothhours"),f"{n1['Both']} h")

            with right:
                st.subheader(t("alternative"))
                st.metric(
                    t("sunhours"),
                    f"{n2['Sun']} h",
                    delta=n2["Sun"]-n1["Sun"]
                )
                st.metric(
                    t("earthhours"),
                    f"{n2['Earth']} h",
                    delta=n2["Earth"]-n1["Earth"]
                )
                st.metric(
                    t("bothhours"),
                    f"{n2['Both']} h",
                    delta=n2["Both"]-n1["Both"]
                )

            fig = go.Figure()

            fig.add_trace(go.Bar(
                x=list(n1),
                y=list(n1.values()),
                name=t("original"),
                marker_color="#616169"
            ))

            fig.add_trace(go.Bar(
                x=list(n2),
                y=list(n2.values()),
                name=t("alternative"),
                marker_color="#76C5F5"
            ))

            fig.update_layout(
                barmode="group",
                template="plotly_dark",
                paper_bgcolor="#081522",
                plot_bgcolor="#081522",
                font=dict(color="#DCEEFA"),
                height=380
            )

            st.plotly_chart(
                fig,
                use_container_width=True
            )

        except Exception as error:
            st.error(str(error))


# ==========================================================
# SOURCES
# ==========================================================

st.divider()

with st.expander(t("source")):
    st.markdown("""
**NASA Scientific Visualization Studio — Moon Kit**

https://svs.gsfc.nasa.gov/4720/

**NASA LRO / LOLA South Pole Terrain**

https://pgda.gsfc.nasa.gov/products/90

**NASA JPL Horizons**

https://ssd-api.jpl.nasa.gov/doc/horizons.html

**NASA Apollo 17 Lunar Photograph**

https://science.nasa.gov/moon/image-galleries/views-from-the-lunar-surface/

**Limitations**

- The camera background is an Apollo 17 reference photo.
- It is not the selected lunar landing site.
- Scanner cells are not geographically registered to
  the reference photograph.
- Measured slope cells refer to the selected coordinates.
- 5° and 12° are preliminary OFOQ screening thresholds.
- The scanner cannot detect all small rocks or craters.
- Geometric visibility does not ensure power or radio links.
- OFOQ does not certify a safe lunar landing.
""")

st.caption(
    "TEAM OFOQ | NASA SPACE APPS CHALLENGE 2026 | "
    "INDEPENDENT RESEARCH PROTOTYPE"
)
