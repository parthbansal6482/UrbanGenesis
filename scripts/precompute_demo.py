"""
scripts/precompute_demo.py

Generates precomputed results (verdict.json + mask_rgb_<year>.png) for the Gradio demo.
Usage: python scripts/precompute_demo.py --zone nashik_north --config config/settings.yaml
"""

import argparse
import json
import yaml
import logging
from pathlib import Path
from PIL import Image
Image.MAX_IMAGE_PIXELS = None
import sys
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
from analytics.abi import compute_abi_from_file, compute_cropland_loss_ha
from analytics.grader import generate_verdict

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Canonical colors from settings.yaml
CLASS_COLORS = {
    0: (0, 0, 0),        # background/clouds — black
    1: (220, 38, 38),    # buildings — red
    2: (130, 90, 44),    # roads — brown
    3: (212, 160, 23),   # cropland — gold
    4: (34, 139, 34),    # dense vegetation — green
    5: (30, 100, 200),   # water — blue
    6: (210, 180, 140),  # bare soil — tan
}

def mask_to_rgb(mask_arr):
    h, w = mask_arr.shape
    rgb = np.zeros((h, w, 3), dtype=np.uint8)
    for cls_id, color in CLASS_COLORS.items():
        rgb[mask_arr == cls_id] = color
    return rgb

def generate_true_color(tiff_path: Path, output_png_path: Path, target_size: int = 1024):
    import rasterio
    from rasterio.enums import Resampling
    logger.info(f"Generating true color RGB image from {tiff_path}...")
    try:
        with rasterio.open(tiff_path) as src:
            factor = max(1.0, src.width / target_size)
            new_width = int(src.width / factor)
            new_height = int(src.height / factor)
            
            rgb = src.read(
                [1, 2, 3],
                out_shape=(3, new_height, new_width),
                resampling=Resampling.bilinear
            ).astype(np.float32)
            
        stretched = np.zeros_like(rgb, dtype=np.uint8)
        for i in range(3):
            band = rgb[i]
            valid_pixels = band[(band > 0) & (band < 3000)]
            if len(valid_pixels) == 0:
                valid_pixels = band[band > 0]
            if len(valid_pixels) == 0:
                valid_pixels = band
            p2, p98 = np.percentile(valid_pixels, [2, 98])
            band_stretched = np.clip(band, p2, p98)
            diff = p98 - p2
            if diff == 0:
                diff = 1.0
            band_stretched = ((band_stretched - p2) / diff * 255.0).astype(np.uint8)
            stretched[i] = band_stretched
            
        rgb_img = np.transpose(stretched, (1, 2, 0))
        Image.fromarray(rgb_img).save(output_png_path)
        logger.info(f"Saved true color image to {output_png_path}")
    except Exception as e:
        logger.error(f"Failed to generate true color image: {e}")

def generate_ndvi_map(tiff_path: Path, output_png_path: Path, target_size: int = 1024):
    import rasterio
    from rasterio.enums import Resampling
    logger.info(f"Generating NDVI map from {tiff_path}...")
    try:
        with rasterio.open(tiff_path) as src:
            factor = max(1.0, src.width / target_size)
            new_width = int(src.width / factor)
            new_height = int(src.height / factor)
            
            red = src.read(1, out_shape=(new_height, new_width), resampling=Resampling.bilinear).astype(np.float32)
            if src.count >= 4:
                nir = src.read(4, out_shape=(new_height, new_width), resampling=Resampling.bilinear).astype(np.float32)
            else:
                nir = red * 1.5
                
        denominator = nir + red
        denominator[denominator == 0] = 1.0
        ndvi = (nir - red) / denominator
        ndvi = np.clip(ndvi, -1.0, 1.0)
        
        h, w = ndvi.shape
        rgb = np.zeros((h, w, 3), dtype=np.uint8)
        
        norm_ndvi = (ndvi + 0.1) / 0.7
        norm_ndvi = np.clip(norm_ndvi, 0.0, 1.0)
        
        for y in range(h):
            for x in range(w):
                val = norm_ndvi[y, x]
                if val < 0.2:
                    rgb[y, x] = (160, 120, 80)
                elif val < 0.5:
                    t = (val - 0.2) / 0.3
                    rgb[y, x] = (int(160 + t * 50), int(120 + t * 80), int(80 - t * 40))
                else:
                    t = (val - 0.5) / 0.5
                    rgb[y, x] = (int(210 - t * 176), int(200 - t * 61), int(40 + t * 4))
                    
        Image.fromarray(rgb).save(output_png_path)
        logger.info(f"Saved NDVI map to {output_png_path}")
    except Exception as e:
        logger.error(f"Failed to generate NDVI map: {e}")

def main():
    parser = argparse.ArgumentParser(description="Precompute FarmGuard results for demo.")
    parser.add_argument("--zone", required=True, help="Zone name from configuration")
    parser.add_argument("--config", default="config/settings.yaml", help="Path to settings.yaml")
    args = parser.parse_args()

    with open(args.config) as f:
        cfg = yaml.safe_load(f)

    if args.zone not in cfg["zones"]:
        raise ValueError(f"Zone '{args.zone}' not found in configuration.")

    zone_cfg = cfg["zones"][args.zone]
    mask_dir = Path(cfg["paths"]["masks"]) / args.zone
    raw_dir = Path(cfg["paths"]["raw_data"]) / args.zone
    precomputed_dir = Path(cfg["paths"]["precomputed"]) / args.zone
    precomputed_dir.mkdir(parents=True, exist_ok=True)

    mask_paths_by_year = {}
    
    # Gather stitched masks for each year
    for year in zone_cfg["years"]:
        mask_path = mask_dir / str(year) / "stitched_mask.png"
        if not mask_path.exists():
            logger.error(f"Stitched mask not found for {args.zone} — {year} at {mask_path}. "
                         "Please run inference first.")
            continue
        mask_paths_by_year[year] = mask_path

    if not mask_paths_by_year:
        logger.error(f"No masks found for {args.zone}. Cannot generate demo data.")
        return

    logger.info(f"Computing ABI timeseries for {args.zone}...")
    records = []
    for year in sorted(mask_paths_by_year.keys()):
        result = compute_abi_from_file(mask_paths_by_year[year])
        result["year"] = year
        
        # Add helper names matching UI fields
        mask_arr = np.array(Image.open(mask_paths_by_year[year]))
        result["soil_pixels"] = int((mask_arr == 6).sum())
        result["soil_pct"] = round(result["soil_pixels"] / mask_arr.size * 100, 2)
        result["buildings_pct"] = round(result["buildings_pixels"] / mask_arr.size * 100, 2)
        result["roads_pct"] = round(result["roads_pixels"] / mask_arr.size * 100, 2)
        result["vegetation_pct"] = round(result["vegetation_pixels"] / mask_arr.size * 100, 2)
        result["water_pct"] = round(result["water_pixels"] / mask_arr.size * 100, 2)
        
        records.append(result)

    # Calculate cropland loss (10m pixel resolution default = 10.0m)
    loss_ha = 0.0
    years_sorted = sorted(mask_paths_by_year.keys())
    if len(years_sorted) > 1:
        mask_before = np.array(Image.open(mask_paths_by_year[years_sorted[0]]))
        mask_after = np.array(Image.open(mask_paths_by_year[years_sorted[-1]]))
        loss_ha = compute_cropland_loss_ha(mask_before, mask_after, resolution_m=10.0)

    logger.info(f"Generating grading verdict for {args.zone}...")
    verdict = generate_verdict(records, args.zone, cropland_loss_ha=loss_ha)

    # Save verdict.json
    verdict_path = precomputed_dir / "verdict.json"
    with open(verdict_path, "w") as f:
        json.dump(verdict, f, indent=2)
    logger.info(f"Saved verdict JSON to {verdict_path}")

    # Generate RGB mask visualization for earliest and latest years
    target_years = [years_sorted[0], years_sorted[-1]] if len(years_sorted) > 1 else [years_sorted[0]]

    for year in target_years:
        mask_path = mask_paths_by_year[year]
        mask_arr = np.array(Image.open(mask_path))
        rgb_arr = mask_to_rgb(mask_arr)
        
        rgb_image_path = precomputed_dir / f"mask_rgb_{year}.png"
        Image.fromarray(rgb_arr).save(rgb_image_path)
        logger.info(f"Saved RGB mask visualization to {rgb_image_path}")

        # Also generate true-color and NDVI maps
        tiff_path = raw_dir / str(year) / "stacked_aligned.tif"
        if not tiff_path.exists():
            tiff_path = raw_dir / str(year) / "stacked.tif"

        if tiff_path.exists():
            generate_true_color(tiff_path, precomputed_dir / f"true_color_{year}.png")
            generate_ndvi_map(tiff_path, precomputed_dir / f"ndvi_map_{year}.png")
        else:
            logger.warning(f"Stacked tiff not found for {year} at {tiff_path}. Cannot generate true-color/NDVI maps.")

    logger.info(f"Precomputation for {args.zone} complete.")

if __name__ == "__main__":
    main()
