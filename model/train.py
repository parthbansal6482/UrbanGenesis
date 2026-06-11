"""
model/train.py

Fine-tunes SegFormer (nvidia/mit-b2) on SpaceNet 7 + Sentinel-2 tiles.
Uses HuggingFace Accelerate for mixed-precision and multi-GPU support.
"""

import torch
import torch.nn as nn
import yaml
import logging
from pathlib import Path
from torch.utils.data import DataLoader
from transformers import (
    SegformerForSemanticSegmentation,
    get_cosine_schedule_with_warmup,
)
from torch.optim import AdamW
import torch.nn.functional as F
from tqdm import tqdm
import numpy as np

from model.dataset import (
    SatelliteSegmentationDataset,
    get_train_transforms,
    get_val_transforms,
)

logger = logging.getLogger(__name__)


def compute_miou(preds: torch.Tensor, labels: torch.Tensor, num_classes: int) -> float:
    """Compute mean IoU across all classes, ignoring background (class 0)."""
    iou_per_class = []
    for cls in range(1, num_classes):
        pred_cls = (preds == cls)
        true_cls = (labels == cls)
        intersection = (pred_cls & true_cls).sum().float()
        union = (pred_cls | true_cls).sum().float()
        if union == 0:
            continue
        iou_per_class.append((intersection / union).item())
    return np.mean(iou_per_class) if iou_per_class else 0.0


def train(config_path: str = "config/settings.yaml"):
    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    mcfg = cfg["model"]
    if torch.cuda.is_available():
        device = torch.device("cuda")
    else:
        # Fall back to CPU on macOS to avoid known PyTorch MPS attention head backward-pass non-contiguous view bugs
        device = torch.device("cpu")

    num_classes = mcfg.get("num_classes", 7)

    # Load model — SegFormer balances accuracy and speed
    id2label = {int(k): v for k, v in cfg["classes"].items()}
    label2id = {v: k for k, v in id2label.items()}

    model = SegformerForSemanticSegmentation.from_pretrained(
        mcfg["backbone"],
        num_labels=num_classes,
        id2label=id2label,
        label2id=label2id,
        ignore_mismatched_sizes=True,
    )

    # Adapt SegFormer for 4-channel input (RGB + NIR)
    # The first layer is segformer.stages.0.patch_embeddings.proj
    conv = model.segformer.stages[0].patch_embeddings.proj
    if conv.in_channels != 4:
        new_conv = nn.Conv2d(
            in_channels=4,
            out_channels=conv.out_channels,
            kernel_size=conv.kernel_size,
            stride=conv.stride,
            padding=conv.padding,
            bias=conv.bias is not None
        )
        # Copy pretrained weights for RGB channels
        with torch.no_grad():
            new_conv.weight[:, :3, :, :] = conv.weight
            # Initialize the NIR channel weight with average of RGB weights
            new_conv.weight[:, 3, :, :] = conv.weight.mean(dim=1)
            if conv.bias is not None:
                new_conv.bias.copy_(conv.bias)
        model.segformer.stages[0].patch_embeddings.proj = new_conv
        model.config.num_channels = 4
        logger.info("Adapted SegFormer first convolution layer to accept 4-channel inputs.")

    model = model.to(device)

    # Collect tiles and labels for the first configured zone
    zone_keys = list(cfg.get("zones", {}).keys())
    zone_name = zone_keys[0] if zone_keys else "nashik_north"
    tile_dir = Path(cfg["paths"]["tiles"]) / zone_name
    tiles = sorted(tile_dir.glob("**/*.tif"))
    
    # Locate corresponding label PNGs: replaces /tiles/ with /labels/ and changes extension
    labels = [Path(str(t).replace("/tiles/", "/labels/").replace(".tif", ".png"))
              for t in tiles]
    tiles = [t for t, l in zip(tiles, labels) if l.exists()]
    labels = [l for l in labels if l.exists()]

    if not tiles:
        logger.warning("No tile/label pairs found in paths specified by settings.yaml.")
        return 0.0

    # 80/20 split
    n_train = int(0.8 * len(tiles))
    train_dataset = SatelliteSegmentationDataset(
        tiles[:n_train], labels[:n_train], get_train_transforms()
    )
    val_dataset = SatelliteSegmentationDataset(
        tiles[n_train:], labels[n_train:], get_val_transforms()
    )

    train_loader = DataLoader(
        train_dataset, batch_size=mcfg["batch_size"], shuffle=True,
        num_workers=4, pin_memory=True, drop_last=True,
    )
    val_loader = DataLoader(
        val_dataset, batch_size=mcfg["batch_size"], shuffle=False,
        num_workers=2, pin_memory=True,
    )

    optimizer = AdamW(
        model.parameters(),
        lr=mcfg["learning_rate"],
        weight_decay=mcfg["weight_decay"],
    )

    total_steps = len(train_loader) * mcfg["epochs"]
    warmup_steps = int(0.1 * total_steps)
    scheduler = get_cosine_schedule_with_warmup(optimizer, warmup_steps, total_steps)

    use_amp = mcfg["mixed_precision"] and device.type == "cuda"
    scaler = torch.cuda.amp.GradScaler(enabled=use_amp)

    # CrossEntropyLoss with label smoothing from config
    label_smoothing = mcfg.get("label_smoothing", 0.0)
    loss_fn = nn.CrossEntropyLoss(label_smoothing=label_smoothing)

    best_miou = 0.0
    patience_counter = 0
    ckpt_dir = Path(cfg["paths"]["checkpoints"])
    ckpt_dir.mkdir(parents=True, exist_ok=True)

    for epoch in range(mcfg["epochs"]):
        # --- Training loop ---
        model.train()
        epoch_loss = 0.0

        for batch in tqdm(train_loader, desc=f"Epoch {epoch+1} train"):
            pixel_values = batch["pixel_values"].to(device)
            labels_batch = batch["labels"].to(device)

            optimizer.zero_grad()
            if device.type == "cuda":
                with torch.cuda.amp.autocast(enabled=mcfg["mixed_precision"]):
                    outputs = model(pixel_values=pixel_values)
                    logits = outputs.logits
                    upsampled_logits = F.interpolate(
                        logits, size=labels_batch.shape[-2:],
                        mode="bilinear", align_corners=False
                    )
                    loss = loss_fn(upsampled_logits, labels_batch)
                scaler.scale(loss).backward()
                scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
                scaler.step(optimizer)
                scaler.update()
            else:
                outputs = model(pixel_values=pixel_values)
                logits = outputs.logits
                upsampled_logits = F.interpolate(
                    logits, size=labels_batch.shape[-2:],
                    mode="bilinear", align_corners=False
                )
                loss = loss_fn(upsampled_logits, labels_batch)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
                optimizer.step()
            scheduler.step()
            epoch_loss += loss.item()

        # --- Validation loop ---
        model.eval()
        all_preds, all_labels = [], []

        with torch.no_grad():
            for batch in tqdm(val_loader, desc=f"Epoch {epoch+1} val"):
                pixel_values = batch["pixel_values"].to(device)
                outputs = model(pixel_values=pixel_values)
                logits = outputs.logits  # (B, C, H/4, W/4)

                # Upsample to input resolution
                upsampled = F.interpolate(
                    logits, size=pixel_values.shape[-2:],
                    mode="bilinear", align_corners=False
                )
                preds = upsampled.argmax(dim=1).cpu()
                all_preds.append(preds)
                all_labels.append(batch["labels"])

        all_preds = torch.cat(all_preds)
        all_labels = torch.cat(all_labels)
        miou = compute_miou(all_preds, all_labels, num_classes)

        avg_loss = epoch_loss / len(train_loader)
        logger.info(f"Epoch {epoch+1} | Loss: {avg_loss:.4f} | mIoU: {miou:.4f}")

        # Early stopping + checkpoint saving
        if miou > best_miou:
            best_miou = miou
            patience_counter = 0
            model.save_pretrained(ckpt_dir / "best_model")
            logger.info(f"New best mIoU: {best_miou:.4f} — checkpoint saved")
        else:
            patience_counter += 1
            if patience_counter >= mcfg["early_stopping_patience"]:
                logger.info("Early stopping triggered.")
                break

    return best_miou
