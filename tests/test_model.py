import numpy as np
import pytest
import torch
import torch.nn as nn
import rasterio
from PIL import Image
from pathlib import Path
from torch.utils.data import DataLoader
from transformers import SegformerForSemanticSegmentation, SegformerConfig
from model.dataset import SatelliteSegmentationDataset, get_train_transforms
from model.train import compute_miou

def test_dataset_output_shapes(tmp_path):
    tile_path = tmp_path / "tile.tif"
    label_path = tmp_path / "label.png"
    
    # 4-band tile data (512x512)
    tile_data = np.random.randint(0, 3000, size=(4, 512, 512), dtype=np.uint16)
    profile = {
        "driver": "GTiff",
        "dtype": "uint16",
        "width": 512,
        "height": 512,
        "count": 4,
        "crs": "EPSG:32643",
        "transform": rasterio.transform.from_origin(77.45, 13.10, 0.0001, 0.0001),
    }
    with rasterio.open(tile_path, "w", **profile) as dst:
        dst.write(tile_data)
        
    # Label mask data (512x512)
    label_data = np.random.randint(0, 6, size=(512, 512), dtype=np.uint8)
    Image.fromarray(label_data).save(label_path)
    
    dataset = SatelliteSegmentationDataset([tile_path], [label_path], transforms=get_train_transforms())
    assert len(dataset) == 1
    
    item = dataset[0]
    assert "pixel_values" in item
    assert "labels" in item
    assert item["pixel_values"].shape == (4, 512, 512)
    assert item["labels"].shape == (512, 512)
    assert item["pixel_values"].dtype == torch.float32
    assert item["labels"].dtype == torch.long

def test_miou_computation():
    preds = torch.tensor([[1, 2], [3, 0]])
    labels = torch.tensor([[1, 2], [3, 4]])
    # classes: 0 (bg, ignored), 1, 2, 3, 4 (5 classes total)
    # class 1: pred true, label true -> intersection=1, union=1 -> iou=1.0
    # class 2: pred true, label true -> intersection=1, union=1 -> iou=1.0
    # class 3: pred true, label true -> intersection=1, union=1 -> iou=1.0
    # class 4: pred false, label true -> intersection=0, union=1 -> iou=0.0
    # mean of class 1, 2, 3, 4 = (1.0 + 1.0 + 1.0 + 0.0) / 4 = 0.75
    miou = compute_miou(preds, labels, num_classes=5)
    assert np.isclose(miou, 0.75)

def test_model_4channel_adaptation():
    config = SegformerConfig(
        num_labels=6,
        in_channels=3,
    )
    model = SegformerForSemanticSegmentation(config)
    
    # Verify default model is 3-channel input
    conv = model.segformer.stages[0].patch_embeddings.proj
    assert conv.in_channels == 3
    
    # Adapt to 4 channels
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
    
    # Verify adapted model is 4-channel input
    adapted_conv = model.segformer.stages[0].patch_embeddings.proj
    assert adapted_conv.in_channels == 4
    
    # Test forward pass with 4-channel input
    dummy_input = torch.randn(1, 4, 256, 256)
    outputs = model(pixel_values=dummy_input)
    assert outputs.logits.shape[0] == 1
    assert outputs.logits.shape[1] == 6 # num_labels
