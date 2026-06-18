"""
scripts/fetch_esri_landcover.py

Fetches ESRI 2023 Annual Land Cover + Sentinel-2 true color imagery from
Microsoft Planetary Computer STAC API and generates high-accuracy precomputed
demo assets.

Why ESRI Land Cover instead of the trained SegFormer model:
- ESRI Land Cover is cloud-free (cloud-masked composite)
- Expert-validated, 10m resolution globally
- Available for every year 2017-2023 via Planetary Computer STAC
- Zero model inference errors, zero cloud contamination
- The class map aligns with FarmGuard: cropland, buildings, vegetation, water, etc.

ESRI Land Cover class mapping:
  1 = Water          -> FarmGuard class 5
  2 = Trees          -> FarmGuard class 4 (dense_vegetation)
  3 = Grass          -> FarmGuard class 4 (dense_vegetation)
  4 = Flooded_veg    -> FarmGuard class 4
  5 = Crops          -> FarmGuard class 3 (cropland) <- key class
  6 = Scrub_shrub    -> FarmGuard class 6 (bare_soil)
  7 = Built_area     -> FarmGuard class 1 (buildings)
  8 = Bare_ground    -> FarmGuard class 6 (bare_soil)
  9 = Snow_ice       -> FarmGuard class 0 (background)
  10 = Clouds        -> FarmGuard class 0 (background)
  11 = Rangeland     -> FarmGuard class 6 (bare_soil)
"""

import numpy as np
import json
import sys
import os
from pathlib import Path
from PIL import Image
import matplotlib
import matplotlib.cm as cm
import logging

# Set GDAL HTTP timeouts BEFORE rasterio is imported (env vars read at init time)
# This prevents COG windowed reads from failing prematurely on slow CDN responses
os.environ.setdefault("GDAL_HTTP_TIMEOUT", "300")          # 300s per HTTP request
os.environ.setdefault("GDAL_HTTP_CONNECTTIMEOUT", "60")   # 60s to establish connection
os.environ.setdefault("GDAL_HTTP_MAX_RETRY", "5")         # retry up to 5 times
os.environ.setdefault("GDAL_HTTP_RETRY_DELAY", "3")       # 3s between retries
os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")  # faster COG reads

# Ensure project root in path
sys.path.insert(0, str(Path(__file__).parent.parent))
from analytics.abi import compute_abi, compute_cropland_loss_ha
from analytics.grader import generate_verdict

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
PRECOMPUTED_DIR = PROJECT_ROOT / "demo" / "precomputed"

# FarmGuard class color map (6 classes)
CLASS_COLORS = {
    0: (0, 0, 0),        # background/nodata - black
    1: (220, 38, 38),    # buildings - red
    2: (212, 160, 23),   # cropland - gold
    3: (34, 139, 34),    # dense vegetation - green
    4: (30, 100, 200),   # water - blue
    5: (210, 180, 140),  # bare soil - tan
}

# ESRI LC class -> FarmGuard class mapping
ESRI_TO_FARMGUARD = {
    0:  0,  # nodata -> background
    1:  4,  # water -> water
    2:  3,  # trees -> dense_vegetation
    3:  3,  # grass -> dense_vegetation
    4:  3,  # flooded_veg -> dense_vegetation
    5:  2,  # crops -> cropland (THE KEY CLASS)
    6:  5,  # scrub/shrub -> bare_soil
    7:  1,  # built area -> buildings
    8:  5,  # bare ground -> bare_soil
    9:  0,  # snow/ice -> background
    10: 0,  # clouds -> background
    11: 5,  # rangeland -> bare_soil
}


def mask_to_rgb(mask):
    """Convert integer class mask to RGB image using FarmGuard color palette."""
    h, w = mask.shape
    rgb = np.zeros((h, w, 3), dtype=np.uint8)
    for cls_id, color in CLASS_COLORS.items():
        rgb[mask == cls_id] = color
    return rgb


def fetch_esri_landcover_tile(bbox, year, output_shape=1024):
    """
    Fetch ESRI Annual Land Cover for a given bbox and year from Planetary Computer.
    Returns (farmguard_mask, raw_esri_mask) as numpy arrays.
    bbox: [lon_min, lat_min, lon_max, lat_max] in WGS84 (EPSG:4326)
    """
    try:
        import pystac_client
        import planetary_computer
        import rasterio
        from rasterio.windows import from_bounds
        from rasterio.warp import transform_bounds
        from rasterio.enums import Resampling
    except ImportError:
        raise ImportError("Required: pip install pystac-client planetary-computer rasterio")

    # Determine target dimensions:
    if isinstance(output_shape, int):
        out_h, out_w = output_shape, output_shape
    else:
        out_h, out_w = output_shape

    # ESRI Land Cover is available 2017-2023; clamp to nearest available year
    esri_year = min(max(year, 2017), 2023)
    if year != esri_year:
        logger.warning(f"ESRI LC not available for {year}, using {esri_year}")

    client = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )

    search = client.search(
        collections=["io-lulc-annual-v02"],
        bbox=bbox,
        datetime=f"{esri_year}-01-01/{esri_year}-12-31",
        max_items=10,
    )
    items = list(search.items())
    if not items:
        logger.warning(f"No ESRI LC items found for bbox={bbox}, year={esri_year}")
        return None, None

    logger.info(f"Found {len(items)} ESRI LC tiles for {esri_year}")

    lon_min, lat_min, lon_max, lat_max = bbox
    all_tiles = []

    for item in items:
        href = item.assets["data"].href
        try:
            signed_href = planetary_computer.sign(href)
            with rasterio.open(signed_href) as src:
                # Reproject bbox from WGS84 to the raster's native CRS
                src_crs = src.crs
                if src_crs and str(src_crs).upper() not in ("EPSG:4326", "CRS84"):
                    left, bottom, right, top = transform_bounds(
                        "EPSG:4326", src_crs,
                        lon_min, lat_min, lon_max, lat_max
                    )
                else:
                    left, bottom, right, top = lon_min, lat_min, lon_max, lat_max

                window = from_bounds(left, bottom, right, top, src.transform)
                data = src.read(
                    1,
                    window=window,
                    out_shape=(out_h, out_w),
                    resampling=Resampling.nearest,
                    boundless=True,     # allow reads that extend beyond raster extent
                    fill_value=0,
                )
                all_tiles.append(data)
        except Exception as e:
            logger.warning(f"Failed to read tile: {e}")
            continue

    if not all_tiles:
        return None, None

    # Mosaic: for each pixel, use the first non-zero value across tiles
    esri_mask = np.zeros((out_h, out_w), dtype=np.uint8)
    for tile in all_tiles:
        valid = (tile > 0) & (esri_mask == 0)
        esri_mask[valid] = tile[valid]

    # Remap ESRI classes to FarmGuard classes
    farmguard_mask = np.zeros_like(esri_mask)
    for esri_cls, fg_cls in ESRI_TO_FARMGUARD.items():
        farmguard_mask[esri_mask == esri_cls] = fg_cls

    return farmguard_mask, esri_mask


def _fetch_single_s2_band(signed_href, lon_min, lat_min, lon_max, lat_max, output_shape):
    """Worker function to fetch a single band of Sentinel-2 from Planetary Computer COG."""
    import rasterio
    from rasterio.windows import from_bounds
    from rasterio.warp import transform_bounds
    from rasterio.enums import Resampling
    
    with rasterio.open(signed_href) as src:
        src_crs = src.crs
        if src_crs and str(src_crs).upper() not in ("EPSG:4326", "CRS84"):
            left, bottom, right, top = transform_bounds(
                "EPSG:4326", src_crs,
                lon_min, lat_min, lon_max, lat_max
            )
        else:
            left, bottom, right, top = lon_min, lat_min, lon_max, lat_max

        window = from_bounds(left, bottom, right, top, src.transform)
        if output_shape is None:
            out_h = int(round(window.height))
            out_w = int(round(window.width))
        elif isinstance(output_shape, int):
            out_h, out_w = output_shape, output_shape
        else:
            out_h, out_w = output_shape

        return src.read(
            1,
            window=window,
            out_shape=(out_h, out_w),
            resampling=Resampling.bilinear,
            boundless=True,
            fill_value=0,
        ).astype(np.float32)


def fetch_sentinel2_true_color(bbox, year, output_size=None):
    """
    Fetch best available Sentinel-2 true color image (least cloudy) for a bbox/year.
    Returns (RGB array, (red,green,blue,nir) bands) or (None, None) on failure.
    bbox: [lon_min, lat_min, lon_max, lat_max] in WGS84 (EPSG:4326)
    """
    try:
        import pystac_client
        import planetary_computer
        import rasterio
        from rasterio.windows import from_bounds
        from rasterio.warp import transform_bounds
        import concurrent.futures
        from collections import defaultdict
    except ImportError:
        raise ImportError("Required: pip install pystac-client planetary-computer rasterio")

    client = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )

    lon_min, lat_min, lon_max, lat_max = bbox

    # Multi-stage datetime window search to guarantee full coverage:
    # 1. February strictly (mature Rabi season)
    # 2. Jan 15 to Mar 15 (highly similar phenology)
    # 3. Full year fallback
    search_stages = [
        (f"{year}-02-01/{year}-02-28", 15, 30, "February strictly"),
        (f"{year}-01-15/{year}-03-15", 20, 60, "Jan 15 - Mar 15"),
        (f"{year}-01-01/{year}-12-31", 20, 100, "Full year fallback"),
    ]

    best_date = None
    best_coverage_pct = 0.0
    best_cloud_cover = 100.0
    best_date_items = []

    for date_range, max_cloud, max_items, label in search_stages:
        logger.info(f"Evaluating candidate dates in {label} ({date_range})...")
        search = client.search(
            collections=["sentinel-2-l2a"],
            bbox=bbox,
            datetime=date_range,
            query={"eo:cloud_cover": {"lt": max_cloud}},
            sortby=[{"field": "eo:cloud_cover", "direction": "asc"}],
            max_items=max_items,
        )
        items = list(search.items())
        if not items:
            continue

        # Group by date
        date_groups = defaultdict(list)
        for item in items:
            date_str = item.datetime.strftime("%Y-%m-%d")
            tile_id = item.properties.get("s2:mgrs_tile", "")
            # Deduplicate items by tile ID to avoid redundant downloads on same date
            if not any(x.properties.get("s2:mgrs_tile") == tile_id for x in date_groups[date_str]):
                date_groups[date_str].append(item)

        # Score date groups in this stage
        stage_best_date = None
        stage_best_coverage = 0.0
        stage_best_cloud = 100.0
        stage_best_items = []

        for date_str, group_items in sorted(date_groups.items()):
            combined_mask = np.zeros((64, 64), dtype=bool)
            total_cloud = 0.0
            
            for item in group_items:
                try:
                    href = item.assets["B04"].href
                    signed_href = planetary_computer.sign(href)
                    with rasterio.open(signed_href) as src:
                        src_crs = src.crs
                        if src_crs and str(src_crs).upper() not in ("EPSG:4326", "CRS84"):
                            left, bottom, right, top = transform_bounds(
                                "EPSG:4326", src_crs,
                                lon_min, lat_min, lon_max, lat_max
                            )
                        else:
                            left, bottom, right, top = lon_min, lat_min, lon_max, lat_max
                        window = from_bounds(left, bottom, right, top, src.transform)
                        test_data = src.read(1, window=window, out_shape=(64, 64), boundless=True, fill_value=0)
                        combined_mask |= (test_data > 0)
                        total_cloud += item.properties.get("eo:cloud_cover", 0.0)
                except Exception as e:
                    logger.warning(f"  Failed to inspect candidate {item.id} on {date_str}: {e}")
                    continue
            
            coverage_pct = np.mean(combined_mask) * 100
            avg_cloud = total_cloud / len(group_items) if group_items else 100.0
            logger.info(f"  Date {date_str}: coverage={coverage_pct:.2f}%, avg_cloud={avg_cloud:.2f}% ({len(group_items)} tiles)")

            if coverage_pct > stage_best_coverage + 1.0:
                stage_best_coverage = coverage_pct
                stage_best_cloud = avg_cloud
                stage_best_date = date_str
                stage_best_items = group_items
            elif abs(coverage_pct - stage_best_coverage) <= 1.0 and avg_cloud < stage_best_cloud:
                stage_best_coverage = coverage_pct
                stage_best_cloud = avg_cloud
                stage_best_date = date_str
                stage_best_items = group_items

        if stage_best_coverage > best_coverage_pct:
            best_coverage_pct = stage_best_coverage
            best_cloud_cover = stage_best_cloud
            best_date = stage_best_date
            best_date_items = stage_best_items

        # If we found >= 98% coverage in this stage, we are done!
        if best_coverage_pct >= 98.0:
            logger.info(f"Excellent coverage ({best_coverage_pct:.2f}%) found in {label}. Terminating date search.")
            break
        else:
            logger.info(f"Best coverage in {label} was {best_coverage_pct:.2f}% (< 98%). Trying next stage...")

    if not best_date_items:
        logger.warning("No valid Sentinel-2 dates found with coverage.")
        return None, None

    logger.info(f"Selected best date: {best_date} ({best_coverage_pct:.2f}% coverage, {len(best_date_items)} tiles)")

    # Resolve native dimensions first using B04 of the first tile
    try:
        first_item = best_date_items[0]
        red_href = first_item.assets["B04"].href
        signed_red_href = planetary_computer.sign(red_href)
        with rasterio.open(signed_red_href) as src:
            src_crs = src.crs
            if src_crs and str(src_crs).upper() not in ("EPSG:4326", "CRS84"):
                left, bottom, right, top = transform_bounds(
                    "EPSG:4326", src_crs,
                    lon_min, lat_min, lon_max, lat_max
                )
            else:
                left, bottom, right, top = lon_min, lat_min, lon_max, lat_max
            window = from_bounds(left, bottom, right, top, src.transform)
            
            if output_size is None:
                output_shape = (int(round(window.height)), int(round(window.width)))
                logger.info(f"  Native Sentinel-2 shape computed: {output_shape[1]}x{output_shape[0]} (10m/px)")
            elif isinstance(output_size, int):
                output_shape = (output_size, output_size)
            else:
                output_shape = output_size
    except Exception as e:
        logger.error(f"Failed to inspect dimensions: {e}")
        return None, None

    out_h, out_w = output_shape

    # Download bands for all tiles on the selected date and merge them
    band_components = defaultdict(list)
    success = True
    tasks = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        for band in ["B04", "B03", "B02", "B08"]:
            for item in best_date_items:
                href = item.assets[band].href
                signed_href = planetary_computer.sign(href)
                future = executor.submit(
                    _fetch_single_s2_band,
                    signed_href,
                    lon_min, lat_min, lon_max, lat_max,
                    output_shape
                )
                tasks[future] = (band, item.id)

        completed, unresolved = concurrent.futures.wait(tasks.keys(), timeout=None)

        for future in tasks:
            band, item_id = tasks[future]
            try:
                data = future.result()
                band_components[band].append(data)
            except Exception as e:
                logger.warning(f"  Failed to read {band} for {item_id}: {e}")
                success = False

    if not success or len(band_components) < 4:
        logger.warning("  Failed to download all bands for the selected tiles.")
        return None, None

    # Merge/mosaic the band components by taking the maximum/non-zero value
    bands_data = {}
    for band in ["B04", "B03", "B02", "B08"]:
        components = band_components[band]
        merged = np.zeros((out_h, out_w), dtype=np.float32)
        for comp in components:
            valid = (comp > 0)
            merged[valid] = comp[valid]
        bands_data[band] = merged

    red = bands_data["B04"]
    green = bands_data["B03"]
    blue = bands_data["B02"]
    nir = bands_data["B08"]

    # Cloud mask: bright in all bands (Sentinel-2 L2A digital numbers)
    cloud_mask = (red > 3500) & (green > 3500) & (blue > 3500)

    # Stretch to 8-bit using percentile normalization on non-cloud pixels
    h, w = red.shape
    stretched = np.zeros((h, w, 3), dtype=np.uint8)
    for i, band_data in enumerate([red, green, blue]):
        land_pixels = band_data[~cloud_mask & (band_data > 0)]
        if len(land_pixels) > 100:
            p2, p98 = np.percentile(land_pixels, [2, 98])
        else:
            p2, p98 = 0, 3000
        if p98 == p2:
            p98 = p2 + 1
        stretched[:, :, i] = np.clip((band_data - p2) / (p98 - p2) * 255, 0, 255).astype(np.uint8)

    # Fill cloud pixels with light gray instead of black
    stretched[cloud_mask] = [200, 200, 200]

    return stretched, (red, green, blue, nir)


def generate_ndvi_map_from_bands(red, green, blue, nir):
    """Generate a colored NDVI map from band arrays."""
    denom = nir + red
    denom[denom == 0] = 1.0
    ndvi = (nir - red) / denom
    ndvi_clipped = np.clip(ndvi, -0.1, 0.8)
    norm_ndvi = (ndvi_clipped - (-0.1)) / (0.8 - (-0.1))
    cmap = matplotlib.colormaps["RdYlGn"]
    ndvi_rgba = (cmap(norm_ndvi) * 255.0).astype(np.uint8)
    return ndvi_rgba[:, :, :3]


def generate_zone_assets(zone_key, bbox, years, use_network=True):
    """Generate all precomputed assets for a zone. Falls back to mock if network unavailable."""
    zone_dir = PRECOMPUTED_DIR / zone_key
    zone_dir.mkdir(parents=True, exist_ok=True)

    timeseries_stats = []
    first_year_mask = None
    last_year_mask = None

    for year in years:
        logger.info(f"Processing {zone_key} -- {year}...")
        fg_mask = None

        if use_network:
            try:
                # 1. Fetch Sentinel-2 first to get the native 10m/px shape
                tc_rgb, bands = fetch_sentinel2_true_color(bbox, year, output_size=None)
                
                if tc_rgb is not None:
                    h, w = tc_rgb.shape[:2]
                    logger.info(f"  Sentinel-2 fetched at native size: {w}x{h} (10m/px)")
                    Image.fromarray(tc_rgb).save(zone_dir / f"true_color_{year}.png")
                    
                    if bands is not None:
                        red, green, blue, nir = bands
                        ndvi_img = generate_ndvi_map_from_bands(red, green, blue, nir)
                        Image.fromarray(ndvi_img).save(zone_dir / f"ndvi_map_{year}.png")
                    
                    # 2. Fetch ESRI Land Cover at the matching native shape
                    fg_mask, esri_mask = fetch_esri_landcover_tile(bbox, year, output_shape=(h, w))
                else:
                    logger.warning("  Sentinel-2 fetch failed, falling back to 1024px for ESRI LC")
                    fg_mask, esri_mask = fetch_esri_landcover_tile(bbox, year, output_shape=(1024, 1024))
                
                if fg_mask is not None:
                    logger.info(f"  ESRI Land Cover fetched for {year}")
                    mask_rgb = mask_to_rgb(fg_mask)
                    Image.fromarray(mask_rgb).save(zone_dir / f"mask_rgb_{year}.png")

            except Exception as e:
                logger.warning(f"  Network fetch failed for {zone_key}/{year}: {e}. Using mock.")
                fg_mask = None

        if fg_mask is None:
            logger.info(f"  Generating realistic mock for {zone_key} -- {year}...")
            size = 1024
            fg_mask = _generate_realistic_mock(zone_key, year, size)
            mask_rgb = mask_to_rgb(fg_mask)
            Image.fromarray(mask_rgb).save(zone_dir / f"mask_rgb_{year}.png")
            tc = _mask_to_true_color(fg_mask, size, year)
            Image.fromarray(tc).save(zone_dir / f"true_color_{year}.png")
            ndvi_img = _mask_to_ndvi(fg_mask, size, year)
            Image.fromarray(ndvi_img).save(zone_dir / f"ndvi_map_{year}.png")

        if year == years[0]:
            first_year_mask = fg_mask
        if year == years[-1]:
            last_year_mask = fg_mask

        stats = compute_abi(fg_mask)
        stats["year"] = year
        stats["soil_pixels"] = int((fg_mask == 6).sum())
        stats["soil_pct"] = round(stats["soil_pixels"] / fg_mask.size * 100, 2)
        stats["buildings_pct"] = round(stats["buildings_pixels"] / fg_mask.size * 100, 2)
        stats["roads_pct"] = round(stats["roads_pixels"] / fg_mask.size * 100, 2)
        stats["vegetation_pct"] = round(stats["vegetation_pixels"] / fg_mask.size * 100, 2)
        stats["water_pct"] = round(stats["water_pixels"] / fg_mask.size * 100, 2)
        stats["cropland_pct"] = round(stats["cropland_pixels"] / fg_mask.size * 100, 2)
        timeseries_stats.append(stats)

    timeseries_stats = sorted(timeseries_stats, key=lambda x: x["year"])

    loss_ha = 0.0
    encroachment_stats = {
        "total_cropland_lost_ha": 0.0,
        "total_water_lost_ha": 0.0
    }
    if first_year_mask is not None and last_year_mask is not None:
        loss_ha = compute_cropland_loss_ha(first_year_mask, last_year_mask, resolution_m=10.0)
        from analytics.encroachment import calculate_encroachment_stats, generate_encroachment_heatmap
        encroachment_stats = calculate_encroachment_stats(first_year_mask, last_year_mask, mapping_type="esri")
        
        # Save encroachment heatmap
        heatmap_arr = generate_encroachment_heatmap(first_year_mask, last_year_mask, mapping_type="esri")
        Image.fromarray(heatmap_arr).save(zone_dir / "encroachment_heatmap.png")
        logger.info(f"  Saved encroachment heatmap to {zone_dir / 'encroachment_heatmap.png'}")

    verdict = generate_verdict(timeseries_stats, zone_key, cropland_loss_ha=loss_ha)
    verdict["encroachment"] = encroachment_stats

    with open(zone_dir / "verdict.json", "w") as f:
        json.dump(verdict, f, indent=2)

    logger.info(f"  Grade {verdict['grade']} (ABI={verdict['abi']:.3f}, Crop loss={loss_ha:.1f} ha, Cropland Encroachment={encroachment_stats['total_cropland_lost_ha']:.1f} ha)")
    return verdict


def _generate_realistic_mock(zone_key, year, size=1024):
    """
    Generate spatially coherent land use mask using Gaussian blur noise.
    Creates realistic field/neighborhood patterns rather than random pixel noise.
    """
    from scipy.ndimage import gaussian_filter

    rng = np.random.default_rng(hash(zone_key) % (2**32) + year)
    t_pct = (year - 2018) / max((2024 - 2018), 1)

    zone_profiles = {
        "nashik_north": {
            "cropland":   0.50 - t_pct * 0.18,
            "buildings":  0.08 + t_pct * 0.14,
            "roads":      0.03 + t_pct * 0.05,
            "vegetation": 0.14,
            "water":      0.04,
            "bare_soil":  0.21 - t_pct * 0.01,
        },
        "vijayawada_west": {
            "cropland":   0.62 - t_pct * 0.10,
            "buildings":  0.05 + t_pct * 0.08,
            "roads":      0.02 + t_pct * 0.03,
            "vegetation": 0.08,
            "water":      0.15,
            "bare_soil":  0.08,
        },
        "hubli_outskirts": {
            "cropland":   0.55 - t_pct * 0.20,
            "buildings":  0.06 + t_pct * 0.18,
            "roads":      0.03 + t_pct * 0.06,
            "vegetation": 0.10,
            "water":      0.03,
            "bare_soil":  0.23 - t_pct * 0.04,
        },
        "bengaluru": {
            "cropland":   max(0.01, 0.10 - t_pct * 0.06),
            "buildings":  0.45 + t_pct * 0.15,
            "roads":      0.12 + t_pct * 0.08,
            "vegetation": max(0.10, 0.25 - t_pct * 0.10),
            "water":      0.02,
            "bare_soil":  max(0.02, 0.14 - t_pct * 0.07),
        },
    }

    profile = zone_profiles.get(zone_key, zone_profiles["nashik_north"])
    total = sum(profile.values())
    profile = {k: max(0.0, v / total) for k, v in profile.items()}

    # Large-scale spatial coherence using Gaussian blur noise.
    # IMPORTANT: use rank-based (argsort) assignment, NOT value thresholds.
    # Gaussian blur distorts the uniform distribution so value thresholds
    # produce wildly wrong class proportions. Rank assignment guarantees
    # exact proportions while preserving spatial coherence.
    noise = rng.random((size, size)).astype(np.float32)
    noise_blurred = gaussian_filter(noise, sigma=30)

    # Flatten and sort pixels by their blurred noise value
    flat_blurred = noise_blurred.flatten()
    sorted_indices = np.argsort(flat_blurred)  # ascending order
    total_pixels = size * size

    mask_flat = np.zeros(total_pixels, dtype=np.uint8)
    start_idx = 0
    for cls_id, key in [(1, "buildings"), (2, "roads"), (3, "cropland"),
                         (4, "vegetation"), (5, "water"), (6, "bare_soil")]:
        frac = profile.get(key, 0.0)
        n_pixels = int(round(frac * total_pixels))
        end_idx = min(start_idx + n_pixels, total_pixels)
        mask_flat[sorted_indices[start_idx:end_idx]] = cls_id
        start_idx = end_idx

    # Fill any remaining pixels with bare_soil (class 6)
    if start_idx < total_pixels:
        mask_flat[sorted_indices[start_idx:]] = 6

    mask = mask_flat.reshape((size, size))

    # Fine-scale road network overlay
    fine_noise = rng.random((size, size)).astype(np.float32)
    fine_blurred = gaussian_filter(fine_noise, sigma=6)
    fine_blurred = (fine_blurred - fine_blurred.min()) / (fine_blurred.max() - fine_blurred.min() + 1e-8)
    road_mask = fine_blurred > 0.93
    mask[road_mask & (mask != 5) & (mask != 1)] = 2

    return mask


def _mask_to_true_color(mask, size, year):
    """Generate realistic synthetic true color image from land use mask."""
    rng = np.random.default_rng(year)
    tc = np.zeros((size, size, 3), dtype=np.uint8)

    class_rgb = {
        0: (30, 30, 35),
        1: (195, 195, 200),
        2: (85, 85, 90),
        3: (160, 185, 80),
        4: (45, 110, 50),
        5: (40, 80, 160),
        6: (195, 170, 130),
    }

    for cls_id, rgb in class_rgb.items():
        px = mask == cls_id
        if px.any():
            tc[px] = rgb

    noise = rng.integers(-18, 18, (size, size, 3), dtype=np.int16)
    tc = np.clip(tc.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    return tc


def _mask_to_ndvi(mask, size, year):
    """Generate NDVI visualization from land use mask."""
    rng = np.random.default_rng(year + 1000)
    ndvi = np.zeros((size, size), dtype=np.float32)

    class_ndvi = {0: -0.1, 1: 0.02, 2: 0.01, 3: 0.45, 4: 0.72, 5: -0.12, 6: 0.08}
    for cls_id, val in class_ndvi.items():
        ndvi[mask == cls_id] = val

    ndvi += rng.normal(0, 0.04, (size, size))
    ndvi_clipped = np.clip(ndvi, -0.1, 0.8)
    norm = (ndvi_clipped - (-0.1)) / 0.9
    cmap = matplotlib.colormaps["RdYlGn"]
    rgba = (cmap(norm) * 255).astype(np.uint8)
    return rgba[:, :, :3]


if __name__ == "__main__":
    import argparse
    import yaml

    parser = argparse.ArgumentParser(
        description="Fetch ESRI Land Cover + generate FarmGuard demo assets"
    )
    parser.add_argument("--zone", default="all", help="Zone key or 'all'")
    parser.add_argument("--mock", action="store_true", help="Use mock generation (no network)")
    args = parser.parse_args()

    cfg_path = PROJECT_ROOT / "config" / "settings.yaml"
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)

    zones = cfg.get("zones", {})
    if args.zone != "all":
        zones = {k: v for k, v in zones.items() if k == args.zone}

    if not zones:
        logger.error(f"No zones found matching '{args.zone}'")
        sys.exit(1)

    use_network = not args.mock
    mode_label = "Network (ESRI Land Cover + Sentinel-2)" if use_network else "Mock (spatially coherent synthetic)"
    logger.info(f"Mode: {mode_label}")

    for zone_key, zone_cfg in zones.items():
        bbox = zone_cfg["bbox"]
        years = zone_cfg.get("years", [2017, 2019, 2021, 2023])
        logger.info(f"\n{'='*60}")
        logger.info(f"Zone: {zone_cfg.get('name', zone_key)}  BBox: {bbox}  Years: {years}")
        generate_zone_assets(zone_key, bbox, years, use_network=use_network)

    logger.info("\nAll zones processed.")
    logger.info(f"Assets saved to: {PRECOMPUTED_DIR}")
