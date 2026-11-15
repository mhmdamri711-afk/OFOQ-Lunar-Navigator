import base64
import json
from io import BytesIO
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import requests
import rasterio
import streamlit as st
import streamlit.components.v1 as components
import plotly.graph_objects as go

from PIL import Image, ImageEnhance
from pyproj import CRS, Transformer
from rasterio.windows import Window


# ==========================================================
# OFOQ v10 — LUNAR MISSION NAVIGATOR
# ==========================================================

st.set_page_config(
    page_title="أُفُق | OFOQ",
    page_icon="🌙",
    layout="wide",
    initial_sidebar_state="expanded"
)

MOON_URL = (
    "https://svs.gsfc.nasa.gov/vis/a000000/"
    "a004700/a004720/lroc_color_2k.jpg"
)

DATA_BASE = (
    "https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/"
)

SLOPE_URL = DATA_BASE + "LDSM_80S_80MPP_ADJ.TIF"
DEM_URL = DATA_BASE + "LDEM_80S_80MPP_ADJ.TIF"

HORIZONS_URL = (
    "https://ssd.jpl.nasa.gov/api/horizons.api"
)

MOON_CRS = CRS.from_proj4(
    "+proj=longlat +a=1737400 +b=1737400 "
    "+no_defs"
)

C = {
    "space": "#050B16",
    "navy": "#10243A",
    "ice": "#76C5F5",
    "silver": "#DCECF7",
    "green": "#35B77A",
    "yellow": "#E3B84E",
    "red": "#D96868",
    "gray": "#6D7A8A"
}


# ==========================================================
# STATE
# ==========================================================

defaults = {
    "language": "العربية",
    "page": "explore",
    "moon_view": "2D",
    "lander_view": "camera",
    "lat": -89.0,
    "lon": 0.0,
    "last_pick": None,
    "backup": None,
    "mission_result": None
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ==========================================================
# TRANSLATION
# ==========================================================

WORDS = {
    "explore": ("استكشف القمر", "Explore the Moon"),
    "views": ("كاميرا الهبوط", "Landing Camera"),
    "sun": ("الشمس والأرض", "Sun & Earth"),
    "compare": ("الخطة البديلة", "Mission Plan B"),
    "site": ("الموقع المختار", "Selected location"),
    "lat": ("خط العرض", "Latitude"),
    "lon": ("خط الطول", "Longitude"),
    "save": ("حفظ موقع بديل", "Save backup site"),
    "choose": (
        "اضغط على القمر لتحديد موقع الدراسة",
        "Click the Moon to select a location"
    ),
    "camera": (
        "رؤية الكاميرا من الأعلى",
        "Top-down Camera View"
    ),
    "side": (
        "رؤية التضاريس ثلاثية الأبعاد",
        "3D Terrain View"
    ),
    "best": (
        "أفضل منطقة وفق مؤشر الانحدار",
        "Best Area by Slope Index"
    ),
    "nodata": (
        "لا تتوفر بيانات كافية لتقييم الموقع",
        "Insufficient data to evaluate this site"
    ),
    "date": (
        "تاريخ المهمة (UTC)",
        "Mission date (UTC)"
    ),
    "hours": (
        "مدة المهمة بالساعات",
        "Mission duration (hours)"
    ),
    "calculate": (
        "احسب ظروف المهمة",
        "Calculate Mission Conditions"
    ),
    "sunhours": (
        "ظهور الشمس",
        "Sun Visible"
    ),
    "earthhours": (
        "ظهور الأرض",
        "Earth Visible"
    ),
    "bothhours": (
        "ظهورهما معًا",
        "Both Visible"
    ),
    "delay": (
        "نفس الموقع مع تأخير الموعد",
        "Same Site, Delayed Landing"
    ),
    "different": (
        "موقع بديل في التاريخ نفسه",
        "Alternative Site, Same Date"
    ),
    "comparebutton": (
        "قارن الخطتين",
        "Compare Mission Plans"
    ),
    "sources": (
        "المصادر العلمية",
        "Scientific Sources"
    )
}


def tr(key):
    ar, en = WORDS.get(key, (key, key))
    return ar if st.session_state.language == "العربية" else en


def is_ar():
    return st.session_state.language == "العربية"


def set_site(lat, lon):
    st.session_state.lat = round(
        max(-90, min(90, float(lat))), 5
    )
    st.session_state.lon = round(
        ((float(lon) + 180) % 360) - 180, 5
    )
    st.session_state.mission_result = None


# ==========================================================
# STYLE
# ==========================================================

st.markdown("""
<style>
.stApp {
    background:
        radial-gradient(
            circle at 80% 0%,
            #17324B 0%,
            #10243A 32%,
            #050B16 80%
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
    max-width: 1550px;
    padding-top: 1rem;
}

h1, h2, h3, p, label {
    color: #DCECF7 !important;
}

.stButton button {
    min-height: 52px;
    border-radius: 13px !important;
    background: #10243A !important;
    color: #DCECF7 !important;
    border: 1px solid #35536B !important;
    font-weight: 700 !important;
}

.stButton button:hover {
    background: #173A58 !important;
    border-color: #76C5F5 !important;
}

.stButton button[kind="primary"] {
    background: #76C5F5 !important;
    color: #050B16 !important;
}

[data-testid="stSidebar"] .stButton button {
    min-height: 66px !important;
    font-size: 15px !important;
}

[data-testid="stMetric"] {
    background: #10243A;
    border: 1px solid #35536B;
    border-radius: 15px;
    padding: 16px;
}

.ofoq-hero {
    padding: 27px 33px;
    margin-bottom: 20px;
    border-radius: 22px;
    border: 1px solid #35536B;
    background:
        radial-gradient(
            circle at 82% 40%,
            rgba(118,197,245,.18),
            transparent 28%
        ),
        linear-gradient(120deg,#050B16,#10243A);
}

.ofoq-logo {
    font-size: clamp(38px,5vw,66px);
    font-weight: 850;
    letter-spacing: 3px;
}

.ofoq-small {
    color: #76C5F5;
    letter-spacing: 2px;
    font-weight: 700;
    font-size: 12px;
}

.ofoq-card {
    background: #10243A;
    border: 1px solid #35536B;
    border-radius: 16px;
    padding: 18px;
    margin-bottom: 13px;
}

.ofoq-score {
    font-size: 43px;
    font-weight: 850;
    color: #76C5F5;
}
</style>
""", unsafe_allow_html=True)


# ==========================================================
# IMAGES
# ==========================================================

@st.cache_data(ttl=86400, show_spinner=False)
def get_moon_image():
    response = requests.get(MOON_URL, timeout=35)
    response.raise_for_status()

    return Image.open(
        BytesIO(response.content)
    ).convert("RGB")


def data_url(image):
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=90)

    return (
        "data:image/jpeg;base64,"
        + base64.b64encode(buffer.getvalue()).decode()
    )


def local_moon_image(lat, lon):
    image = get_moon_image()
    w, h = image.size

    x = int((lon + 180) / 360 * w)
    y = int((90 - lat) / 180 * h)

    size = min(180, w, h)

    left = max(0, min(w-size, x-size//2))
    top = max(0, min(h-size, y-size//2))

    patch = image.crop(
        (left, top, left+size, top+size)
    )

    patch = patch.resize(
        (900, 900),
        Image.Resampling.BICUBIC
    )

    return ImageEnhance.Contrast(patch).enhance(1.22)


# ==========================================================
# REAL NASA TERRAIN
# ==========================================================

def read_raster(url, lat, lon, size=48):
    with rasterio.Env(
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        GDAL_HTTP_TIMEOUT="15",
        GDAL_HTTP_MAX_RETRY="1",
        CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".TIF"
    ):
        with rasterio.open("/vsicurl/" + url) as src:

            if src.crs is None:
                raise ValueError("Missing raster CRS")

            transformer = Transformer.from_crs(
                MOON_CRS,
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
                    "Selected location outside data coverage"
                )

            window = Window(
                col-half,
                row-half,
                size,
                size
            )

            a = src.read(
                1,
                window=window,
                masked=True
            )

            values = np.ma.array(
                a, dtype=float
            ).filled(np.nan)

            if src.nodata is not None:
                values[
                    np.isclose(values, src.nodata)
                ] = np.nan

            pixel = max(
                abs(src.transform.a),
                abs(src.transform.e)
            )

            return values, pixel


@st.cache_data(ttl=3600, show_spinner=False)
def get_terrain(lat, lon):
    if lat > -80:
        raise ValueError(
            "Terrain coverage is restricted to 80–90°S"
        )

    slope, pixel = read_raster(
        SLOPE_URL, lat, lon
    )

    dem, _ = read_raster(
        DEM_URL, lat, lon
    )

    if not np.isfinite(slope).any():
        raise ValueError("No valid slope data")

    if not np.isfinite(dem).any():
        raise ValueError("No valid elevation data")

    return slope, dem, pixel


def make_hillshade(dem, pixel):
    z = np.asarray(dem, dtype=float)

    z = np.where(
        np.isfinite(z),
        z,
        np.nanmedian(z)
    )

    dy, dx = np.gradient(z, pixel, pixel)

    nx = -dx
    ny = -dy
    nz = np.ones_like(z)

    norm = np.sqrt(nx**2 + ny**2 + nz**2)

    nx /= norm
    ny /= norm
    nz /= norm

    light = np.array([-0.65, -0.45, 0.61])
    light /= np.linalg.norm(light)

    shade = np.clip(
        nx*light[0] + ny*light[1] + nz*light[2],
        0, 1
    )

    gray = np.clip(
        35 + shade*210,
        0, 255
    ).astype(np.uint8)

    rgb = np.stack(
        [gray, gray, gray],
        axis=-1
    )

    return Image.fromarray(rgb, "RGB").resize(
        (900, 900),
        Image.Resampling.BICUBIC
    )


# ==========================================================
# NINE LANDING CELLS
# ==========================================================

def position_name(row, col):
    arabic = [
        ["أعلى اليسار", "أعلى الوسط", "أعلى اليمين"],
        ["وسط اليسار", "المنتصف", "وسط اليمين"],
        ["أسفل اليسار", "أسفل الوسط", "أسفل اليمين"]
    ]

    english = [
        ["Top left", "Top center", "Top right"],
        ["Middle left", "Center", "Middle right"],
        ["Bottom left", "Bottom center", "Bottom right"]
    ]

    return (
        arabic[row][col]
        if is_ar()
        else english[row][col]
    )


def build_cells(slope=None):
    cells = []

    for row in range(3):
        for col in range(3):

            cell = {
                "row": row,
                "col": col,
                "score": None,
                "status": "gray",
                "slope": None,
                "coverage": 0,
                "position": position_name(row, col)
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
                    p90 = float(
                        np.percentile(valid, 90)
                    )

                    # Prototype slope-based index.
                    # NOT probability of landing success.
                    score = int(round(
                        max(0, min(100, 100-5*p90))
                    ))

                    cell["score"] = score
                    cell["slope"] = round(p90, 2)

                    if score >= 75:
                        cell["status"] = "green"
                    elif score >= 50:
                        cell["status"] = "yellow"
                    else:
                        cell["status"] = "red"

            cells.append(cell)

    return cells


def best_cell(cells):
    valid = [
        c for c in cells
        if c["score"] is not None
    ]

    if not valid:
        return None

    return max(
        valid,
        key=lambda x: x["score"]
    )


@st.cache_data(ttl=3600, show_spinner=False)
def analyze_terrain(lat, lon):
    try:
        slope, dem, pixel = get_terrain(lat, lon)

        return {
            "ok": True,
            "slope": slope,
            "dem": dem,
            "pixel": pixel,
            "error": None
        }

    except Exception as error:
        return {
            "ok": False,
            "slope": None,
            "dem": None,
            "pixel": None,
            "error": str(error)
        }


# ==========================================================
# CAMERA IMAGE WITH 9 TRANSPARENT CELLS
# ==========================================================

def draw_camera(image, cells):
    picture = data_url(image)
    cell_data = json.dumps(cells, ensure_ascii=False)

    markup = """
    <html>
    <head>
    <style>
      * {box-sizing:border-box;}

      body {
        margin:0;
        background:#050B16;
        font-family:Arial,sans-serif;
      }

      .camera {
        width:100%;
        height:590px;
        position:relative;
        overflow:hidden;
        border-radius:17px;
        border:1px solid #35536B;
        background:#050B16;
      }

      .photo {
        position:absolute;
        inset:0;
        background-image:url("__IMAGE__");
        background-size:cover;
        background-position:center;
      }

      .grid {
        position:absolute;
        inset:8%;
        display:grid;
        grid-template-columns:repeat(3,1fr);
        grid-template-rows:repeat(3,1fr);
        gap:6px;
      }

      .cell {
        display:flex;
        align-items:center;
        justify-content:center;
        font-size:clamp(22px,3vw,37px);
        font-weight:800;
        color:white;
        border:1px solid #DCECF7A0;
        border-radius:9px;
        text-shadow:0 2px 5px #000;
      }

      .green {
        background:rgba(53,183,122,.32);
      }

      .yellow {
        background:rgba(227,184,78,.32);
      }

      .red {
        background:rgba(217,104,104,.34);
      }

      .gray {
        background:rgba(109,122,138,.28);
      }

      .label {
        position:absolute;
        top:13px;
        left:13px;
        padding:10px 14px;
        background:#081522E6;
        border:1px solid #76C5F5;
        color:#DCECF7;
        border-radius:10px;
        font-size:12px;
        z-index:5;
      }

      .cell:hover {
        outline:2px solid white;
      }
    </style>
    </head>

    <body>
      <div class="camera">
        <div class="photo"></div>
        <div class="label">
          OFOQ / LANDING CAMERA
        </div>
        <div class="grid" id="grid"></div>
      </div>

      <script>
        const cells=__CELLS__;
        const grid=document.getElementById("grid");

        cells.forEach(c=>{
          const el=document.createElement("div");

          el.className="cell "+c.status;

          el.textContent=(
            c.score===null
            ? "—"
            : c.score+"%"
          );

          el.title=(
            c.position+
            " | "+(
              c.score===null
              ? "No data"
              : c.score+"%"
            )
          );

          grid.appendChild(el);
        });
      </script>
    </body>
    </html>
    """

    markup = markup.replace(
        "__IMAGE__", picture
    ).replace(
        "__CELLS__", cell_data
    )

    components.html(
        markup,
        height=600,
        scrolling=False
    )


# ==========================================================
# 3D TERRAIN VIEW
# ==========================================================

def draw_3d_terrain(dem, pixel):
    z = np.asarray(dem, dtype=float)

    median = float(np.nanmedian(z))

    z = np.where(
        np.isfinite(z), z, median
    )

    z = z - median

    coords = np.arange(
        z.shape[0]
    ) * pixel

    fig = go.Figure(
        data=[
            go.Surface(
                x=coords,
                y=coords,
                z=z,
                colorscale="Greys",
                showscale=False
            )
        ]
    )

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#050B16",
        height=580,
        scene=dict(
            xaxis_title="X (m)",
            yaxis_title="Y (m)",
            zaxis_title="Height (m)",
            camera=dict(
                eye=dict(
                    x=1.7,
                    y=-2.2,
                    z=0.8
                )
            )
        ),
        margin=dict(l=0,r=0,t=15,b=0)
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )


# ==========================================================
# INTERACTIVE 2D / 3D MOON
# ==========================================================

PICKER_HTML = """
<div class="moon-container"></div>
"""

PICKER_CSS = """
.moon-container {
  width:100%;
  height:510px;
  overflow:hidden;
  border:1px solid #35536B;
  border-radius:18px;
  background:#050B16;
}

.moon-container canvas {
  display:block;
  width:100%;
  height:100%;
  cursor:crosshair;
  touch-action:none;
}
"""

PICKER_JS = """
export default function(component) {
  const {data,parentElement,setTriggerValue}=component;

  const root=parentElement.querySelector(".moon-container");
  root.replaceChildren();

  let disposed=false;
  let cleanup=()=>{};

  function pick(lat,lon){
    setTriggerValue("picked",{
      lat:Math.max(-90,Math.min(90,lat)),
      lon:((lon+180)%360+360)%360-180,
      id:Date.now()+Math.random()
    });
  }

  if(data.mode==="2D") {
    const canvas=document.createElement("canvas");
    canvas.width=1100;
    canvas.height=550;
    root.appendChild(canvas);

    const ctx=canvas.getContext("2d");
    const img=new Image();

    let zoom=1;
    let cx=1024;
    let cy=512;
    let down=null;
    let moved=false;

    function viewport(){
      const vw=img.width/zoom;
      const vh=img.height/zoom;

      return {
        x:Math.max(0,Math.min(img.width-vw,cx-vw/2)),
        y:Math.max(0,Math.min(img.height-vh,cy-vh/2)),
        w:vw,
        h:vh
      };
    }

    function draw(){
      if(!img.naturalWidth)return;

      const v=viewport();

      ctx.fillStyle="#050B16";
      ctx.fillRect(0,0,1100,550);

      ctx.drawImage(
        img,
        v.x,v.y,v.w,v.h,
        0,0,1100,550
      );

      const px=(data.lon+180)/360*img.width;
      const py=(90-data.lat)/180*img.height;

      const mx=(px-v.x)/v.w*1100;
      const my=(py-v.y)/v.h*550;

      if(mx>=0&&mx<=1100&&my>=0&&my<=550){
        ctx.strokeStyle="#76C5F5";
        ctx.lineWidth=4;
        ctx.beginPath();
        ctx.arc(mx,my,13,0,Math.PI*2);
        ctx.stroke();

        ctx.fillStyle="white";
        ctx.beginPath();
        ctx.arc(mx,my,4,0,Math.PI*2);
        ctx.fill();
      }
    }

    img.onload=()=>{
      cx=(data.lon+180)/360*img.width;
      cy=(90-data.lat)/180*img.height;
      draw();
    };

    img.src=data.texture;

    function point(e){
      const r=canvas.getBoundingClientRect();

      return {
        x:(e.clientX-r.left)/r.width*1100,
        y:(e.clientY-r.top)/r.height*550
      };
    }

    canvas.onpointerdown=e=>{
      down={...point(e),cx,cy};
      moved=false;
      canvas.setPointerCapture(e.pointerId);
    };

    canvas.onpointermove=e=>{
      if(!down||!img.naturalWidth)return;

      const p=point(e);
      const dx=p.x-down.x;
      const dy=p.y-down.y;

      if(Math.hypot(dx,dy)>5)moved=true;

      if(moved){
        cx=down.cx-dx/1100*img.width/zoom;
        cy=down.cy-dy/550*img.height/zoom;
        draw();
      }
    };

    canvas.onpointerup=e=>{
      if(!down||!img.naturalWidth)return;

      if(!moved){
        const p=point(e);
        const v=viewport();

        const ix=v.x+p.x/1100*v.w;
        const iy=v.y+p.y/550*v.h;

        const lat=90-iy/img.height*180;
        const lon=ix/img.width*360-180;

        data.lat=lat;
        data.lon=lon;

        draw();
        pick(lat,lon);
      }

      down=null;
      moved=false;
    };

    canvas.onwheel=e=>{
      e.preventDefault();

      zoom=Math.max(
        1,
        Math.min(
          7,
          zoom*(e.deltaY<0?1.2:1/1.2)
        )
      );

      draw();
    };

  } else {

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

        root.appendChild(renderer.domElement);

        const tex=new THREE.TextureLoader().load(
          data.texture
        );

        tex.colorSpace=THREE.SRGBColorSpace;

        const moon=new THREE.Mesh(
          new THREE.SphereGeometry(1.65,80,64),
          new THREE.MeshStandardMaterial({
            map:tex,
            roughness:1
          })
        );

        scene.add(moon);

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

        function mark(lat,lon){
          const phi=(lon+180)/360*Math.PI*2;
          const a=lat*Math.PI/180;

          marker.position.set(
            -1.7*Math.cos(phi)*Math.cos(a),
             1.7*Math.sin(a),
             1.7*Math.sin(phi)*Math.cos(a)
          );
        }

        mark(data.lat,data.lon);

        const ray=new THREE.Raycaster();
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

          ray.setFromCamera(mouse,camera);

          const hits=ray.intersectObject(moon);

          if(!hits.length||!hits[0].uv)return;

          const uv=hits[0].uv;
          const lat=uv.y*180-90;
          const lon=uv.x*360-180;

          mark(lat,lon);
          pick(lat,lon);
        };

        function resize(){
          const w=root.clientWidth||850;

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
        root.textContent="3D view: "+String(error);
      }
    })();
  }

  return()=>{
    disposed=true;
    cleanup();
    root.replaceChildren();
  };
}
"""

MOON_PICKER = st.components.v2.component(
    "ofoq_moon_picker_v10",
    html=PICKER_HTML,
    css=PICKER_CSS,
    js=PICKER_JS
)


# ==========================================================
# NASA HORIZONS
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

    r = requests.get(
        HORIZONS_URL,
        params=params,
        timeout=60
    )

    r.raise_for_status()
    text = r.json()["result"]

    if "$$SOE" not in text or "$$EOE" not in text:
        raise ValueError(text[:350])

    block = (
        text.split("$$SOE",1)[1]
        .split("$$EOE",1)[0]
    )

    rows = []

    for line in block.splitlines():
        parts = [
            p.strip()
            for p in line.split(",")
        ]

        if len(parts) < 5:
            continue

        try:
            rows.append({
                "time": pd.to_datetime(
                    parts[0],
                    format="%Y-%b-%d %H:%M"
                ),
                "elevation": float(parts[4])
            })
        except ValueError:
            continue

    if not rows:
        raise ValueError("No NASA data returned")

    return pd.DataFrame(rows)


def calculate_mission(lat, lon, start, hours):
    start_text = start.strftime("%Y-%m-%d %H:%M")

    sun = horizons(
        "10", lat, lon, start_text, hours
    )

    earth = horizons(
        "399", lat, lon, start_text, hours
    )

    df = sun.merge(
        earth,
        on="time",
        suffixes=("_sun", "_earth")
    ).sort_values("time")

    df = df.iloc[:-1].copy()

    if len(df) != hours:
        raise ValueError(
            "Incomplete NASA hourly data"
        )

    df["Sun"] = df.elevation_sun > 0
    df["Earth"] = df.elevation_earth > 0
    df["Both"] = df.Sun & df.Earth

    return df


def mission_metrics(df):
    return {
        "Sun": int(df.Sun.sum()),
        "Earth": int(df.Earth.sum()),
        "Both": int(df.Both.sum())
    }


# ==========================================================
# PAGE FUNCTIONS
# All pages are independent functions.
# This prevents invalid if/elif structure.
# ==========================================================

def page_explore():
    st.header(tr("explore"))
    st.write(
        "اضغط على القمر لاختيار الموقع."
        if is_ar()
        else "Click the Moon to choose a location."
    )

    a, b = st.columns(2)

    with a:
        if st.button(
            "2D MAP",
            type=(
                "primary"
                if st.session_state.moon_view == "2D"
                else "secondary"
            ),
            use_container_width=True
        ):
            st.session_state.moon_view = "2D"
            st.rerun()

    with b:
        if st.button(
            "3D MOON",
            type=(
                "primary"
                if st.session_state.moon_view == "3D"
                else "secondary"
            ),
            use_container_width=True
        ):
            st.session_state.moon_view = "3D"
            st.rerun()

    try:
        result = MOON_PICKER(
            data={
                "texture": data_url(get_moon_image()),
                "mode": st.session_state.moon_view,
                "lat": st.session_state.lat,
                "lon": st.session_state.lon
            },
            key="moon_picker_v10",
            on_picked_change=lambda: None
        )

        point = getattr(result, "picked", None)

        if point:
            if point.get("id") != st.session_state.last_pick:
                st.session_state.last_pick = point["id"]
                set_site(
                    point["lat"],
                    point["lon"]
                )
                st.rerun()

    except Exception as error:
        st.error(str(error))

    a, b = st.columns(2)

    a.metric(
        tr("lat"),
        f"{st.session_state.lat:.5f}°"
    )

    b.metric(
        tr("lon"),
        f"{st.session_state.lon:.5f}°"
    )


def page_views():
    st.header(tr("views"))

    st.write(
        "اختر رؤية الكاميرا أو استكشف التضاريس "
        "ثلاثية الأبعاد."
        if is_ar()
        else "Switch between the landing camera "
             "and 3D terrain."
    )

    a, b = st.columns(2)

    with a:
        if st.button(
            tr("camera"),
            type=(
                "primary"
                if st.session_state.lander_view == "camera"
                else "secondary"
            ),
            use_container_width=True
        ):
            st.session_state.lander_view = "camera"
            st.rerun()

    with b:
        if st.button(
            tr("side"),
            type=(
                "primary"
                if st.session_state.lander_view == "3d"
                else "secondary"
            ),
            use_container_width=True
        ):
            st.session_state.lander_view = "3d"
            st.rerun()

    lat = st.session_state.lat
    lon = st.session_state.lon

    with st.spinner("NASA LOLA"):
        terrain = analyze_terrain(lat, lon)

    if terrain["ok"]:
        slope = terrain["slope"]
        dem = terrain["dem"]
        pixel = terrain["pixel"]

        cells = build_cells(slope)
        image = make_hillshade(dem, pixel)

    else:
        slope = None
        dem = None
        pixel = None

        cells = build_cells(None)

        try:
            image = local_moon_image(lat, lon)
        except Exception:
            image = Image.new(
                "RGB",
                (900,900),
                (55,58,65)
            )

    left, right = st.columns(
        [3,1],
        gap="large"
    )

    with left:
        if (
            st.session_state.lander_view == "3d"
            and dem is not None
        ):
            draw_3d_terrain(dem, pixel)

        elif st.session_state.lander_view == "3d":
            st.warning(tr("nodata"))
            st.image(image, use_container_width=True)

        else:
            draw_camera(image, cells)

    with right:
        st.markdown(
            "### " + tr("best")
        )

        best = best_cell(cells)

        if best is None:
            st.info(tr("nodata"))

        else:
            st.markdown(
                f"""
                <div class="ofoq-card">
                  <div>{best['position']}</div>
                  <div class="ofoq-score">
                    {best['score']}%
                  </div>
                  <div>
                    {"انحدار السطح" if is_ar()
                     else "Surface slope"}:
                    {best['slope']}°
                  </div>
                </div>
                """,
                unsafe_allow_html=True
            )

        st.markdown("### " + (
            "دليل الألوان"
            if is_ar()
            else "Color Legend"
        ))

        legend = [
            ("green", "75–100%"),
            ("yellow", "50–74%"),
            ("red", "0–49%"),
            ("gray", "No data")
        ]

        for name, label in legend:
            st.markdown(
                f"""
                <div style="
                    display:flex;
                    gap:10px;
                    align-items:center;
                    padding:7px;
                ">
                  <span style="
                    display:inline-block;
                    width:16px;
                    height:16px;
                    border-radius:4px;
                    background:{C[name]};
                  "></span>
                  <span>{label}</span>
                </div>
                """,
                unsafe_allow_html=True
            )

    if terrain["ok"]:
        st.success(
            "تم استخراج القياسات من NASA LOLA."
            if is_ar()
            else "NASA LOLA measurements loaded."
        )
        st.caption(
            f"Resolution: {pixel:.0f} m/pixel"
        )

    else:
        st.warning(
            "بيانات التضاريس غير متاحة لهذا الموقع."
            if is_ar()
            else "Terrain data unavailable for this location."
        )

        with st.expander(
            "التفاصيل التقنية"
            if is_ar()
            else "Technical details"
        ):
            st.code(terrain["error"])

    st.caption(
        "النسب مؤشر أولي مبني على الانحدار، وليست "
        "احتمال نجاح الهبوط. المنظر محاكاة مبنية "
        "على ارتفاعات NASA، وليس تصوير مركبة حقيقيًا."
        if is_ar()
        else "Percentages are preliminary slope-based "
             "indices, not landing probabilities. "
             "The surface view is simulated from NASA data."
    )


def page_sun():
    st.header(tr("sun"))

    mission_date = st.date_input(
        tr("date"),
        value=date(2026,11,15)
    )

    hours = st.slider(
        tr("hours"),
        24,96,48,12
    )

    signature = (
        st.session_state.lat,
        st.session_state.lon,
        mission_date,
        hours
    )

    if st.button(
        tr("calculate"),
        type="primary"
    ):
        try:
            start = datetime.combine(
                mission_date,
                datetime.min.time()
            )

            with st.spinner("NASA Horizons"):
                df = calculate_mission(
                    st.session_state.lat,
                    st.session_state.lon,
                    start,
                    hours
                )

            st.session_state.mission_result = (
                signature,
                df
            )

        except Exception as error:
            st.error(str(error))

    saved = st.session_state.mission_result

    if saved is None or saved[0] != signature:
        return

    df = saved[1]
    n = mission_metrics(df)

    a, b, c = st.columns(3)

    a.metric(tr("sunhours"), f"{n['Sun']} h")
    b.metric(tr("earthhours"), f"{n['Earth']} h")
    c.metric(tr("bothhours"), f"{n['Both']} h")

    fig = go.Figure()

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
        height=410
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )

    st.caption(
        "هذه حسابات رؤية هندسية، ولا تشمل "
        "حجب التضاريس أو جودة الاتصال الفعلية."
        if is_ar()
        else "Geometric visibility only; terrain "
             "obstruction and link performance excluded."
    )


def page_compare():
    st.header(tr("compare"))

    mission_date = st.date_input(
        tr("date"),
        value=date(2026,11,15),
        key="compare_date"
    )

    hours = st.slider(
        tr("hours"),
        24,96,48,12,
        key="compare_hours"
    )

    mode = st.radio(
        "Comparison",
        ["delay","site"],
        format_func=lambda x:(
            tr("delay")
            if x == "delay"
            else tr("different")
        )
    )

    start_a = datetime.combine(
        mission_date,
        datetime.min.time()
    )

    start_b = start_a
    lat_b = st.session_state.lat
    lon_b = st.session_state.lon

    if mode == "delay":
        delay = st.slider(
            "Delay (hours)",
            0,168,48,24
        )

        start_b += timedelta(hours=delay)

    elif st.session_state.backup is not None:
        lat_b, lon_b = st.session_state.backup

        st.info(
            f"{lat_b:.5f}°, {lon_b:.5f}°"
        )

    else:
        st.warning(
            "احفظ موقعًا بديلًا من صفحة الاستكشاف."
            if is_ar()
            else "Save a backup site from Explore."
        )

    disabled = (
        mode == "site"
        and st.session_state.backup is None
    )

    if st.button(
        tr("comparebutton"),
        type="primary",
        disabled=disabled
    ):
        try:
            with st.spinner("NASA Horizons"):
                first = calculate_mission(
                    st.session_state.lat,
                    st.session_state.lon,
                    start_a,
                    hours
                )

                second = calculate_mission(
                    lat_b,
                    lon_b,
                    start_b,
                    hours
                )

            m1 = mission_metrics(first)
            m2 = mission_metrics(second)

            a, b = st.columns(2)

            with a:
                st.subheader("Original")
                for key, value in m1.items():
                    st.metric(key, f"{value} h")

            with b:
                st.subheader("Alternative")
                for key, value in m2.items():
                    st.metric(
                        key,
                        f"{value} h",
                        delta=value-m1[key]
                    )

            fig = go.Figure()

            fig.add_trace(go.Bar(
                x=list(m1),
                y=list(m1.values()),
                name="Original",
                marker_color="#6D7A8A"
            ))

            fig.add_trace(go.Bar(
                x=list(m2),
                y=list(m2.values()),
                name="Alternative",
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
                fig,
                use_container_width=True
            )

        except Exception as error:
            st.error(str(error))


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

    pages = [
        ("explore", "◉", "explore"),
        ("views", "▦", "views"),
        ("sun", "☼", "sun"),
        ("compare", "◇", "compare")
    ]

    for key, symbol, name in pages:
        if st.button(
            symbol + "  " + tr(name),
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

    st.caption(tr("site"))

    st.write(
        f"{tr('lat')}: **{st.session_state.lat:.5f}°**"
    )

    st.write(
        f"{tr('lon')}: **{st.session_state.lon:.5f}°**"
    )

    if st.button(
        tr("save"),
        use_container_width=True
    ):
        st.session_state.backup = (
            st.session_state.lat,
            st.session_state.lon
        )
        st.success("✓")


# ==========================================================
# HERO
# ==========================================================

st.markdown(
    """
    <div class="ofoq-hero">
      <div class="ofoq-small">
        NASA SPACE APPS CHALLENGE 2026
      </div>
      <div class="ofoq-logo">أُفُق | OFOQ</div>
      <div class="ofoq-small">
        BEYOND THE HORIZON, TOWARD THE MOON.
      </div>
    </div>
    """,
    unsafe_allow_html=True
)


# ==========================================================
# PAGE ROUTER
# ==========================================================

PAGE_FUNCTIONS = {
    "explore": page_explore,
    "views": page_views,
    "sun": page_sun,
    "compare": page_compare
}

PAGE_FUNCTIONS[
    st.session_state.page
]()


# ==========================================================
# SCIENTIFIC SOURCES
# ==========================================================

st.divider()

with st.expander(tr("sources")):
    st.markdown("""
**NASA CGI Moon Kit**

https://svs.gsfc.nasa.gov/4720/

**NASA LOLA South Pole Terrain**

https://pgda.gsfc.nasa.gov/products/90

**NASA JPL Horizons**

https://ssd-api.jpl.nasa.gov/doc/horizons.html

**Important limitations**

- The 3×3 grid uses a slope-based index.
- Index = max(0, min(100, 100 − 5 × slope P90)).
- Green: 75–100%.
- Yellow: 50–74%.
- Red: below 50%.
- Gray: insufficient measurements.
- This index is not landing success probability.
- The 3D terrain is a simulation, not a live camera feed.
- NASA Horizons visibility does not include terrain masking.
- OFOQ is not a certified landing system.
""")

st.caption(
    "TEAM OFOQ | NASA SPACE APPS CHALLENGE 2026"
)
