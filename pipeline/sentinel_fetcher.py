"""
pipeline/sentinel_fetcher.py

Fetches the best-available cloud-free Sentinel-2 Level-2A true-color
composite for a given bounding box and year from Microsoft Planetary Computer.

Strategy:
    1. February strictly        — mature Rabi season, minimal cloud cover
    2. Jan 15 – Mar 15          — similar phenology fallback window
    3. Full-year fallback       — guaranteed result at cost of phenology accuracy

Within each window, candidate dates are scored by spatial coverage and
average cloud fraction. Bands are downloaded in parallel (ThreadPoolExecutor).
"""

import logging
from collections import defaultdict

import numpy as np

from pipeline.stac_client import create_stac_client

logger = logging.getLogger(__name__)

_S2_BANDS = ["B04", "B03", "B02", "B08"]   # Red, Green, Blue, NIR
_CLOUD_MASK_THRESHOLD = 3500                # L2A digital number


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _fetch_single_s2_band(
    signed_href: str,
    lon_min: float,
    lat_min: float,
    lon_max: float,
    lat_max: float,
    output_shape: tuple[int, int] | None,
) -> np.ndarray:
    """
    Fetch one Sentinel-2 band from a COG HREF.

    Designed to run inside a ThreadPoolExecutor — all rasterio imports
    happen inside the function body to avoid cross-thread state issues.

    Args:
        signed_href:  Pre-signed COG URL.
        lon_min/lat_min/lon_max/lat_max: WGS84 bounding box.
        output_shape: (height, width) target pixels, or None for native res.

    Returns:
        float32 numpy array of shape output_shape (or native window shape).
    """
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.warp import transform_bounds
    from rasterio.windows import from_bounds

    with rasterio.open(signed_href) as src:
        src_crs = src.crs
        if src_crs and str(src_crs).upper() not in ("EPSG:4326", "CRS84"):
            left, bottom, right, top = transform_bounds(
                "EPSG:4326", src_crs, lon_min, lat_min, lon_max, lat_max
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


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


def fetch_sentinel2_true_color(
    bbox: list[float],
    year: int,
    output_size: int | tuple[int, int] | None = None,
) -> tuple[np.ndarray | None, tuple | None]:
    """
    Fetch the best-available Sentinel-2 true-color composite for a zone/year.

    Args:
        bbox:        [lon_min, lat_min, lon_max, lat_max] in WGS84.
        year:        Target year (searches within that calendar year).
        output_size: Target pixel dimensions. None = native 10 m/px resolution.
                     Pass an int for a square, or (height, width) tuple.

    Returns:
        (rgb_array, (red, green, blue, nir))  — uint8 (H,W,3) + float32 bands,
        or (None, None) if no usable imagery found.
    """
    import concurrent.futures

    import planetary_computer
    import rasterio
    from rasterio.warp import transform_bounds
    from rasterio.windows import from_bounds

    client = create_stac_client()
    lon_min, lat_min, lon_max, lat_max = bbox

    search_stages = [
        (f"{year}-02-01/{year}-02-28", 15, 30, "February strictly"),
        (f"{year}-01-15/{year}-03-15", 20, 60, "Jan 15 – Mar 15"),
        (f"{year}-01-01/{year}-12-31", 20, 100, "Full-year fallback"),
    ]

    best_date: str | None = None
    best_coverage_pct = 0.0
    best_cloud_cover = 100.0
    best_date_items: list = []

    for date_range, max_cloud, max_items, label in search_stages:
        logger.info("Evaluating candidates in %s (%s)…", label, date_range)
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

        # Group by date; deduplicate by MGRS tile ID
        date_groups: dict[str, list] = defaultdict(list)
        for item in items:
            date_str = item.datetime.strftime("%Y-%m-%d")
            tile_id = item.properties.get("s2:mgrs_tile", "")
            if not any(x.properties.get("s2:mgrs_tile") == tile_id for x in date_groups[date_str]):
                date_groups[date_str].append(item)

        stage_best_date: str | None = None
        stage_best_coverage = 0.0
        stage_best_cloud = 100.0
        stage_best_items: list = []

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
                                "EPSG:4326", src_crs, lon_min, lat_min, lon_max, lat_max
                            )
                        else:
                            left, bottom, right, top = lon_min, lat_min, lon_max, lat_max
                        window = from_bounds(left, bottom, right, top, src.transform)
                        test_data = src.read(
                            1, window=window, out_shape=(64, 64), boundless=True, fill_value=0
                        )
                        combined_mask |= test_data > 0
                        total_cloud += item.properties.get("eo:cloud_cover", 0.0)
                except Exception as exc:
                    logger.warning("Failed to inspect %s on %s: %s", item.id, date_str, exc)
                    continue

            coverage_pct = np.mean(combined_mask) * 100
            avg_cloud = total_cloud / len(group_items) if group_items else 100.0
            logger.info(
                "  Date %s: coverage=%.2f%%, avg_cloud=%.2f%% (%d tiles)",
                date_str, coverage_pct, avg_cloud, len(group_items),
            )

            if coverage_pct > stage_best_coverage + 1.0:
                stage_best_coverage, stage_best_cloud = coverage_pct, avg_cloud
                stage_best_date, stage_best_items = date_str, group_items
            elif abs(coverage_pct - stage_best_coverage) <= 1.0 and avg_cloud < stage_best_cloud:
                stage_best_coverage, stage_best_cloud = coverage_pct, avg_cloud
                stage_best_date, stage_best_items = date_str, group_items

        if stage_best_coverage > best_coverage_pct:
            best_coverage_pct = stage_best_coverage
            best_cloud_cover = stage_best_cloud
            best_date = stage_best_date
            best_date_items = stage_best_items

        if best_coverage_pct >= 98.0:
            logger.info(
                "Excellent coverage (%.2f%%) found in %s — stopping date search.",
                best_coverage_pct, label,
            )
            break
        else:
            logger.info(
                "Best coverage in %s was %.2f%% (< 98%%). Trying next stage…",
                label, best_coverage_pct,
            )

    if not best_date_items:
        logger.warning("No valid Sentinel-2 dates found with coverage.")
        return None, None

    logger.info(
        "Selected best date: %s (%.2f%% coverage, %d tiles)",
        best_date, best_coverage_pct, len(best_date_items),
    )

    # Resolve native output dimensions from B04 of the first tile
    try:
        first_item = best_date_items[0]
        red_href = planetary_computer.sign(first_item.assets["B04"].href)
        with rasterio.open(red_href) as src:
            src_crs = src.crs
            if src_crs and str(src_crs).upper() not in ("EPSG:4326", "CRS84"):
                left, bottom, right, top = transform_bounds(
                    "EPSG:4326", src_crs, lon_min, lat_min, lon_max, lat_max
                )
            else:
                left, bottom, right, top = lon_min, lat_min, lon_max, lat_max
            window = from_bounds(left, bottom, right, top, src.transform)

            if output_size is None:
                output_shape: tuple[int, int] = (int(round(window.height)), int(round(window.width)))
                logger.info("Native Sentinel-2 shape: %dx%d (10 m/px)", output_shape[1], output_shape[0])
            elif isinstance(output_size, int):
                output_shape = (output_size, output_size)
            else:
                output_shape = output_size
    except Exception as exc:
        logger.error("Failed to inspect native dimensions: %s", exc)
        return None, None

    out_h, out_w = output_shape

    # Download all bands for all tiles in parallel
    band_components: dict[str, list[np.ndarray]] = defaultdict(list)
    tasks: dict = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        for band in _S2_BANDS:
            for item in best_date_items:
                signed_href = planetary_computer.sign(item.assets[band].href)
                future = executor.submit(
                    _fetch_single_s2_band,
                    signed_href, lon_min, lat_min, lon_max, lat_max, output_shape,
                )
                tasks[future] = (band, item.id)

        concurrent.futures.wait(tasks.keys())

        for future, (band, item_id) in tasks.items():
            try:
                band_components[band].append(future.result())
            except Exception as exc:
                logger.warning("Failed to read %s for %s: %s", band, item_id, exc)

    if len(band_components) < 4:
        logger.warning("Failed to download all bands for selected tiles.")
        return None, None

    # Mosaic each band — max (non-zero) value wins
    bands_data: dict[str, np.ndarray] = {}
    for band in _S2_BANDS:
        merged = np.zeros((out_h, out_w), dtype=np.float32)
        for comp in band_components[band]:
            valid = comp > 0
            merged[valid] = comp[valid]
        bands_data[band] = merged

    red, green, blue, nir = (bands_data[b] for b in _S2_BANDS)

    # Simple cloud mask — pixels that are bright in all visible bands
    cloud_mask = (red > _CLOUD_MASK_THRESHOLD) & (green > _CLOUD_MASK_THRESHOLD) & (blue > _CLOUD_MASK_THRESHOLD)

    # Percentile stretch to 8-bit
    h, w = red.shape
    stretched = np.zeros((h, w, 3), dtype=np.uint8)
    for i, band_data in enumerate([red, green, blue]):
        land_pixels = band_data[~cloud_mask & (band_data > 0)]
        p2, p98 = (np.percentile(land_pixels, [2, 98]) if len(land_pixels) > 100 else (0, 3000))
        if p98 == p2:
            p98 = p2 + 1
        stretched[:, :, i] = np.clip((band_data - p2) / (p98 - p2) * 255, 0, 255).astype(np.uint8)

    stretched[cloud_mask] = [200, 200, 200]   # cloud pixels → light grey

    return stretched, (red, green, blue, nir)
