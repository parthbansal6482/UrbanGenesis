"""
demo/app.py

Gradio web app for FarmGuard (Satyukt Farmland Encroachment Detection System).
Uses pre-computed inference results so the demo is fast and free to host.
Deployable to Hugging Face Spaces with zero modification.

Features:
  - Interactive Folium map with land-use overlay on OpenStreetMap
  - Before/After comparison sliders
  - Donut chart breakdown of land composition (including cropland class 3)
  - ABI (Agricultural Buffer Index) timeseries trend chart
  - Human-readable verdict panel with style-safe HTML and detailed change table
"""

import os
import gradio as gr
import numpy as np
import json
import yaml
import plotly.graph_objects as go
from pathlib import Path
from PIL import Image
Image.MAX_IMAGE_PIXELS = None
import sys
import logging
import base64
import io
import folium
import math
import html

# Ensure project root is in system path
sys.path.insert(0, str(Path(__file__).parent.parent))
from analytics.grader import generate_verdict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PRECOMPUTED_DIR = Path(__file__).parent / "precomputed"
CONFIG_PATH = Path(__file__).parent.parent / "config" / "settings.yaml"

# Load zone configs (bounding boxes, names, years) from settings.yaml
ZONE_BBOXES = {}
ZONE_DISPLAY_NAMES = {}
ZONE_YEARS = {}
try:
    with open(CONFIG_PATH) as f:
        _cfg = yaml.safe_load(f)
    for zone, vals in _cfg.get("zones", {}).items():
        ZONE_BBOXES[zone] = vals["bbox"]  # [lon_min, lat_min, lon_max, lat_max]
        ZONE_DISPLAY_NAMES[zone] = vals.get("name", zone.replace("_", " ").capitalize())
        ZONE_YEARS[zone] = vals.get("years", [2017, 2019, 2021, 2023])
except Exception:
    ZONE_BBOXES = {
        "nashik_north": [73.72, 20.05, 73.98, 20.25],
        "vijayawada_west": [80.45, 16.45, 80.70, 16.65],
        "hubli_outskirts": [74.95, 15.28, 75.20, 15.48],
    }
    ZONE_DISPLAY_NAMES = {
        "nashik_north": "Nashik North Agricultural Zone",
        "vijayawada_west": "Vijayawada West Farmland",
        "hubli_outskirts": "Hubli Peripheral Agricultural Zone",
    }
    ZONE_YEARS = {
        "nashik_north": [2017, 2019, 2021, 2023],
        "vijayawada_west": [2017, 2019, 2021, 2023],
        "hubli_outskirts": [2017, 2019, 2021, 2023],
    }

# Canonical class names and colors
CLASS_INFO = {
    0: {"name": "Background",       "color": "#000000", "emoji": "⬛"},
    1: {"name": "Buildings",        "color": "#DC2626", "emoji": "🏢"},
    2: {"name": "Roads",            "color": "#825A2C", "emoji": "🛣️"},
    3: {"name": "Cropland",         "color": "#D4A017", "emoji": "🌾"},
    4: {"name": "Dense Vegetation", "color": "#228B22", "emoji": "🌳"},
    5: {"name": "Water Bodies",     "color": "#1E64C8", "emoji": "💧"},
    6: {"name": "Bare Soil",        "color": "#D2B48C", "emoji": "🏜️"},
}

# ─────────────────────────────────────────────────────
# Data helpers
# ─────────────────────────────────────────────────────

def safe_float(v, default=0.0):
    """Convert potentially Infinity/NaN JSON values to safe floats."""
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def load_zone_data(zone_name: str) -> dict:
    zone_dir = PRECOMPUTED_DIR / zone_name
    with open(zone_dir / "verdict.json") as f:
        raw = f.read()
    raw = raw.replace(": Infinity", ": null").replace(":Infinity", ":null")
    raw = raw.replace(": NaN", ": null").replace(":NaN", ":null")
    data = json.loads(raw)

    # Sanitise numeric fields
    data["abi"] = safe_float(data.get("abi"), 0.0)
    data["overall_abi_change_pct"] = safe_float(data.get("overall_abi_change_pct"), 0.0)
    data["cropland_loss_ha"] = safe_float(data.get("cropland_loss_ha"), 0.0)
    for rec in data.get("timeseries", []):
        rec["abi"] = safe_float(rec.get("abi"), 0.0)
    return data


# ─────────────────────────────────────────────────────
# Map builder
# ─────────────────────────────────────────────────────

def build_folium_map(zone_name: str, before_year: int, after_year: int) -> str:
    """
    Builds an interactive Folium map with:
    - OpenStreetMap base layer
    - AI land-use overlays (before/after comparison, toggleable)
    - True Color satellite overlays (before/after comparison, toggleable)
    - NDVI vegetation overlays (before/after comparison, toggleable)
    - Isolated iframe sandbox to prevent CSS leakages
    """
    bbox = ZONE_BBOXES.get(zone_name, [73.72, 20.05, 73.98, 20.25])
    lon_min, lat_min, lon_max, lat_max = bbox
    center_lat = (lat_min + lat_max) / 2
    center_lon = (lon_min + lon_max) / 2
    zone_dir = PRECOMPUTED_DIR / zone_name

    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=11.5,
        tiles="cartodbpositron",
        control_scale=True,
    )

    # Add alternate base maps
    folium.TileLayer(
        "cartodbdarkmatter",
        name="Dark Map (CartoDB Dark Matter)",
        attr="CartoDB"
    ).add_to(m)

    folium.TileLayer(
        "OpenStreetMap",
        name="Detailed Street Map (OSM)",
        attr="OpenStreetMap"
    ).add_to(m)

    # Helper: load mask PNG, convert to RGBA with transparency for background pixels
    def mask_to_rgba_image(mask_path: Path) -> np.ndarray:
        rgb_arr = np.array(Image.open(mask_path).convert("RGB"))
        h, w, _ = rgb_arr.shape
        rgba = np.zeros((h, w, 4), dtype=np.uint8)
        
        # Exact RGB values saved in the precomputed mask PNGs
        expected_colors = {
            0: (0, 0, 0),        # background/clouds
            1: (220, 38, 38),    # buildings - red
            2: (130, 90, 44),    # roads - brown
            3: (212, 160, 23),   # cropland - gold
            4: (34, 139, 34),    # dense vegetation - green
            5: (30, 100, 200),   # water - blue
            6: (210, 180, 140),  # bare soil - tan
        }
        
        for cls_id, rgb_col in expected_colors.items():
            # Exact pixel match (lossless PNG)
            mask = (rgb_arr[:, :, 0] == rgb_col[0]) & \
                   (rgb_arr[:, :, 1] == rgb_col[1]) & \
                   (rgb_arr[:, :, 2] == rgb_col[2])
            
            info = CLASS_INFO[cls_id]
            hex_c = info["color"].lstrip("#")
            r, g, b = tuple(int(hex_c[i:i+2], 16) for i in (0, 2, 4))
            
            rgba[mask, 0] = r
            rgba[mask, 1] = g
            rgba[mask, 2] = b
            rgba[mask, 3] = 0 if cls_id == 0 else 225
            
        return rgba

    bounds = [[lat_min, lon_min], [lat_max, lon_max]]

    # 1. Overlay True Color Satellite Images if they exist
    true_color_before = zone_dir / f"true_color_{before_year}.png"
    true_color_after  = zone_dir / f"true_color_{after_year}.png"
    
    if true_color_before.exists():
        folium.raster_layers.ImageOverlay(
            image=np.array(Image.open(true_color_before)),
            bounds=bounds,
            opacity=0.90,
            name=f"📸 {before_year} — True Color Satellite",
            show=False,
            zindex=1,
        ).add_to(m)

    if true_color_after.exists():
        folium.raster_layers.ImageOverlay(
            image=np.array(Image.open(true_color_after)),
            bounds=bounds,
            opacity=0.90,
            name=f"📸 {after_year} — True Color Satellite",
            show=False,
            zindex=2,
        ).add_to(m)

    # 2. Overlay NDVI Vegetation Maps if they exist
    ndvi_before = zone_dir / f"ndvi_map_{before_year}.png"
    ndvi_after  = zone_dir / f"ndvi_map_{after_year}.png"
    
    if ndvi_before.exists():
        folium.raster_layers.ImageOverlay(
            image=np.array(Image.open(ndvi_before)),
            bounds=bounds,
            opacity=0.85,
            name=f"🌱 {before_year} — NDVI Vegetation Map",
            show=False,
            zindex=3,
        ).add_to(m)

    if ndvi_after.exists():
        folium.raster_layers.ImageOverlay(
            image=np.array(Image.open(ndvi_after)),
            bounds=bounds,
            opacity=0.85,
            name=f"🌱 {after_year} — NDVI Vegetation Map",
            show=False,
            zindex=4,
        ).add_to(m)

    # 3. Overlay AI Land Use Classification Masks
    mask_before_path = zone_dir / f"mask_rgb_{before_year}.png"
    mask_after_path  = zone_dir / f"mask_rgb_{after_year}.png"

    if mask_before_path.exists():
        img_before = mask_to_rgba_image(mask_before_path)
        folium.raster_layers.ImageOverlay(
            image=img_before,
            bounds=bounds,
            opacity=0.85,
            name=f"🌾 {before_year} — Land Use (AI)",
            show=False,
            zindex=5,
        ).add_to(m)

    if mask_after_path.exists():
        img_after = mask_to_rgba_image(mask_after_path)
        folium.raster_layers.ImageOverlay(
            image=img_after,
            bounds=bounds,
            opacity=0.85,
            name=f"🌾 {after_year} — Land Use (AI)",
            show=True,
            zindex=6,
        ).add_to(m)

    # Fit map to bbox
    m.fit_bounds(bounds)

    # Layer control
    folium.LayerControl(collapsed=False, position="topright").add_to(m)

    # Legend HTML with forced style safety
    legend_html = """
    <div style="
        position: fixed;
        bottom: 30px; left: 30px;
        z-index: 1000;
        background-color: white;
        border: 1px solid #E5E7EB;
        border-radius: 12px;
        padding: 14px 18px;
        font-family: 'Inter', sans-serif;
        font-size: 13px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.12);
        min-width: 175px;
        color: #1F2937;
    ">
        <b style="font-size:14px; display:block; margin-bottom:10px; color:#111827;">🌾 Land Use Classes</b>
    """
    for cls_id, info in CLASS_INFO.items():
        if cls_id == 0:
            continue
        legend_html += f"""
        <div style="display:flex; align-items:center; margin-bottom:6px;">
            <span style="display:inline-block; width:14px; height:14px; border-radius:3px;
                         background:{info['color']}; margin-right:8px; flex-shrink:0;"></span>
            <span style="color:#374151;">{info['emoji']} {info['name']}</span>
        </div>"""
    legend_html += "</div>"

    m.get_root().html.add_child(folium.Element(legend_html))

    # Convert map representation to raw HTML
    raw_map_html = m._repr_html_()

    # Wrap inside an isolated iframe sandbox to prevent CSS leaking
    iframe_html = f'<iframe srcdoc="{html.escape(raw_map_html)}" width="100%" height="520px" style="border:none; border-radius:16px; box-shadow: 0 4px 16px rgba(0,0,0,0.06);"></iframe>'
    return iframe_html


# ─────────────────────────────────────────────────────
# Chart builders
# ─────────────────────────────────────────────────────

def build_abi_chart(timeseries: list) -> go.Figure:
    years = [r["year"] for r in timeseries]
    abis  = [safe_float(r.get("abi"), 0.0) for r in timeseries]

    fig = go.Figure()

    # Shaded safety/risk zones based on Satyukt ABI thresholds
    fig.add_hrect(y0=0, y1=0.3, fillcolor="#FEF2F2", opacity=0.4, line_width=0, annotation_text="🔴 Critical (<0.3)", annotation_position="top right")
    fig.add_hrect(y0=0.3, y1=0.5, fillcolor="#FFF7ED", opacity=0.4, line_width=0, annotation_text="🟠 High Risk (0.3-0.5)", annotation_position="top right")
    fig.add_hrect(y0=0.5, y1=1.0, fillcolor="#FFFBEB", opacity=0.4, line_width=0, annotation_text="🟡 Elevated Risk (0.5-1.0)", annotation_position="top right")
    fig.add_hrect(y0=1.0, y1=2.0, fillcolor="#F0FDF4", opacity=0.4, line_width=0, annotation_text="🟢 Moderate Risk (1.0-2.0)", annotation_position="top right")

    # Gradient area fill
    fig.add_trace(go.Scatter(
        x=years + years[::-1],
        y=abis + [0] * len(years),
        fill="toself",
        fillcolor="rgba(16, 185, 129, 0.12)",
        line=dict(width=0),
        showlegend=False,
        hoverinfo="skip",
    ))

    # Main line
    fig.add_trace(go.Scatter(
        x=years, y=abis,
        mode="lines+markers+text",
        line=dict(color="#059669", width=3),
        marker=dict(size=12, color="#10B981", line=dict(color="#065F46", width=2)),
        text=[f"{v:.2f}" for v in abis],
        textposition="top center",
        textfont=dict(size=11, color="#374151"),
        name="ABI Ratio",
    ))

    fig.update_layout(
        title=dict(
            text="Agricultural Buffer Index (ABI) Trend Over Time",
            font=dict(size=15, family="Inter, sans-serif", color="#111827")
        ),
        xaxis=dict(
            title="Year",
            tickmode="array",
            tickvals=years,
            gridcolor="#F3F4F6",
            tickfont=dict(size=12),
        ),
        yaxis=dict(
            title="ABI Score",
            gridcolor="#F3F4F6",
            rangemode="tozero",
        ),
        template="plotly_white",
        height=360,
        margin=dict(l=40, r=40, t=60, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        plot_bgcolor="#FAFAFA",
    )
    return fig


def build_donut_chart(timeseries: list, year: int) -> go.Figure:
    """Build a donut chart showing exact land composition breakdown for a given year."""
    rec = next((r for r in timeseries if r["year"] == year), None)
    if rec is None:
        return go.Figure()

    # Read classes directly from precomputed data
    b_pixels = rec.get("buildings_pixels", 0)
    r_pixels = rec.get("roads_pixels", 0)
    c_pixels = rec.get("cropland_pixels", 0)
    v_pixels = rec.get("vegetation_pixels", 0)
    w_pixels = rec.get("water_pixels", 0)
    s_pixels = rec.get("soil_pixels", 0)

    labels = ["🏢 Buildings", "🛣️ Roads", "🌾 Cropland", "🌳 Vegetation", "💧 Water Bodies", "🏜️ Bare Soil"]
    values = [b_pixels, r_pixels, c_pixels, v_pixels, w_pixels, s_pixels]
    colors = ["#DC2626", "#825A2C", "#D4A017", "#228B22", "#1E64C8", "#D2B48C"]

    # If all values are 0, put placeholder
    if sum(values) == 0:
        values = [1, 1, 1, 1, 1, 1]

    fig = go.Figure(go.Pie(
        labels=labels,
        values=values,
        hole=0.52,
        marker=dict(colors=colors, line=dict(color="white", width=2)),
        textinfo="percent",
        textfont=dict(size=12),
        hovertemplate="<b>%{label}</b><br>%{value:,} pixels<br>%{percent}<extra></extra>",
    ))

    fig.update_layout(
        title=dict(
            text=f"Land Composition — {year}",
            font=dict(size=14, family="Inter, sans-serif", color="#111827")
        ),
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=-0.25, font=dict(size=11)),
        height=320,
        margin=dict(l=20, r=20, t=50, b=20),
    )
    return fig


# ─────────────────────────────────────────────────────
# Main analysis function
# ─────────────────────────────────────────────────────

def analyse_zone(zone_name: str, before_year: int, after_year: int, viz_mode: str = "AI Land Use Classification"):
    # Enforce chronological ordering
    if before_year > after_year:
        before_year, after_year = after_year, before_year
        
    zone_dir = PRECOMPUTED_DIR / zone_name

    try:
        data = load_zone_data(zone_name)
        timeseries = data["timeseries"]
        years = sorted([r["year"] for r in timeseries])

        # Clamp selected years to what actually exists in timeseries
        if years:
            before_year = min(years, key=lambda x: abs(x - before_year))
            after_year  = min(years, key=lambda x: abs(x - after_year))

        # Determine paths based on viz mode
        if viz_mode == "True Color Satellite Image":
            img_before_path = zone_dir / f"true_color_{before_year}.png"
            img_after_path  = zone_dir / f"true_color_{after_year}.png"
        elif viz_mode == "NDVI Vegetation Map":
            img_before_path = zone_dir / f"ndvi_map_{before_year}.png"
            img_after_path  = zone_dir / f"ndvi_map_{after_year}.png"
        else:
            img_before_path = zone_dir / f"mask_rgb_{before_year}.png"
            img_after_path  = zone_dir / f"mask_rgb_{after_year}.png"

        # Fallbacks to AI mask if the requested visualization file doesn't exist
        if not img_before_path.exists():
            img_before_path = zone_dir / f"mask_rgb_{before_year}.png"
        if not img_after_path.exists():
            img_after_path  = zone_dir / f"mask_rgb_{after_year}.png"

        # Images for side-by-side
        img_before = Image.open(img_before_path) if img_before_path.exists() else None
        img_after  = Image.open(img_after_path)  if img_after_path.exists() else None

        # Charts
        chart_abi    = build_abi_chart(timeseries)
        chart_before = build_donut_chart(timeseries, before_year)
        chart_after  = build_donut_chart(timeseries, after_year)

        # Folium map
        map_html = build_folium_map(zone_name, before_year, after_year)

        # Fetch values for selected years
        rec_before = next((r for r in timeseries if r["year"] == before_year), None)
        rec_after  = next((r for r in timeseries if r["year"] == after_year), None)

        if rec_before and rec_after:
            a18 = rec_before["abi"]
            a24 = rec_after["abi"]
            latest_abi = a24
            chg_pct = ((a24 - a18) / a18 * 100) if a18 > 0 else 0.0
        else:
            latest_abi = safe_float(data.get("abi"), 0.0)
            chg_pct = safe_float(data.get("overall_abi_change_pct"), 0.0)

        # Dynamic Grade styling
        g = data.get("grade", "?")
        if g in ["A", "B"]:
            card_bg = "linear-gradient(135deg, #F0FDF4 0%, #ECFDF5 100%)"
            card_border = "#D1FAE5"
            grade_color = "#16A34A"
            badge_emoji = "🟢"
        elif g in ["C", "D"]:
            card_bg = "linear-gradient(135deg, #FFFBEB 0%, #FFF7ED 100%)"
            card_border = "#FDE68A"
            grade_color = "#D97706"
            badge_emoji = "🟡"
        else:  # F
            card_bg = "linear-gradient(135deg, #FEF2F2 0%, #FFF5F5 100%)"
            card_border = "#FCA5A5"
            grade_color = "#DC2626"
            badge_emoji = "🔴"

        alert_active = data.get("encroachment_alert", False)
        alert_text = "⚠️ Encroachment Alert Active" if alert_active else "✅ Buffer boundary stable"

        # Build detailed transition comparison rows in style-safe HTML
        table_rows_html = ""
        if rec_before and rec_after:
            classes_to_compare = [
                ("🏢 Buildings", "buildings_pct"),
                ("🛣️ Roads", "roads_pct"),
                ("🌾 Cropland", "cropland_pct"),
                ("🌳 Vegetation", "vegetation_pct"),
                ("💧 Water Bodies", "water_pct"),
                ("🏜️ Bare Soil", "soil_pct"),
            ]
            for label, field in classes_to_compare:
                pct_before = rec_before.get(field, 0.0)
                pct_after  = rec_after.get(field, 0.0)
                diff = pct_after - pct_before
                if diff > 0.05:
                    trend_str = f"<span style='color:#16A34A; font-weight:600;'>📈 +{diff:.2f}%</span>"
                elif diff < -0.05:
                    trend_str = f"<span style='color:#DC2626; font-weight:600;'>📉 {diff:.2f}%</span>"
                else:
                    trend_str = "<span style='color:#6B7280;'>🟢 Stable</span>"
                
                table_rows_html += f"""
                <tr style="border-bottom: 1px solid #E5E7EB;">
                    <td style="padding:10px 12px; font-weight:500; color:#374151;">{label}</td>
                    <td style="padding:10px 12px; text-align:right; color:#1F2937;">{pct_before:.2f}%</td>
                    <td style="padding:10px 12px; text-align:right; color:#1F2937;">{pct_after:.2f}%</td>
                    <td style="padding:10px 12px; text-align:right;">{trend_str}</td>
                </tr>
                """

        # Detailed Report summary card using explicit Satyukt corporate styling
        cropland_loss_ha = data.get("cropland_loss_ha", 0.0)
        summary_md = f"""
<div style="background: {card_bg};
     border: 1px solid {card_border}; border-radius: 16px; padding: 22px 26px; margin-bottom: 16px; color: #1F2937; font-family: 'Inter', sans-serif;">

<h3 style="margin-top: 0; margin-bottom: 14px; font-size: 1.35em; font-weight: 700; color: #111827; font-family: 'Outfit', sans-serif;">
  {badge_emoji} {ZONE_DISPLAY_NAMES.get(zone_name, zone_name)} Risk Assessment
</h3>

<table style="width:100%; border-collapse:collapse; font-size:0.95em; margin-bottom:18px; color: #1F2937;">
<tr>
  <td style="padding:8px 12px; background:#F9FAFB; border-radius:8px 0 0 8px; font-weight:600; color:#4B5563;">📍 Region</td>
  <td style="padding:8px 12px; background:#F9FAFB; color:#1F2937;">{ZONE_DISPLAY_NAMES.get(zone_name, zone_name)}</td>
  <td style="padding:8px 12px; background:#F9FAFB; font-weight:600; color:#4B5563;">🗓️ Period</td>
  <td style="padding:8px 12px; background:#F9FAFB; border-radius:0 8px 8px 0; color:#1F2937;">{before_year} → {after_year}</td>
</tr>
<tr style="height:8px;"></tr>
<tr>
  <td style="padding:8px 12px; background:#F9FAFB; border-radius:8px 0 0 8px; font-weight:600; color:#4B5563;">📊 ABI Score ({after_year})</td>
  <td style="padding:8px 12px; background:#F9FAFB; color:#1F2937;"><b>{latest_abi:.3f}</b></td>
  <td style="padding:8px 12px; background:#F9FAFB; font-weight:600; color:#4B5563;">📉 Buffer Change</td>
  <td style="padding:8px 12px; background:#F9FAFB; border-radius:0 8px 8px 0; color:{'#DC2626' if chg_pct < 0 else '#16A34A'};"><b>{chg_pct:+.1f}%</b></td>
</tr>
<tr style="height:8px;"></tr>
<tr>
  <td style="padding:8px 12px; background:#F9FAFB; border-radius:8px 0 0 8px; font-weight:600; color:#4B5563;">🌾 Cropland Lost</td>
  <td style="padding:8px 12px; background:#F9FAFB; color:#1F2937;"><b>{cropland_loss_ha:.1f} ha</b></td>
  <td style="padding:8px 12px; background:#F9FAFB; font-weight:600; color:#4B5563;">🚨 Alert Status</td>
  <td style="padding:8px 12px; background:#F9FAFB; border-radius:0 8px 8px 0; color:#1F2937; font-weight:600;">{alert_text}</td>
</tr>
<tr style="height:8px;"></tr>
<tr>
  <td style="padding:8px 12px; background:#F9FAFB; border-radius:8px 0 0 8px; font-weight:600; color:#4B5563;">🏅 Risk Grade</td>
  <td style="padding:8px 12px; background:#F9FAFB; color:{grade_color}; font-weight:700; font-size:1.05em;" colspan="3">{badge_emoji} <b>Grade {g}</b> — {data.get('label','')}</td>
</tr>
</table>

<div style="background: rgba(255,255,255,0.7); border-radius: 12px; padding: 12px 16px; border: 1px solid rgba(0,0,0,0.05); margin-bottom: 20px; font-style: italic; color: #4B5563;">
  &ldquo;{data.get('description', '')}&rdquo;
</div>

<h4 style="margin-top: 0; margin-bottom: 10px; font-size: 1.1em; font-weight: 700; color: #111827; font-family: 'Outfit', sans-serif;">📋 Land Cover Transition Metrics ({before_year} vs {after_year})</h4>

<table style="width:100%; border-collapse:collapse; font-size:0.92em; border: 1px solid #E5E7EB; border-radius: 8px; overflow: hidden; background: white; color:#1F2937;">
<thead>
  <tr style="background:#F3F4F6; border-bottom: 2px solid #E5E7EB;">
    <th style="padding:10px 12px; text-align:left; font-weight:600; color:#374151;">Land Class</th>
    <th style="padding:10px 12px; text-align:right; font-weight:600; color:#374151;">{before_year} %</th>
    <th style="padding:10px 12px; text-align:right; font-weight:600; color:#374151;">{after_year} %</th>
    <th style="padding:10px 12px; text-align:right; font-weight:600; color:#374151;">Trend Shift</th>
  </tr>
</thead>
<tbody>
  {table_rows_html}
</tbody>
</table>

</div>
"""

    except Exception as e:
        logger.warning(f"Using fallback for {zone_name}: {e}")
        import traceback; traceback.print_exc()

        mock_timeseries = [
            {"year": 2018, "abi": 2.20, "buildings_pixels": 2000, "roads_pixels": 800, "cropland_pixels": 4000, "vegetation_pixels": 1800, "water_pixels": 400, "soil_pixels": 1000, "buildings_pct": 20.0, "roads_pct": 8.0, "cropland_pct": 40.0, "vegetation_pct": 18.0, "water_pct": 4.0, "soil_pct": 10.0},
            {"year": 2020, "abi": 1.45, "buildings_pixels": 3000, "roads_pixels": 1200, "cropland_pixels": 3800, "vegetation_pixels": 1800, "water_pixels": 500, "soil_pixels": 800, "buildings_pct": 30.0, "roads_pct": 12.0, "cropland_pct": 38.0, "vegetation_pct": 18.0, "water_pct": 5.0, "soil_pct": 8.0},
            {"year": 2022, "abi": 0.88, "buildings_pixels": 4500, "roads_pixels": 1800, "cropland_pixels": 3200, "vegetation_pixels": 1800, "water_pixels": 500, "soil_pixels": 800, "buildings_pct": 45.0, "roads_pct": 18.0, "cropland_pct": 32.0, "vegetation_pct": 18.0, "water_pct": 5.0, "soil_pct": 8.0},
            {"year": 2024, "abi": 0.42, "buildings_pixels": 5500, "roads_pixels": 2500, "cropland_pixels": 2000, "vegetation_pixels": 1100, "water_pixels": 300, "soil_pixels": 100, "buildings_pct": 55.0, "roads_pct": 25.0, "cropland_pct": 20.0, "vegetation_pct": 11.0, "water_pct": 3.0, "soil_pct": 1.0},
        ]
        dummy = np.zeros((512, 512, 3), dtype=np.uint8)
        dummy[:256, :] = (34, 139, 34)  # vegetation
        dummy[256:, :256] = (220, 38, 38)  # buildings
        dummy[256:, 256:] = (212, 160, 23)  # cropland

        img_before = Image.fromarray(dummy)
        img_after  = Image.fromarray(dummy)

        chart_abi    = build_abi_chart(mock_timeseries)
        chart_before = build_donut_chart(mock_timeseries, 2018)
        chart_after  = build_donut_chart(mock_timeseries, 2024)

        map_html = build_folium_map(zone_name, before_year, after_year)

        summary_md = f"""
<div style="background: linear-gradient(135deg, #FEF2F2 0%, #FFF5F5 100%);
     border: 1px solid #FCA5A5; border-radius: 16px; padding: 22px 26px; color:#1F2937;">
<h3>🔴 {ZONE_DISPLAY_NAMES.get(zone_name, zone_name)} — Fallback Report</h3>
<p>Precomputed results not yet generated on disk. Displaying simulation based on default parameters.</p>
</div>
"""

    return img_before, img_after, chart_abi, chart_before, chart_after, map_html, summary_md


# ─────────────────────────────────────────────────────
# UI Layout
# ─────────────────────────────────────────────────────

ZONE_CHOICES = sorted([d.name for d in PRECOMPUTED_DIR.iterdir() if d.is_dir()]) if PRECOMPUTED_DIR.exists() else []
if not ZONE_CHOICES:
    ZONE_CHOICES = ["nashik_north", "vijayawada_west", "hubli_outskirts"]

# Prefer nashik_north as the starting zone (active agricultural zone);
# fall back to first alphabetical zone
DEFAULT_ZONE = "nashik_north" if "nashik_north" in ZONE_CHOICES else ZONE_CHOICES[0]
DEFAULT_YEARS = ZONE_YEARS.get(DEFAULT_ZONE, [2018, 2020, 2022, 2024])

ZONE_CHOICES_TUPLES = [
    (ZONE_DISPLAY_NAMES.get(name, name.replace("_", " ").capitalize()), name)
    for name in ZONE_CHOICES
]

custom_css = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Outfit:wght@700;800&display=swap');

body, .gradio-container {
    font-family: 'Inter', sans-serif !important;
    background: #F8FAFC !important;
}

#title-block { text-align: center; margin-bottom: 8px; }
#title-block h1 { 
    font-family: 'Outfit', sans-serif !important;
    font-size: 2.4em !important;
    font-weight: 800 !important;
    background: linear-gradient(135deg, #059669, #D4A017, #0284C7);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin-bottom: 0px !important;
}
#title-block p {
    color: #6B7280 !important;
    font-size: 1.05em !important;
    margin-top: 4px !important;
}

.panel-card {
    background: white;
    border-radius: 16px;
    padding: 20px;
    border: 1px solid #E5E7EB;
    box-shadow: 0 2px 12px rgba(0,0,0,0.05);
}

.legend-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    margin-top: 10px;
}

.legend-item {
    display: flex;
    align-items: center;
    font-size: 0.88em;
    color: #374151;
}

.legend-dot {
    width: 14px;
    height: 14px;
    border-radius: 4px;
    margin-right: 7px;
    flex-shrink: 0;
}

button#analyse-btn {
    background: linear-gradient(135deg, #059669, #D4A017) !important;
    border: none !important;
    border-radius: 12px !important;
    font-weight: 600 !important;
    font-size: 1.05em !important;
    color: white !important;
    padding: 12px 24px !important;
    cursor: pointer !important;
    transition: all 0.2s ease !important;
}

button#analyse-btn:hover {
    opacity: 0.92 !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 16px rgba(5, 150, 105, 0.35) !important;
}

.tab-nav button {
    font-family: 'Inter', sans-serif !important;
    font-weight: 500 !important;
}
"""

with gr.Blocks(
    title="FarmGuard — Satyukt Farmland Encroachment System",
) as demo:

    with gr.Group(elem_id="title-block"):
        gr.Markdown("# 🌾 FarmGuard")
        gr.Markdown("### Satyukt Farmland Encroachment Detection System")

    # ── Controls row ──────────────────────────────────
    with gr.Row():
        with gr.Column(scale=1, min_width=240):
            zone_dropdown = gr.Dropdown(
                choices=ZONE_CHOICES_TUPLES,
                label="🗺️ Select Farmland Zone",
                value=DEFAULT_ZONE,
            )
            with gr.Row():
                before_year = gr.Dropdown(
                    choices=DEFAULT_YEARS,
                    label="🗓️ Before Year",
                    value=DEFAULT_YEARS[0],
                )
                after_year = gr.Dropdown(
                    choices=DEFAULT_YEARS,
                    label="🗓️ After Year",
                    value=DEFAULT_YEARS[-1],
                )
            viz_mode = gr.Dropdown(
                choices=["AI Land Use Classification", "True Color Satellite Image", "NDVI Vegetation Map"],
                label="🖼️ Side-by-Side Visualization Mode",
                value="AI Land Use Classification",
            )
            analyse_btn = gr.Button("🔍 Analyze Zone", elem_id="analyse-btn", variant="primary", size="lg")

            gr.HTML("""
            <div class="panel-card" style="margin-top:16px;">
              <b style="font-size:0.95em; color:#111827;">🌾 AI Land Use Legend</b>
              <div class="legend-grid">
                <div class="legend-item"><span class="legend-dot" style="background:#DC2626;"></span>🏢 Buildings</div>
                <div class="legend-item"><span class="legend-dot" style="background:#825A2C;"></span>🛣️ Roads</div>
                <div class="legend-item"><span class="legend-dot" style="background:#D4A017;"></span>🌾 Cropland</div>
                <div class="legend-item"><span class="legend-dot" style="background:#228B22;"></span>🌳 Vegetation</div>
                <div class="legend-item"><span class="legend-dot" style="background:#1E64C8;"></span>💧 Water</div>
                <div class="legend-item"><span class="legend-dot" style="background:#D2B48C;"></span>🏜️ Bare Soil</div>
                <div class="legend-item"><span class="legend-dot" style="background:#111111; border:1px solid #ccc;"></span>⬛ Background</div>
              </div>
            </div>
            """)

        with gr.Column(scale=3):
            summary_out = gr.Markdown(value="*Select parameters and click **Analyze Zone** to begin.*")

    # ── Interactive Map ────────────────────────────────
    with gr.Group():
        gr.Markdown("## 🗺️ Interactive Map — AI Land Use Overlay on Real Map")
        gr.Markdown(
            "_Use the **layer control** (top-right of map) to toggle between AI Land Use, True Color Satellite, and NDVI Vegetation overlays. "
            "Zoom in to see the classifications overlaid directly on top of OpenStreetMap streets and fields._"
        )
        map_out = gr.HTML(label="Interactive Map")

    # ── Before/After Classification Maps ──────────────
    with gr.Group():
        gr.Markdown("## 📸 Land Use Maps — Before & After")
        gr.Markdown(
            "_Pixels are colored based on the selected Side-by-Side Visualization Mode._"
        )
        with gr.Row():
            img_before_out = gr.Image(label="🗓️ Before Year Map", type="pil", interactive=False)
            img_after_out  = gr.Image(label="🗓️ After Year Map", type="pil", interactive=False)

    # ── Analytics Charts ───────────────────────────────
    with gr.Group():
        gr.Markdown("## 📊 Environmental Analytics")
        with gr.Tabs(elem_classes=["tab-nav"]):
            with gr.TabItem("📈 ABI Trend Over Time"):
                gr.Markdown(
                    "_**ABI (Agricultural Buffer Index)**: Measures how much natural/farmland buffer exists per unit built-up. "
                    "Below 0.3 = critical urbanization pressure. Downward trend = active encroachment into farmland._"
                )
                chart_abi_out = gr.Plot()

            with gr.TabItem("🥧 Land Breakdown — Before Year"):
                gr.Markdown("_How land was used in the selected **Before Year**._")
                chart_before_out = gr.Plot()

            with gr.TabItem("🥧 Land Breakdown — After Year"):
                gr.Markdown("_How land is used in the selected **After Year**._")
                chart_after_out = gr.Plot()

    def handle_zone_change(zone_name, viz_m):
        years = ZONE_YEARS.get(zone_name, [2018, 2020, 2022, 2024])
        b_year = years[0]
        a_year = years[-1]
        img_b, img_a, chart_abi, chart_b, chart_a, map_h, summ = analyse_zone(zone_name, b_year, a_year, viz_m)
        return (
            gr.Dropdown(choices=years, value=b_year),
            gr.Dropdown(choices=years, value=a_year),
            img_b, img_a, chart_abi, chart_b, chart_a, map_h, summ
        )

    # ── Event handlers ─────────────────────────────────
    outputs = [img_before_out, img_after_out, chart_abi_out, chart_before_out, chart_after_out, map_out, summary_out]
    inputs_list = [zone_dropdown, before_year, after_year, viz_mode]

    analyse_btn.click(fn=analyse_zone, inputs=inputs_list, outputs=outputs)
    before_year.change(fn=analyse_zone, inputs=inputs_list, outputs=outputs)
    after_year.change(fn=analyse_zone, inputs=inputs_list, outputs=outputs)
    viz_mode.change(fn=analyse_zone, inputs=inputs_list, outputs=outputs)

    # Zone dropdown and initial page load update the years choices dynamically
    zone_dropdown.change(
        fn=handle_zone_change,
        inputs=[zone_dropdown, viz_mode],
        outputs=[before_year, after_year] + outputs
    )
    demo.load(
        fn=handle_zone_change,
        inputs=[zone_dropdown, viz_mode],
        outputs=[before_year, after_year] + outputs
    )


if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        share=False,
        theme=gr.themes.Soft(primary_hue="emerald", secondary_hue="sky", neutral_hue="slate"),
        css=custom_css,
    )
