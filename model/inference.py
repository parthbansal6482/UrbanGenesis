"""
model/inference.py

Runs batch inference on a directory of 512x512 tiles.
Stitches tile masks back into a full-scene mask using the tiles_metadata.json.
"""

import numpy as np
import torch
import torch.nn.functional as F
import rasterio
from transformers import SegformerForSemanticSegmentation
from pathlib import Path
from PIL import Image
Image.MAX_IMAGE_PIXELS = None
import json
import logging
from tqdm import tqdm

logger = logging.getLogger(__name__)

CLASS_COLORS = {
    0: (0, 0, 0),        # background — black
    1: (220, 38, 38),    # buildings — red
    2: (180, 120, 60),   # roads — brown
    3: (34, 139, 34),    # dense vegetation — green
    4: (30, 100, 200),   # water — blue
    5: (210, 180, 140),  # bare soil — tan
}


def load_model(checkpoint_dir: str, device: torch.device):
    """Loads a SegFormer model, adapting it for 4 channels if it has 3 in config."""
    checkpoint_path = Path(checkpoint_dir)
    try:
        model = SegformerForSemanticSegmentation.from_pretrained(checkpoint_dir)
    except Exception as e:
        logger.info(f"Normal from_pretrained failed: {e}. Attempting manual 4-channel initialization...")
        from transformers import SegformerConfig
        config = SegformerConfig.from_pretrained(checkpoint_dir)
        model = SegformerForSemanticSegmentation(config)
        
        # Adapt first conv to 4 channels
        import torch.nn as nn
        conv = model.segformer.stages[0].patch_embeddings.proj
        new_conv = nn.Conv2d(
            in_channels=4,
            out_channels=conv.out_channels,
            kernel_size=conv.kernel_size,
            stride=conv.stride,
            padding=conv.padding,
            bias=conv.bias is not None
        )
        model.segformer.stages[0].patch_embeddings.proj = new_conv
        
        # Load weights
        bin_path = checkpoint_path / "pytorch_model.bin"
        safetensors_path = checkpoint_path / "model.safetensors"
        
        if safetensors_path.exists():
            from safetensors.torch import load_file
            state_dict = load_file(safetensors_path)
        else:
            state_dict = torch.load(bin_path, map_location="cpu")
            
        model.load_state_dict(state_dict)

    # Ensure stages[0] is 4-channel
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
        model.segformer.stages[0].patch_embeddings.proj = new_conv

    model.eval().to(device)
    return model


def run_inference_on_tiles(
    tile_dir: Path,
    checkpoint_dir: str,
    output_dir: Path,
    config: dict,
    batch_size: int = 8,
) -> Path:
    """
    Runs model inference on all tiles, saves per-tile masks,
    then updates metadata with mask paths.
    """
    if torch.cuda.is_available():
        device = torch.device("cuda")
    elif torch.backends.mps.is_available():
        device = torch.device("mps")
    else:
        device = torch.device("cpu")
        
    model = load_model(checkpoint_dir, device)

    meta_path = tile_dir / "tiles_metadata.json"
    with open(meta_path) as f:
        metadata = json.load(f)

    tile_paths = [Path(m["path"]) for m in metadata]
    output_dir.mkdir(parents=True, exist_ok=True)

    all_mask_paths = []

    # Process in batches
    for batch_start in tqdm(range(0, len(tile_paths), batch_size), desc="Inference"):
        batch_meta = metadata[batch_start : batch_start + batch_size]
        batch_tiles = []

        for m in batch_meta:
            with rasterio.open(m["path"]) as src:
                arr = src.read().astype(np.float32)  # (4, H, W)
            # Normalise (same stats as training, scale to [0,1] first)
            arr = arr / 10000.0
            means = np.array([0.485, 0.456, 0.406, 0.4])[:, None, None]
            stds  = np.array([0.229, 0.224, 0.225, 0.2])[:, None, None]
            arr = (arr - means) / stds
            batch_tiles.append(arr)

        batch_tensor = torch.tensor(np.stack(batch_tiles), dtype=torch.float32).to(device)

        with torch.no_grad():
            if device.type == "cuda":
                with torch.amp.autocast(device_type="cuda"):
                    outputs = model(pixel_values=batch_tensor)
            else:
                outputs = model(pixel_values=batch_tensor)
            logits = F.interpolate(
                outputs.logits,
                size=batch_tensor.shape[-2:],
                mode="bilinear",
                align_corners=False,
            )
            preds = logits.argmax(dim=1).cpu().numpy().astype(np.uint8)

        for pred, meta in zip(preds, batch_meta):
            mask_path = output_dir / Path(meta["path"]).name.replace(".tif", "_mask.png")
            Image.fromarray(pred).save(mask_path)
            meta["mask_path"] = str(mask_path)
            all_mask_paths.append(mask_path)

    # Save updated metadata with mask paths
    with open(output_dir / "masks_metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    logger.info(f"Inference complete. {len(all_mask_paths)} masks saved.")
    return output_dir


def stitch_tiles_to_scene(
    masks_metadata_path: Path,
    output_scene_path: Path,
    crop: int = 32,
) -> Path:
    """
    Stitches tile masks back into a single full-scene mask using tiles metadata.
    Uses PIL to assemble the final image.
    Applies boundary-aware border cropping to eliminate convolution padding edge artifacts.
    """
    with open(masks_metadata_path) as f:
        metadata = json.load(f)
        
    if not metadata:
        raise ValueError("Metadata is empty.")
        
    # Read heights, widths, and placements
    row_ends = [m["row_start"] + m["height"] for m in metadata]
    col_ends = [m["col_start"] + m["width"] for m in metadata]
    max_height = max(row_ends)
    max_width = max(col_ends)
    
    full_mask = np.zeros((max_height, max_width), dtype=np.uint8)
    
    for m in metadata:
        mask_path = Path(m["mask_path"])
        mask_arr = np.array(Image.open(mask_path))
        r_start = m["row_start"]
        c_start = m["col_start"]
        w = m["width"]
        h = m["height"]
        
        # Apply boundary-aware cropping
        r_s_crop = crop if r_start > 0 else 0
        r_e_crop = crop if (r_start + h) < max_height else 0
        c_s_crop = crop if c_start > 0 else 0
        c_e_crop = crop if (c_start + w) < max_width else 0
        
        r_s_full = r_start + r_s_crop
        r_e_full = r_start + h - r_e_crop
        c_s_full = c_start + c_s_crop
        c_e_full = c_start + w - c_e_crop
        
        r_s_mask = r_s_crop
        r_e_mask = h - r_e_crop
        c_s_mask = c_s_crop
        c_e_mask = w - c_e_crop
        
        if r_e_full > r_s_full and c_e_full > c_s_full:
            full_mask[r_s_full : r_e_full, c_s_full : c_e_full] = mask_arr[r_s_mask : r_e_mask, c_s_mask : c_e_mask]
        
    output_scene_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(full_mask).save(output_scene_path)
    logger.info(f"Stitched mask saved to {output_scene_path}")
    return output_scene_path


def mask_to_rgb(mask: np.ndarray) -> np.ndarray:
    """Convert class index mask to RGB visualisation."""
    rgb = np.zeros((*mask.shape, 3), dtype=np.uint8)
    for cls_id, color in CLASS_COLORS.items():
        rgb[mask == cls_id] = color
    return rgb
