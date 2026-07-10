"""
scripts/train_unet.py

Standalone CLI script to train the U-Net spatial growth forecasting model.
Saves model checkpoints for deployment/inference.
"""

import argparse
import logging
import os
import sys
from pathlib import Path

import torch
import torch.optim as optim
import yaml
from torch.utils.data import DataLoader

# Setup project root path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import CONFIG_PATH
from model.dataset import ChangeWeightedHybridLoss, GlobalPatchDataset, compute_class_weights
from model.architecture import UNet, ResNet34UNet

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("train_unet")


def main() -> None:
    parser = argparse.ArgumentParser(description="Train U-Net spatial growth forecasting model")
    parser.add_argument("--epochs", type=int, default=None, help="Number of training epochs")
    parser.add_argument("--batch-size", type=int, default=None, help="Batch size")
    parser.add_argument(
        "--save-path",
        type=str,
        default="model/checkpoints/unet_weights.pt",
        help="Path where trained model weights will be saved",
    )
    parser.add_argument("--lr", type=float, default=0.001, help="Learning rate")
    parser.add_argument("--weight-decay", type=float, default=1e-4, help="Weight decay")
    parser.add_argument("--change-weight", type=float, default=3.0, help="Loss weight modifier for transition pixels")
    parser.add_argument(
        "--model-type",
        type=str,
        choices=["standard", "resnet34"],
        default="resnet34",
        help="UNet encoder backbone style: 'standard' or 'resnet34'"
    )
    args = parser.parse_args()

    # Detect device
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type == "cpu":
        torch.set_num_threads(2)
        torch.set_num_interop_threads(1)
        logger.info("ENVIRONMENT: Local CPU detected.")
    else:
        logger.info("ENVIRONMENT: GPU detected.")

    # Load configuration
    with open(CONFIG_PATH) as f:
        cfg = yaml.safe_load(f)

    zones = cfg.get("zones", {})
    zone_keys = sorted(list(zones.keys()))

    logger.info("Initializing global training dataset (2017 & 2019 -> 2021 target)...")
    train_dataset = GlobalPatchDataset(zone_keys, 2017, 2019, 2021, patch_size=128, augment=True)

    # Set parameters depending on hardware/cli arguments
    cpu_cores = os.cpu_count() or 2
    if device.type == "cuda":
        batch_size = args.batch_size or 128
        num_workers = min(2, cpu_cores)
        pin_memory = True
        epochs = args.epochs or 50
        use_amp = True
        logger.info("PROFILING: GPU-optimal training settings active.")
    else:
        batch_size = args.batch_size or 8
        num_workers = 0
        pin_memory = False
        epochs = args.epochs or 5
        use_amp = False
        logger.info("PROFILING: Thermal-aware CPU settings active.")

    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=num_workers,
        pin_memory=pin_memory,
    )

    # Compute inverse frequency weights
    class_weights = compute_class_weights(train_dataset).to(device)
    logger.info(f"Class-imbalance weights: {class_weights.cpu().numpy()}")

    # Instantiate model
    if args.model_type == "resnet34":
        logger.info("Initializing U-Net with pre-trained ResNet34 backbone...")
        model = ResNet34UNet(in_channels=22, out_channels=6, pretrained=True).to(device)
    else:
        logger.info("Initializing standard U-Net with custom convolutions...")
        model = UNet(in_channels=22, out_channels=6).to(device)
    
    criterion = ChangeWeightedHybridLoss(change_weight=args.change_weight)
    optimizer = optim.Adam(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)

    logger.info(f"Starting training on {device} for {epochs} epochs...")
    model.train()
    for epoch in range(epochs):
        epoch_loss = 0.0
        for X_batch, y_batch, prev_batch in train_loader:
            X_batch, y_batch, prev_batch = X_batch.to(device), y_batch.to(device), prev_batch.to(device)
            optimizer.zero_grad()
            with torch.amp.autocast("cuda", enabled=use_amp):
                outputs = model(X_batch)
                loss = criterion(outputs, y_batch, prev_batch)
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            epoch_loss += loss.item() * X_batch.size(0)
        scheduler.step()
        logger.info(
            f"  Epoch {epoch+1}/{epochs} | Loss: {epoch_loss/len(train_dataset):.4f} | LR: {scheduler.get_last_lr()[0]:.6f}"
        )

    # Save model checkpoint
    save_path = Path(args.save_path)
    save_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), save_path)
    logger.info(f"Training completed. Checkpoint saved successfully to: {save_path}")


if __name__ == "__main__":
    main()
