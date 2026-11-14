import streamlit as st
import requests
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import rasterio
from pyproj import CRS, Transformer
from rasterio.windows import Window
from datetime import datetime, date, timedelta
from io import BytesIO
from PIL import Image
import base64


# ============================================================
# OFOQ v7 — LUNAR MISSION EXPLORER
# ============================================================

st.set_page_config(
    page_title="OFOQ | أُفُق",
    page_icon="🌙",
    layout="wide",
    initial_sidebar_state="expanded"
)

TEXTURE = (
    "https://svs.gsfc.nasa.gov/vis/a000000/"
    "a004700/a004720/lroc_color_2k.jpg"
)

# NASA Apollo 17 actual surface panorama.
# This is NOT the selected south-pole location.
PANORAMA = (
    "https://svs.gsfc.nasa.gov/vis/a000000/"
    "a004300/a004302/panorama_print.jpg"
)

NASA_SLOPE = (
    "https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/"
    "LDSM_80S_80MPP_ADJ.TIF"
)

HORIZONS = "https://ssd.jpl.nasa.gov/api/horizons.api"

LUNAR_CRS = CRS.from_proj4(
    "+proj=longlat +a=1737400 +b=1737400 "
    "+no_defs"
)

COLORS = {
    "space": "#050B16",
    "navy": "#10243A",
    "ice": "#76C5F5",
    "silver": "#DCECF7",
    "green": "#39AD84",
    "orange": "#E5A64B",
    "red": "#D46A70",
    "gray": "#657587"
}

# ============================================================
# APP STATE
# ============================================================

defaults = {
    "lang": "العربية",
    "page": "explore",
    "view": "2D",
    "lat": -89.0,
    "lon": 0.0,
    "backup": None,
    "last_pick": None,
    "scan": None,
    "visibility": None
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ============================================================
# BILINGUAL TEXT
# ============================================================

WORDS = {
    "explore": ("استكشف القمر", "Explore the Moon"),
    "scan": ("كاميرا المركبة والمسح", "Lander Camera & Scan"),
    "sun": ("الشمس والاتصال", "Sun & Communication"),
    "compare": ("المقارنة والخطة البديلة", "Compare & Plan B"),

    "choose": (
        "اضغط على القمر لاختيار المكان الذي تريد دراسته",
        "Click the Moon to select a location"
    ),
    "instructions": (
        "اضغط لاختيار نقطة، واسحب للتحريك، واستخدم "
        "عجلة الماوس للتكبير.",
        "Click to select, drag to move, and scroll to zoom."
    ),
    "selected": ("الموقع المختار", "Selected location"),
    "lat": ("خط العرض", "Latitude"),
    "lon": ("خط الطول", "Longitude"),

    "scanintro": (
        "شاهد سطح القمر من منظور مركبة افتراضية، "
        "وافحص الخلايا لمعرفة خصائص التضاريس.",
        "Explore a virtual lander perspective and "
        "inspect cells for terrain information."
    ),
    "startscan": ("ابدأ مسح التضاريس", "Start Terrain Scan"),
    "dataok": (
        "تم استخراج قياسات الانحدار من NASA.",
        "NASA slope measurements were retrieved."
    ),
    "datafail": (
        "لم تتوفر قياسات الانحدار لهذا الموقع. "
        "ستظهر الخلايا باللون الرمادي.",
        "Slope measurements are unavailable. "
        "Cells remain gray."
    ),
    "green": (
        "انحدار أقل ضمن معايير الفحص الأولي",
        "Lower slope in preliminary screening"
    ),
    "orange": (
        "انحدار متوسط يحتاج مراجعة",
        "Moderate slope — review needed"
    ),
    "red": (
        "انحدار مرتفع نسبيًا",
        "Relatively steep terrain"
    ),
    "gray": (
        "بيانات غير كافية",
        "Insufficient data"
    ),

    "date": ("تاريخ المهمة UTC", "Mission date UTC"),
    "duration": ("مدة المهمة بالساعات", "Mission duration in hours"),
    "calculate": ("احسب ظروف المهمة", "Calculate Mission Conditions"),
    "sunhours": ("ساعات ظهور الشمس", "Sun visibility"),
    "earthhours": ("ساعات ظهور الأرض", "Earth visibility"),
    "bothhours": ("ظهورهما معًا", "Both visible"),
    "chart": (
        "كيف يتغير ارتفاع الشمس والأرض؟",
        "How do Sun and Earth elevations change?"
    ),

    "comparetitle": (
        "ماذا يحدث إذا تغيرت خطة الهبوط؟",
        "What if the landing plan changes?"
    ),
    "delaymode": (
        "نفس الموقع، موعد مختلف",
        "Same site, different date"
    ),
    "sitemode": (
        "موقع آخر، نفس الموعد",
        "Different site, same date"
    ),
    "delay": ("التأخير بالساعات", "Delay in hours"),
    "runcompare": ("قارن الخطتين", "Compare Plans"),
    "original": ("الخطة الأصلية", "Original Plan"),
    "alternative": ("الخطة البديلة", "Alternative Plan"),
    "save": ("حفظ الموقع كبديل", "Save as Backup Site"),
    "sources": ("المصادر والحدود العلمية", "Sources and Limitations"),
}


def t(key):
    item = WORDS.get(key, (key, key))
    return item[0] if st.session_state.lang == "العربية" else item[1]


def ar():
    return st.session_state.lang == "العربية"


def select_site(lat, lon):
    lat = max(-90.0, min(90.0, float(lat)))
    lon = ((float(lon) + 180) % 360) - 180

    st.session_state.lat = round(lat, 5)
    st.session_state.lon = round(lon, 5)
    st.session_state.scan = None
    st.session_state.visibility = None


# ============================================================
# NASA IMAGE LOADING
# ============================================================

@st.cache_data(ttl=86400, show_spinner=False)
def load_image(url):
    response = requests.get(url, timeout=40)
    response.raise_for_status()

    image = Image.open(BytesIO(response.content)).convert("RGB")

    buf = BytesIO()
    image.save(buf, format="JPEG", quality=88)

    return (
        "data:image/jpeg;base64,"
        + base64.b64encode(buf.getvalue()).decode()
    )


# ============================================================
# VISUAL THEME
# ============================================================

st.markdown("""
<style>
.stApp {
    background:
      radial-gradient(
        circle at 80% 0%,
        #17324A 0%,
        #081522 40%,
        #050B16 80%
      ) !important;
    color: #DCECF7;
}

[data-testid="stHeader"] {
    background: transparent !important;
}

[data-testid="stSidebar"] {
    background: #081522 !important;
    border-right: 1px solid #32516C;
}

.block-container {
    max-width: 1550px;
    padding-top: 1.1rem;
}

h1, h2, h3, p, label {
    color: #DCECF7 !important;
}

[data-testid="stSidebar"] [data-testid="stButton"] button {
    min-height: 66px !important;
    padding: 13px 17px !important;
    font-size: 15px !important;
    font-weight: 700 !important;
    text-align: start !important;
}

[data-testid="stButton"] button {
    background: #10243A !important;
    color: #DCECF7 !important;
    border: 1px solid #345A78 !important;
    border-radius: 14px !important;
    transition: 0.15s ease;
}

[data-testid="stButton"] button:hover {
    border-color: #76C5F5 !important;
    background: #183954 !important;
}

[data-testid="stButton"] button[kind="primary"] {
    background: #76C5F5 !important;
    color: #050B16 !important;
}

[data-testid="stMetric"] {
    background: #10243A;
    border: 1px solid #345A78;
    padding: 17px;
    border-radius: 15px;
}

[data-testid="stMetricValue"] {
    color: #DCECF7;
}

.ofoq-hero {
    position: relative;
    border: 1px solid #3D6481;
    border-radius: 23px;
    padding: 30px 36px;
    margin-bottom: 19px;
    background:
      radial-gradient(
        circle at 82% 36%,
        #76C5F533,
        transparent 28%
      ),
      linear-gradient(120deg, #050B16, #10243A);
    box-shadow: 0 17px 52px #00000050;
}

.ofoq-hero h1 {
    font-size: clamp(38px, 5vw, 65px);
    margin: 7px 0;
    font-weight: 850;
    letter-spacing: 3px;
    text-shadow: 0 0 25px #76C5F52E;
}

.ofoq-eyebrow {
    color: #76C5F5;
    letter-spacing: 2px;
    font-weight: 700;
    font-size: 12px;
}

.ofoq-arc {
    width: 230px;
    height: 34px;
    border-top: 2px solid #76C5F5;
    border-radius: 50% 50% 0 0;
}

.ofoq-card {
    padding: 17px;
    border: 1px solid #345A78;
    background: #10243A;
    border-radius: 16px;
}

.legend {
    display: flex;
    flex-wrap: wrap;
    gap: 15px;
    padding: 14px;
    background: #10243A;
    border: 1px solid #345A78;
    border-radius: 13px;
    margin: 12px 0;
}

.legend span {
    color: #DCECF7;
    font-size: 13px;
}

.legend b {
    display: inline-block;
    width: 12px;
    height: 12px;
    margin-inline-end: 6px;
    border-radius: 3px;
}

hr {
    border-color: #345A78 !important;
}
</style>
""", unsafe_allow_html=True)


# ============================================================
# LARGE SIDE NAVIGATION
# ============================================================

with st.sidebar:
    st.markdown("## أُفُق | OFOQ")
    st.caption("BEYOND THE HORIZON")

    st.selectbox(
        "Language",
        ["العربية", "English"],
        key="lang",
        label_visibility="collapsed"
    )

    st.divider()

    sections = [
        ("explore", "◉", "explore"),
        ("scan", "▦", "scan"),
        ("sun", "☼", "sun"),
        ("compare", "◇", "compare")
    ]

    for key, symbol, name in sections:
        if st.button(
            f"{symbol}  {t(name)}",
            key=f"nav_{key}",
            type="primary" if st.session_state.page == key else "secondary",
            use_container_width=True
        ):
            st.session_state.page = key
            st.rerun()

    st.divider()

    st.caption(t("selected"))
    st.write(f"**{t('lat')}:** {st.session_state.lat:.5f}°")
    st.write(f"**{t('lon')}:** {st.session_state.lon:.5f}°")

    if st.button(t("save"), use_container_width=True):
        st.session_state.backup = (
            st.session_state.lat,
            st.session_state.lon
        )
        st.success("✓")


# ============================================================
# OFOQ HERO
# ============================================================

st.markdown(
    f"""
    <div class="ofoq-hero"
         dir="{'rtl' if ar() else 'ltr'}">
      <div class="ofoq-eyebrow">
        NASA SPACE APPS CHALLENGE 2026
      </div>
      <div class="ofoq-arc"></div>
      <h1>أُفُق | OFOQ</h1>
      <div class="ofoq-eyebrow">
        BEYOND THE HORIZON, TOWARD THE MOON.
      </div>
      <p>
        {"استكشف القمر، واختر موقعًا، وافهم "
         "ظروف المهمة باستخدام بيانات NASA."
         if ar()
         else "Explore the Moon, select a site, "
              "and understand mission conditions using NASA data."}
      </p>
    </div>
    """,
    unsafe_allow_html=True
)


# ============================================================
# ONE MOON VIEWER — EXACTLY ONE CANVAS
# 2D and 3D are completely separate modes.
# ============================================================

MOON_HTML = """
<div class="moon-viewer">
    <div class="moon-stage"></div>
    <div class="moon-hint"></div>
</div>
"""

MOON_CSS = """
.moon-viewer {
    width: 100%;
    border: 1px solid #345A78;
    background: #050B16;
    border-radius: 17px;
    overflow: hidden;
    position: relative;
}

.moon-stage {
    position: relative;
    width: 100%;
    min-height: 500px;
    background: #050B16;
}

.moon-stage canvas {
    display: block;
    width: 100%;
    height: auto;
    cursor: crosshair;
    touch-action: none;
}

.moon-hint {
    position: absolute;
    bottom: 13px;
    left: 13px;
    padding: 11px 14px;
    border-radius: 10px;
    background: #081522E8;
    border: 1px solid #345A78;
    color: #DCECF7;
    font: 13px Arial;
    pointer-events: none;
}
"""

MOON_JS = """
export default function(component) {
    const { data, parentElement, setTriggerValue } = component;

    const stage = parentElement.querySelector(".moon-stage");
    const hint = parentElement.querySelector(".moon-hint");

    // Crucial: remove any old canvas before rendering.
    stage.replaceChildren();

    let disposed = false;
    let cleanup = () => {};

    hint.textContent = data.ar
      ? "اضغط للاختيار • اسحب للتحريك • حرّك العجلة للتكبير"
      : "Click to select • Drag to move • Scroll to zoom";

    function choose(lat, lon) {
      lat = Math.max(-90, Math.min(90, lat));
      lon = ((lon + 180) % 360 + 360) % 360 - 180;

      setTriggerValue("picked", {
        lat: Number(lat.toFixed(5)),
        lon: Number(lon.toFixed(5)),
        id: Date.now() + Math.random()
      });
    }

    // =====================================================
    // 2D VIEW: one NASA image on a single Canvas.
    // Zoom and drag DO NOT create new images.
    // =====================================================

    if (data.mode === "2D") {
      const canvas = document.createElement("canvas");
      canvas.width = 1200;
      canvas.height = 600;
      stage.appendChild(canvas);

      const ctx = canvas.getContext("2d");
      const image = new Image();

      let zoom = 1;
      let centerX = 1024;
      let centerY = 512;
      let down = null;
      let moved = false;

      function viewport() {
        const iw = image.naturalWidth;
        const ih = image.naturalHeight;

        const vw = iw / zoom;
        const vh = ih / zoom;

        const left = Math.max(
          0, Math.min(iw-vw, centerX-vw/2)
        );
        const top = Math.max(
          0, Math.min(ih-vh, centerY-vh/2)
        );

        return {left, top, vw, vh};
      }

      function paint() {
        if (!image.naturalWidth) return;

        const v = viewport();

        ctx.clearRect(0,0,1200,600);
        ctx.fillStyle = "#050B16";
        ctx.fillRect(0,0,1200,600);

        ctx.drawImage(
          image,
          v.left, v.top, v.vw, v.vh,
          0, 0, 1200, 600
        );

        const ix = (data.lon+180)/360 * image.width;
        const iy = (90-data.lat)/180 * image.height;

        const x = (ix-v.left)/v.vw * 1200;
        const y = (iy-v.top)/v.vh * 600;

        if(x>=0 && x<=1200 && y>=0 && y<=600) {
          ctx.strokeStyle = "#76C5F5";
          ctx.fillStyle = "#DCECF7";
          ctx.lineWidth = 4;

          ctx.beginPath();
          ctx.arc(x,y,14,0,Math.PI*2);
          ctx.stroke();

          ctx.beginPath();
          ctx.arc(x,y,5,0,Math.PI*2);
          ctx.fill();
        }
      }

      image.onload = () => {
        centerX = (data.lon+180)/360 * image.width;
        centerY = (90-data.lat)/180 * image.height;
        paint();
      };

      image.src = data.texture;

      function point(e) {
        const r = canvas.getBoundingClientRect();
        return {
          x: (e.clientX-r.left)/r.width*1200,
          y: (e.clientY-r.top)/r.height*600
        };
      }

      function start(e) {
        down = {
          ...point(e),
          cx:centerX,
          cy:centerY
        };

        moved = false;
        canvas.setPointerCapture(e.pointerId);
      }

      function move(e) {
        if(!down || !image.naturalWidth) return;

        const p = point(e);
        const dx = p.x-down.x;
        const dy = p.y-down.y;

        if(Math.hypot(dx,dy)>5) moved=true;

        if(moved) {
          centerX = down.cx - dx/1200*image.width/zoom;
          centerY = down.cy - dy/600*image.height/zoom;
          paint();
        }
      }

      function end(e) {
        if(!down || !image.naturalWidth) return;

        if(!moved) {
          const p = point(e);
          const v = viewport();

          const ix = v.left + p.x/1200*v.vw;
          const iy = v.top + p.y/600*v.vh;

          const lon = ix/image.width*360-180;
          const lat = 90-iy/image.height*180;

          // Update marker immediately in this canvas.
          data.lat = lat;
          data.lon = lon;
          paint();
          choose(lat,lon);
        }

        down = null;
        moved = false;
      }

      function wheel(e) {
        e.preventDefault();

        zoom = Math.max(
          1, Math.min(8,
          zoom*(e.deltaY<0?1.2:1/1.2))
        );

        paint();
      }

      canvas.addEventListener("pointerdown", start);
      canvas.addEventListener("pointermove", move);
      canvas.addEventListener("pointerup", end);
      canvas.addEventListener("wheel", wheel, {passive:false});

      cleanup = () => {
        canvas.removeEventListener("pointerdown", start);
        canvas.removeEventListener("pointermove", move);
        canvas.removeEventListener("pointerup", end);
        canvas.removeEventListener("wheel", wheel);
      };

    } else {

      // ===================================================
      // 3D VIEW: one genuinely interactive Three.js globe.
      // ===================================================

      (async () => {
        try {
          const THREE = await import(
            "https://esm.sh/three@0.160.0"
          );

          const addon = await import(
            "https://esm.sh/three@0.160.0/examples/jsm/controls/OrbitControls.js"
          );

          if(disposed) return;

          const scene = new THREE.Scene();
          scene.background = new THREE.Color(0x050B16);

          const camera = new THREE.PerspectiveCamera(
            44,1,.1,100
          );
          camera.position.set(0,0,4.8);

          const renderer = new THREE.WebGLRenderer({
            antialias:true
          });

          renderer.setPixelRatio(
            Math.min(devicePixelRatio,2)
          );
          stage.appendChild(renderer.domElement);

          const tex = new THREE.TextureLoader().load(
            data.texture
          );
          tex.colorSpace = THREE.SRGBColorSpace;

          const moon = new THREE.Mesh(
            new THREE.SphereGeometry(1.65,96,64),
            new THREE.MeshStandardMaterial({
              map:tex, roughness:1
            })
          );

          scene.add(moon);
          scene.add(
            new THREE.AmbientLight(0xffffff,1.5)
          );

          const light = new THREE.DirectionalLight(
            0xDCECF7,2
          );
          light.position.set(4,3,6);
          scene.add(light);

          const controls = new addon.OrbitControls(
            camera,renderer.domElement
          );

          controls.enableDamping = true;
          controls.enablePan = false;
          controls.minDistance = 2.1;
          controls.maxDistance = 8;

          const marker = new THREE.Mesh(
            new THREE.SphereGeometry(.045,16,16),
            new THREE.MeshBasicMaterial({
              color:0x76C5F5
            })
          );

          function updateMarker(lat,lon) {
            const u = (lon+180)/360;
            const phi = u*Math.PI*2;
            const a = lat*Math.PI/180;

            marker.position.set(
              -1.7*Math.cos(phi)*Math.cos(a),
               1.7*Math.sin(a),
               1.7*Math.sin(phi)*Math.cos(a)
            );
          }

          updateMarker(data.lat,data.lon);
          scene.add(marker);

          let down = null;
          const raycaster = new THREE.Raycaster();
          const mouse = new THREE.Vector2();

          function pointerDown(e) {
            down={x:e.clientX,y:e.clientY};
          }

          function pointerUp(e) {
            if(!down) return;

            const distance = Math.hypot(
              e.clientX-down.x,
              e.clientY-down.y
            );
            down=null;

            if(distance>6) return;

            const rect =
              renderer.domElement.getBoundingClientRect();

            mouse.x = (
              (e.clientX-rect.left)/rect.width
            )*2-1;

            mouse.y = -(
              (e.clientY-rect.top)/rect.height
            )*2+1;

            raycaster.setFromCamera(mouse,camera);
            const hits = raycaster.intersectObject(moon);

            if(!hits.length || !hits[0].uv) return;

            const uv = hits[0].uv;
            const lon = uv.x*360-180;
            const lat = uv.y*180-90;

            updateMarker(lat,lon);
            choose(lat,lon);
          }

          renderer.domElement.addEventListener(
            "pointerdown",pointerDown
          );
          renderer.domElement.addEventListener(
            "pointerup",pointerUp
          );

          function resize() {
            const w=stage.clientWidth||900;
            renderer.setSize(w,520);
            camera.aspect=w/520;
            camera.updateProjectionMatrix();
          }

          const observer=new ResizeObserver(resize);
          observer.observe(stage);
          resize();

          let frame=null;

          function animate() {
            if(disposed) return;
            frame=requestAnimationFrame(animate);
            controls.update();
            renderer.render(scene,camera);
          }

          animate();

          cleanup=()=>{
            observer.disconnect();
            if(frame) cancelAnimationFrame(frame);
            controls.dispose();
            renderer.dispose();
            tex.dispose();
          };

        } catch(err) {
          hint.textContent = "3D error: "+String(err);
        }
      })();
    }

    return ()=>{
      disposed=true;
      cleanup();
      stage.replaceChildren();
    };
}
"""

MOON_VIEWER = st.components.v2.component(
    "ofoq_single_moon_viewer_v7",
    html=MOON_HTML,
    css=MOON_CSS,
    js=MOON_JS
)


# ============================================================
# REAL NASA SLOPE DATA — CONDITIONAL
# ============================================================

@st.cache_data(ttl=3600, show_spinner=False)
def get_slope(lat,lon):
    if lat > -80:
        raise ValueError(
            "The data covers 80–90° south."
        )

    with rasterio.Env(
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        GDAL_HTTP_TIMEOUT="20",
        GDAL_HTTP_MAX_RETRY="1"
    ):
        with rasterio.open(
            "/vsicurl/"+NASA_SLOPE
        ) as src:

            if src.crs is None:
                raise ValueError("Missing raster CRS")

            transform = Transformer.from_crs(
                LUNAR_CRS,
                src.crs,
                always_xy=True
            )

            x,y = transform.transform(lon,lat)
            row,col = src.index(x,y)

            half = 32

            if not (
                half<=row<src.height-half
                and half<=col<src.width-half
            ):
                raise ValueError(
                    "Location outside source image"
                )

            window=Window(
                col-half,
                row-half,
                64,64
            )

            a=src.read(
                1,
                window=window,
                masked=True
            )

            slope=np.ma.array(
                a,dtype=float
            ).filled(np.nan)

            resolution=max(
                abs(src.transform.a),
                abs(src.transform.e)
            )

            return slope,resolution


def make_scan_cells(slope=None):
    cells=[]

    for r in range(8):
        for c in range(8):
            item={
                "id":f"{r+1}-{c+1}",
                "status":"unknown",
                "slope":None,
                "coverage":0
            }

            if slope is not None:
                block=slope[
                    r*8:(r+1)*8,
                    c*8:(c+1)*8
                ]

                values=block[
                    np.isfinite(block)
                ]

                coverage=len(values)/block.size
                item["coverage"]=round(
                    coverage*100,1
                )

                if coverage>=.75:
                    value=float(
                        np.percentile(values,90)
                    )

                    item["slope"]=round(value,2)

                    if value<=5:
                        item["status"]="low"
                    elif value<=12:
                        item["status"]="medium"
                    else:
                        item["status"]="high"

            cells.append(item)

    return cells


# ============================================================
# NASA SURFACE PHOTO + ANIMATED SCAN
# ============================================================

SCANNER_HTML = """
<div class="scan-root">
  <div class="scan-scene">
    <div class="scan-photo"></div>
    <div class="scan-grid"></div>
    <div class="scan-beam"></div>
    <div class="scan-badge"></div>
    <div class="scan-controls">
      <button class="scan-left">◀</button>
      <button class="scan-right">▶</button>
    </div>
    <div class="scan-details"></div>
  </div>
</div>
"""

SCANNER_CSS = """
.scan-scene {
  height: 535px;
  position: relative;
  overflow: hidden;
  border-radius: 18px;
  background: #050B16;
  border: 1px solid #345A78;
  font-family: Arial,sans-serif;
}

.scan-photo {
  position:absolute;
  inset:0;
  background-size:auto 100%;
  background-repeat:no-repeat;
  background-position:50% center;
  filter:contrast(1.12) brightness(.83);
}

.scan-grid {
  position:absolute;
  left:17%;
  right:17%;
  top:38%;
  bottom:11%;
  display:grid;
  grid-template-columns:repeat(8,1fr);
  grid-template-rows:repeat(8,1fr);
  transform:perspective(570px) rotateX(24deg);
  gap:2px;
  z-index:3;
}

.scan-cell {
  border:1px solid #DCECF7C0;
  background:rgba(101,117,135,.24);
  cursor:pointer;
  font-size:0;
}

.scan-cell.low {
  background:rgba(57,173,132,.45);
}

.scan-cell.medium {
  background:rgba(229,166,75,.48);
}

.scan-cell.high {
  background:rgba(212,106,112,.51);
}

.scan-cell.unknown {
  background:rgba(101,117,135,.27);
}

.scan-cell:hover {
  outline:2px solid #DCECF7;
  filter:brightness(1.4);
}

.scan-beam {
  position:absolute;
  left:14%;
  right:14%;
  top:38%;
  height:3px;
  background:#76C5F5;
  box-shadow:0 0 25px #76C5F5;
  z-index:4;
  pointer-events:none;
  animation:scanmove 4s linear infinite;
}

@keyframes scanmove {
  from {top:38%}
  to {top:90%}
}

.scan-badge {
  position:absolute;
  left:16px;
  top:16px;
  padding:11px 15px;
  border-radius:10px;
  background:#081522E8;
  border:1px solid #345A78;
  color:#DCECF7;
  font-size:12px;
  z-index:7;
}

.scan-controls {
  position:absolute;
  left:16px;
  bottom:16px;
  display:flex;
  gap:8px;
  z-index:8;
}

.scan-controls button {
  width:45px;
  height:40px;
  background:#10243A;
  color:#DCECF7;
  border:1px solid #76C5F5;
  border-radius:10px;
  cursor:pointer;
}

.scan-details {
  position:absolute;
  bottom:16px;
  right:16px;
  width:min(350px,46%);
  padding:14px;
  line-height:1.7;
  border-radius:12px;
  border:1px solid #345A78;
  background:#081522E8;
  color:#DCECF7;
  font-size:13px;
  z-index:8;
}
"""

SCANNER_JS = """
export default function(component) {
  const {data,parentElement} = component;

  const scene=parentElement.querySelector(".scan-scene");
  const photo=scene.querySelector(".scan-photo");
  const grid=scene.querySelector(".scan-grid");
  const details=scene.querySelector(".scan-details");
  const badge=scene.querySelector(".scan-badge");

  // Prevent duplicate cells on subsequent reruns.
  grid.replaceChildren();

  photo.style.backgroundImage="url("+data.photo+")";

  badge.textContent="OFOQ / LUNAR TERRAIN SCAN";

  let position=50;

  const updatePhoto=()=>{
    photo.style.backgroundPosition=position+"% center";
  };

  scene.querySelector(".scan-left").onclick=()=>{
    position=Math.max(0,position-15);
    updatePhoto();
  };

  scene.querySelector(".scan-right").onclick=()=>{
    position=Math.min(100,position+15);
    updatePhoto();
  };

  details.textContent=data.ar
    ? "اضغط على أي مربع لعرض معلوماته"
    : "Click any cell to inspect its measurements";

  data.cells.forEach(cell=>{
    const button=document.createElement("button");
    button.className="scan-cell "+cell.status;
    button.title="Cell "+cell.id;

    button.onclick=()=>{
      const value=cell.slope===null
        ? (data.ar?"غير متاح":"Unavailable")
        : cell.slope+"°";

      details.textContent=data.ar
        ? "الخلية "+cell.id+
          " | مؤشر الانحدار: "+value+
          " | البيانات الصالحة: "+cell.coverage+"%"
        : "Cell "+cell.id+
          " | Slope P90: "+value+
          " | Valid coverage: "+cell.coverage+"%";
    };

    grid.appendChild(button);
  });

  return ()=>{
    grid.replaceChildren();
  };
}
"""

SCANNER = st.components.v2.component(
    "ofoq_surface_scanner_v7",
    html=SCANNER_HTML,
    css=SCANNER_CSS,
    js=SCANNER_JS
)


# ============================================================
# NASA HORIZONS
# ============================================================

@st.cache_data(ttl=3600,show_spinner=False)
def horizons(body,lat,lon,start_text,hours):
    start=datetime.strptime(
        start_text,"%Y-%m-%d %H:%M"
    )
    end=start+timedelta(hours=hours)

    params={
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

    response=requests.get(
        HORIZONS,params=params,timeout=60
    )
    response.raise_for_status()

    text=response.json()["result"]

    if "$$SOE" not in text or "$$EOE" not in text:
        raise ValueError(text[:350])

    block=text.split("$$SOE")[1].split("$$EOE")[0]
    rows=[]

    for line in block.splitlines():
        parts=[p.strip() for p in line.split(",")]

        if len(parts)<5:
            continue

        try:
            rows.append({
                "time":pd.to_datetime(
                    parts[0],format="%Y-%b-%d %H:%M"
                ),
                "elevation":float(parts[4])
            })
        except ValueError:
            continue

    if not rows:
        raise ValueError("No numeric ephemeris data")

    return pd.DataFrame(rows)


def analyze(lat,lon,start,hours):
    text=start.strftime("%Y-%m-%d %H:%M")

    sun=horizons("10",lat,lon,text,hours)
    earth=horizons("399",lat,lon,text,hours)

    df=sun.merge(
        earth,
        on="time",
        suffixes=("_sun","_earth")
    ).sort_values("time")

    df=df.iloc[:-1].copy()

    if len(df)!=hours:
        raise ValueError(
            "Incomplete hourly ephemeris"
        )

    df["Sun"]=df.elevation_sun>0
    df["Earth"]=df.elevation_earth>0
    df["Both"]=df.Sun & df.Earth

    return df


def metrics(df):
    return {
        "Sun":int(df.Sun.sum()),
        "Earth":int(df.Earth.sum()),
        "Both":int(df.Both.sum())
    }


def show_chart(df):
    n=metrics(df)

    a,b,c=st.columns(3)
    a.metric(t("sunhours"),f"{n['Sun']} h")
    b.metric(t("earthhours"),f"{n['Earth']} h")
    c.metric(t("bothhours"),f"{n['Both']} h")

    fig=go.Figure()

    fig.add_trace(go.Scatter(
        x=df.time,
        y=df.elevation_sun,
        name="Sun",
        line=dict(
            color="#DCECF7",width=3
        )
    ))

    fig.add_trace(go.Scatter(
        x=df.time,
        y=df.elevation_earth,
        name="Earth",
        line=dict(
            color="#76C5F5",width=3
        )
    ))

    fig.add_hline(
        y=0,
        line_dash="dash",
        line_color="#657587"
    )

    fig.update_layout(
        title=t("chart"),
        template="plotly_dark",
        paper_bgcolor="#081522",
        plot_bgcolor="#081522",
        font=dict(color="#DCECF7"),
        xaxis_title="UTC",
        yaxis_title="Elevation (°)",
        height=410
    )

    st.plotly_chart(fig,use_container_width=True)


# ============================================================
# PAGE 1 — EXPLORE
# ============================================================

if st.session_state.page=="explore":
    st.header(t("explore"))
    st.write(t("choose"))
    st.caption(t("instructions"))

    a,b=st.columns(2)

    with a:
        if st.button(
            "◧  2D MAP",
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
            "◉  3D MOON",
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
        texture=load_image(TEXTURE)

        result=MOON_VIEWER(
            data={
                "mode":st.session_state.view,
                "texture":texture,
                "lat":st.session_state.lat,
                "lon":st.session_state.lon,
                "ar":ar()
            },
            key="ofoq_one_moon",
            on_picked_change=lambda:None
        )

        point=getattr(result,"picked",None)

        if point and point.get("id") != st.session_state.last_pick:
            st.session_state.last_pick=point["id"]
            select_site(
                point["lat"],
                point["lon"]
            )
            st.rerun()

    except Exception as error:
        st.error(str(error))

    left,right=st.columns(2)

    left.metric(
        t("lat"),f"{st.session_state.lat:.5f}°"
    )
    right.metric(
        t("lon"),f"{st.session_state.lon:.5f}°"
    )


# ============================================================
# PAGE 2 — COMBINED LANDER CAMERA + SCAN
# ============================================================

elif st.session_state.page=="scan":
    st.header(t("scan"))
    st.write(t("scanintro"))

    signature=(
        st.session_state.lat,
        st.session_state.lon
    )

    if st.button(t("startscan"),type="primary"):
        try:
            with st.spinner("NASA LOLA"):
                slope,resolution=get_slope(
                    *signature
                )

            st.session_state.scan={
                "site":signature,
                "measured":True,
                "cells":make_scan_cells(slope),
                "resolution":resolution
            }

        except Exception as error:
            st.session_state.scan={
                "site":signature,
                "measured":False,
                "cells":make_scan_cells(None),
                "error":str(error)
            }

    scan=st.session_state.scan

    if scan and scan["site"]==signature:
        cells=scan["cells"]
    else:
        cells=make_scan_cells(None)

    try:
        photo=load_image(PANORAMA)

        SCANNER(
            data={
                "photo":photo,
                "cells":cells,
                "ar":ar()
            },
            key="ofoq_unified_scanner"
        )

    except Exception as error:
        st.error(str(error))

    # The legend uses red only for terrain hazard,
    # never for navigation or selection.
    st.markdown(
        f"""
        <div class="legend">
          <span><b style="background:#39AD84"></b>{t('green')}</span>
          <span><b style="background:#E5A64B"></b>{t('orange')}</span>
          <span><b style="background:#D46A70"></b>{t('red')}</span>
          <span><b style="background:#657587"></b>{t('gray')}</span>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.caption(
        "الصورة بانوراما حقيقية من موقع Apollo 17، "
        "وليست صورة للموقع الذي اخترته. أما قيم "
        "الخلايا فتُحسب من إحداثياتك عند نجاح "
        "تحميل NASA LOLA. المسح فحص أولي فقط."
        if ar()
        else "The panoramic image shows Apollo 17, "
             "not the selected site. Cell measurements "
             "refer to your selected coordinates when "
             "NASA LOLA data is available. "
             "This is preliminary screening only."
    )

    if scan and scan["site"]==signature:
        if scan["measured"]:
            st.success(t("dataok"))

            st.caption(
                f"NASA LOLA — {scan['resolution']:.0f} m/pixel"
            )

            st.download_button(
                "Download CSV",
                pd.DataFrame(cells).to_csv(index=False),
                file_name="OFOQ_scan.csv",
                mime="text/csv"
            )
        else:
            st.warning(t("datafail"))

            with st.expander("Technical details"):
                st.code(scan.get("error",""))


# ============================================================
# PAGE 3 — SUN AND EARTH
# ============================================================

elif st.session_state.page=="sun":
    st.header(t("sun"))

    mission_date=st.date_input(
        t("date"),
        value=date(2026,11,14)
    )

    duration=st.number_input(
        t("duration"),
        min_value=12,
        max_value=168,
        value=48,
        step=12
    )

    signature=(
        st.session_state.lat,
        st.session_state.lon,
        mission_date,
        duration
    )

    if st.button(t("calculate"),type="primary"):
        try:
            start=datetime.combine(
                mission_date,
                datetime.min.time()
            )

            with st.spinner("NASA Horizons"):
                df=analyze(
                    st.session_state.lat,
                    st.session_state.lon,
                    start,
                    duration
                )

            st.session_state.visibility=(
                signature,df
            )

        except Exception as error:
            st.error(str(error))

    saved=st.session_state.visibility

    if saved and saved[0]==signature:
        show_chart(saved[1])

        st.caption(
            "تقديرات هندسية لكل ساعة؛ لا تشمل "
            "حجب الجبال أو كفاءة الاتصال الفعلية."
            if ar()
            else "Hourly geometric estimates. "
                 "Terrain blockage and real "
                 "communication performance are excluded."
        )


# ============================================================
# PAGE 4 — COMPARE
# ============================================================

elif st.session_state.page=="compare":
    st.header(t("comparetitle"))

    mission_date=st.date_input(
        t("date"),
        date(2026,11,14),
        key="compare_date"
    )

    duration=st.number_input(
        t("duration"),
        12,168,48,12,
        key="compare_duration"
    )

    mode=st.selectbox(
        "Comparison",
        ["delay","site"],
        format_func=lambda x:(
            t("delaymode")
            if x=="delay"
            else t("sitemode")
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
        delay=st.number_input(
            t("delay"),
            0,168,48,12
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
                "احفظ موقعًا بديلًا من قائمة الاستكشاف."
                if ar()
                else "Save a backup site from Explore."
            )

    if st.button(
        t("runcompare"),
        type="primary",
        disabled=(
            mode=="site"
            and st.session_state.backup is None
        )
    ):
        try:
            with st.spinner("NASA Horizons"):
                first=analyze(
                    st.session_state.lat,
                    st.session_state.lon,
                    start_a,duration
                )

                second=analyze(
                    lat_b,lon_b,
                    start_b,duration
                )

            n1=metrics(first)
            n2=metrics(second)

            a,b=st.columns(2)

            with a:
                st.subheader(t("original"))
                for name,value in n1.items():
                    st.metric(name,f"{value} h")

            with b:
                st.subheader(t("alternative"))
                for name,value in n2.items():
                    st.metric(
                        name,
                        f"{value} h",
                        delta=value-n1[name]
                    )

            fig=go.Figure()

            fig.add_trace(go.Bar(
                x=list(n1),
                y=list(n1.values()),
                name=t("original"),
                marker_color="#657587"
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
                height=360
            )

            st.plotly_chart(
                fig,use_container_width=True
            )

        except Exception as error:
            st.error(str(error))


# ============================================================
# SOURCES AND LIMITATIONS
# ============================================================

st.divider()

with st.expander(t("sources")):
    st.markdown("""
**NASA Scientific Visualization Studio — CGI Moon Kit**

https://svs.gsfc.nasa.gov/4720/

**NASA Apollo 17 Panorama**

https://svs.gsfc.nasa.gov/4302/

**NASA LOLA South Pole Topography**

https://pgda.gsfc.nasa.gov/products/90

**NASA JPL Horizons**

https://ssd-api.jpl.nasa.gov/doc/horizons.html

**Scientific limitations**

- Scanner colors are preliminary slope-screening categories.
- 5° and 12° thresholds are OFOQ prototype choices.
- The Apollo photograph is not the selected site.
- The grid is a visual overlay, not georegistered to the photograph.
- Small rocks and craters can be unresolved.
- Geometric Sun/Earth visibility is not a guarantee of
  electrical power or radio communication.
- OFOQ does not certify a safe landing site.
""")

st.caption(
    "TEAM OFOQ | NASA SPACE APPS CHALLENGE 2026 | "
    "INDEPENDENT EDUCATIONAL PROTOTYPE"
)
