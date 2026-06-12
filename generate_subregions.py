import os
import json
import numpy as np
import rasterio
from rasterio.enums import Resampling
from PIL import Image
import matplotlib.cm as cm
from pathlib import Path
from pyproj import Transformer
import shutil
import sys

# Ensure project root is in system path
sys.path.insert(0, str(Path(__file__).parent))
from analytics.abi import compute_abi, compute_cropland_loss_ha
from analytics.grader import generate_verdict

# Setup directories
PROJECT_ROOT = Path(__file__).parent
PRECOMPUTED_DIR = PROJECT_ROOT / "demo" / "precomputed"
RAW_DIR = PROJECT_ROOT / "data" / "raw"

# Canonical 7-class colors from settings.yaml
CLASS_COLORS = {
    0: (0, 0, 0),        # background/clouds — black
    1: (220, 38, 38),    # buildings — red
    2: (130, 90, 44),    # roads — brown
    3: (212, 160, 23),   # cropland — gold
    4: (34, 139, 34),    # dense vegetation — green
    5: (30, 100, 200),   # water — blue
    6: (210, 180, 140),  # bare soil — tan
}

def mask_to_rgb(mask):
    h, w = mask.shape
    rgb = np.zeros((h, w, 3), dtype=np.uint8)
    for cls_id, color in CLASS_COLORS.items():
        rgb[mask == cls_id] = color
    return rgb

# Transformer from Lat/Lon (EPSG:4326) to UTM 43N (EPSG:32643)
transformer = Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True)

def crop_and_resample(tiff_path, bbox, target_size=1024):
    lon_min, lat_min, lon_max, lat_max = bbox
    
    # Project coordinates to UTM 43N
    utm_min_x, utm_min_y = transformer.transform(lon_min, lat_min)
    utm_max_x, utm_max_y = transformer.transform(lon_max, lat_max)
    
    with rasterio.open(tiff_path) as src:
        # Create a window based on UTM bounds
        window = src.window(utm_min_x, utm_min_y, utm_max_x, utm_max_y)
        
        red = src.read(1, window=window, out_shape=(target_size, target_size), resampling=Resampling.bilinear).astype(np.float32)
        green = src.read(2, window=window, out_shape=(target_size, target_size), resampling=Resampling.bilinear).astype(np.float32)
        blue = src.read(3, window=window, out_shape=(target_size, target_size), resampling=Resampling.bilinear).astype(np.float32)
        nir = src.read(4, window=window, out_shape=(target_size, target_size), resampling=Resampling.bilinear).astype(np.float32)
        
    return red, green, blue, nir

def classify_model(red, green, blue, nir, model, device):
    """
    Classify using the trained SegFormer model.
    """
    import torch
    import torch.nn.functional as F
    
    # Prepare input tensor: shape (4, 1024, 1024)
    img = np.stack([red, green, blue, nir], axis=0)
    img_scaled = img / 10000.0
    means = np.array([0.485, 0.456, 0.406, 0.4])[:, None, None]
    stds  = np.array([0.229, 0.224, 0.225, 0.2])[:, None, None]
    img_norm = (img_scaled - means) / stds
    
    # Segment into four 512x512 tiles with no overlap to run batch inference
    tiles = [
        img_norm[:, 0:512, 0:512],
        img_norm[:, 0:512, 512:1024],
        img_norm[:, 512:1024, 0:512],
        img_norm[:, 512:1024, 512:1024]
    ]
    batch = torch.tensor(np.stack(tiles), dtype=torch.float32).to(device)
    
    with torch.no_grad():
        outputs = model(pixel_values=batch)
        logits = F.interpolate(outputs.logits, size=(512, 512), mode="bilinear", align_corners=False)
        preds = logits.argmax(dim=1).cpu().numpy().astype(np.uint8)
        
    # Stitch back to 1024x1024
    mask = np.zeros((1024, 1024), dtype=np.uint8)
    mask[0:512, 0:512] = preds[0]
    mask[0:512, 512:1024] = preds[1]
    mask[512:1024, 0:512] = preds[2]
    mask[512:1024, 512:1024] = preds[3]
    
    # Apply heuristic cloud mask as post-processing
    is_cloud = (red > 4000) & (green > 4000) & (blue > 4000)
    mask[is_cloud] = 0
    
    return mask

def load_trained_model():
    model_path = PROJECT_ROOT / "model" / "checkpoints" / "best_model"
    if not model_path.exists():
        return None, None
        
    import torch
    from transformers import SegformerForSemanticSegmentation
    
    device = torch.device("cpu")
    if torch.cuda.is_available():
        device = torch.device("cuda")
    elif torch.backends.mps.is_available():
        device = torch.device("mps")
        
    try:
        model = SegformerForSemanticSegmentation.from_pretrained(str(model_path)).to(device)
        model.eval()
        
        # Ensure first conv is 4 channels
        conv = model.segformer.stages[0].patch_embeddings.proj
        if conv.in_channels != 4:
            import torch.nn as nn
            new_conv = nn.Conv2d(
                in_channels=4,
                out_channels=conv.out_channels,
                kernel_size=conv.kernel_size,
                stride=conv.stride,
                padding=conv.padding,
                bias=conv.bias is not None
            )
            with torch.no_grad():
                new_conv.weight[:, :3, :, :] = conv.weight
                new_conv.weight[:, 3, :, :] = conv.weight.mean(dim=1)
                if conv.bias is not None:
                    new_conv.bias.copy_(conv.bias)
            model.segformer.stages[0].patch_embeddings.proj = new_conv.to(device)
            
        print("Trained model loaded successfully for subregion inference.")
        return model, device
    except Exception as e:
        print(f"Error loading trained model: {e}")
        return None, None

def generate_subregion(zone_key, bbox, is_mock=False):
    zone_dir = PRECOMPUTED_DIR / zone_key
    zone_dir.mkdir(parents=True, exist_ok=True)
    
    years = [2018, 2020, 2022, 2024]
    timeseries_stats = []
    
    # Try loading the model for real inference if available
    model, device = None, None
    if not is_mock:
        model, device = load_trained_model()
        # If no model found, fallback to mock generation for demo convenience
        if model is None:
            is_mock = True
            print(f"No trained model found. Falling back to mock generation for {zone_key}")
        
    first_year_mask = None
    last_year_mask = None

    for year in years:
        size = 1024
        if is_mock:
            # Generate mock segmentation mask representing active urban encroachment on farmland
            print(f"Generating mock farmland zone for {zone_key} - {year}...")
            mask = np.zeros((size, size), dtype=np.uint8)
            
            # Progressively increase the built-up area (1=buildings, 2=roads)
            # and reduce cropland (3) over time.
            t_pct = (year - 2018) / (2024 - 2018)
            
            # Encroachment severity varies by zone
            if zone_key == "nashik_north":
                urban_pct = 0.08 + t_pct * 0.16         # 8% to 24% built-up
                cropland_pct = 0.55 - t_pct * 0.18      # 55% to 37% cropland
            elif zone_key == "hubli_outskirts":
                urban_pct = 0.05 + t_pct * 0.22         # 5% to 27% built-up
                cropland_pct = 0.65 - t_pct * 0.25      # 65% to 40% cropland
            else:  # vijayawada_west
                urban_pct = 0.06 + t_pct * 0.10         # 6% to 16% built-up
                cropland_pct = 0.70 - t_pct * 0.12      # 70% to 58% cropland
                
            rng = np.random.default_rng(year)
            noise = rng.random((size, size))
            
            # Assign classes based on thresholds
            mask[noise < urban_pct * 0.70] = 1          # buildings
            mask[(noise >= urban_pct * 0.70) & (noise < urban_pct)] = 2  # roads
            
            crop_thresh = urban_pct + cropland_pct
            mask[(noise >= urban_pct) & (noise < crop_thresh)] = 3  # cropland (gold)
            
            veg_thresh = crop_thresh + 0.15
            mask[(noise >= crop_thresh) & (noise < veg_thresh)] = 4  # dense vegetation
            
            water_thresh = veg_thresh + 0.05
            mask[(noise >= veg_thresh) & (noise < water_thresh)] = 5  # water
            mask[noise >= water_thresh] = 6                           # bare soil
            
            mask_rgb = mask_to_rgb(mask)
            Image.fromarray(mask_rgb).save(zone_dir / f"mask_rgb_{year}.png")
            
            # True Color Image (RGB)
            tc = np.zeros((size, size, 3), dtype=np.uint8)
            tc[mask == 1] = (180, 180, 180) # concrete buildings
            tc[mask == 2] = (70, 70, 75)    # roads
            tc[mask == 3] = (212, 160, 23)  # cropland (goldish green)
            tc[mask == 4] = (34, 139, 34)   # dense forest green
            tc[mask == 5] = (30, 100, 200)  # blue water
            tc[mask == 6] = (210, 180, 140) # tan bare soil
            
            tc_noise = rng.normal(0, 12, (size, size, 3)).astype(np.int16)
            tc_noisy = np.clip(tc.astype(np.int16) + tc_noise, 0, 255).astype(np.uint8)
            Image.fromarray(tc_noisy).save(zone_dir / f"true_color_{year}.png")
            
            # NDVI map
            ndvi = np.zeros((size, size), dtype=np.float32)
            ndvi[mask == 1] = 0.04
            ndvi[mask == 2] = 0.02
            ndvi[mask == 3] = 0.42
            ndvi[mask == 4] = 0.65
            ndvi[mask == 5] = -0.15
            ndvi[mask == 6] = 0.10
            ndvi = ndvi + rng.normal(0, 0.04, (size, size))
            ndvi_clipped = np.clip(ndvi, -0.1, 0.6)
            norm_ndvi = (ndvi_clipped - (-0.1)) / (0.6 - (-0.1))
            cmap = cm.get_cmap("RdYlGn")
            ndvi_rgba = (cmap(norm_ndvi) * 255.0).astype(np.uint8)
            Image.fromarray(ndvi_rgba[:, :, :3]).save(zone_dir / f"ndvi_map_{year}.png")
            
        else:
            # Process real cropped TIFF
            tiff_path = RAW_DIR / zone_key / str(year) / "stacked_aligned.tif"
            if not tiff_path.exists():
                tiff_path = RAW_DIR / zone_key / str(year) / "stacked.tif"
                
            print(f"Cropping and processing real TIFF for {zone_key} - {year}...")
            red, green, blue, nir = crop_and_resample(tiff_path, bbox)
            
            # Stretched true color
            rgb = np.stack([red, green, blue])
            stretched = np.zeros_like(rgb, dtype=np.uint8)
            for i in range(3):
                band = rgb[i]
                land_pixels = band[(band > 0) & (band < 3000)]
                if len(land_pixels) == 0:
                    land_pixels = band
                p2, p95 = np.percentile(land_pixels, [2, 95])
                band_stretched = np.clip(band, p2, p95)
                diff = p95 - p2
                if diff == 0:
                    diff = 1.0
                stretched[i] = ((band_stretched - p2) / diff * 255.0).astype(np.uint8)
                
            true_color_img = np.transpose(stretched, (1, 2, 0))
            Image.fromarray(true_color_img).save(zone_dir / f"true_color_{year}.png")
            
            # NDVI map
            denom = nir + red
            denom[denom == 0] = 1.0
            ndvi = (nir - red) / denom
            ndvi_clipped = np.clip(ndvi, -0.1, 0.6)
            norm_ndvi = (ndvi_clipped - (-0.1)) / (0.6 - (-0.1))
            cmap = cm.get_cmap("RdYlGn")
            ndvi_rgba = (cmap(norm_ndvi) * 255.0).astype(np.uint8)
            Image.fromarray(ndvi_rgba[:, :, :3]).save(zone_dir / f"ndvi_map_{year}.png")
            
            # Classify using SegFormer model
            mask = classify_model(red, green, blue, nir, model, device)
            
            mask_rgb = mask_to_rgb(mask)
            Image.fromarray(mask_rgb).save(zone_dir / f"mask_rgb_{year}.png")

        # Track masks for cropland loss
        if year == 2018:
            first_year_mask = mask
        if year == 2024:
            last_year_mask = mask

        # Run canonical ABI calculations on the mask
        stats = compute_abi(mask)
        stats["year"] = year
        
        # Add friendly naming mapping for JSON structure
        stats["soil_pixels"] = int((mask == 6).sum())
        stats["soil_pct"] = round(stats["soil_pixels"] / mask.size * 100, 2)
        stats["buildings_pct"] = round(stats["buildings_pixels"] / mask.size * 100, 2)
        stats["roads_pct"] = round(stats["roads_pixels"] / mask.size * 100, 2)
        stats["vegetation_pct"] = round(stats["vegetation_pixels"] / mask.size * 100, 2)
        stats["water_pct"] = round(stats["water_pixels"] / mask.size * 100, 2)
        
        timeseries_stats.append(stats)
        
    timeseries_stats = sorted(timeseries_stats, key=lambda x: x["year"])
    
    # Calculate cropland loss (10m pixel resolution default = 10.0m)
    loss_ha = 0.0
    if first_year_mask is not None and last_year_mask is not None:
        loss_ha = compute_cropland_loss_ha(first_year_mask, last_year_mask, resolution_m=10.0)
        
    # Generate canonical Satyukt risk assessment verdict
    verdict = generate_verdict(timeseries_stats, zone_key, cropland_loss_ha=loss_ha)
    
    # Write verdict
    with open(zone_dir / "verdict.json", "w") as f:
        json.dump(verdict, f, indent=2)
        
    print(f"Generated subregion: {zone_key} | Grade {verdict['grade']} (ABI={verdict['abi']:.3f}, Crop Loss={loss_ha} ha)")

if __name__ == "__main__":
    # Clean up old precomputed folders (Bengaluru & Hyderabad)
    for folder in ["bengaluru_core", "bengaluru_regional", "hyderabad_core", "hyderabad_regional"]:
        old_dir = PRECOMPUTED_DIR / folder
        if old_dir.exists():
            shutil.rmtree(old_dir)
            print(f"Cleaned up legacy precomputed folder: {old_dir}")

    # Generate the new FarmGuard subregions
    generate_subregion("nashik_north", [73.72, 20.05, 73.98, 20.25], is_mock=True)
    generate_subregion("vijayawada_west", [80.45, 16.45, 80.70, 16.65], is_mock=True)
    generate_subregion("hubli_outskirts", [74.95, 15.28, 75.20, 15.48], is_mock=True)
    
    print("All FarmGuard subregions generated successfully!")
