import numpy as np
import pytest
import rasterio
from etl.vegetation import compute_ndvi, compute_cropland_fraction

def test_ndvi_calculation_basic():
    # Simple math validation
    red = np.array([[100, 200], [50, 0]], dtype=np.float32)
    nir = np.array([[150, 100], [200, 0]], dtype=np.float32)
    denom = nir + red
    ndvi = (nir - red) / (denom + 1e-8)
    assert ndvi.min() >= -1.0
    assert ndvi.max() <= 1.0

def test_compute_ndvi_function(tmp_path):
    # Create a dummy 4-band tif (Red=band 1, NIR=band 4)
    # Must be a multiple of 16 for tiled TIFF writing
    tif_path = tmp_path / "dummy_stacked.tif"
    out_path = tmp_path / "dummy_ndvi.tif"
    
    data = np.zeros((4, 16, 16), dtype=np.uint16)
    data[0] = 100  # Red
    data[3] = 200  # NIR
    
    profile = {
        "driver": "GTiff",
        "dtype": "uint16",
        "width": 16,
        "height": 16,
        "count": 4,
        "crs": "EPSG:32643",
        "transform": rasterio.transform.from_origin(77.45, 13.10, 0.0001, 0.0001),
    }
    with rasterio.open(tif_path, "w", **profile) as dst:
        dst.write(data)
        
    ndvi = compute_ndvi(tif_path, out_path)
    assert ndvi.shape == (16, 16)
    # NDVI = (200 - 100) / (200 + 100) = 100 / 300 = 0.33333
    assert np.allclose(ndvi, 1.0 / 3.0)
    
    # Check output file exists and has correct format
    assert out_path.exists()
    with rasterio.open(out_path) as src:
        assert src.count == 1
        assert src.dtypes[0] == "float32"

def test_compute_cropland_fraction():
    # Mask containing different classes: 3=cropland, others=non-cropland
    mask = np.array([
        [0, 1, 2, 3],
        [3, 4, 5, 6],
        [3, 3, 0, 1]
    ], dtype=np.uint8)  # 4 cropland pixels out of 12
    
    fraction = compute_cropland_fraction(mask, cropland_class=3)
    assert np.isclose(fraction, 4.0 / 12.0)

    # Test empty mask
    empty_mask = np.zeros((0, 0), dtype=np.uint8)
    assert compute_cropland_fraction(empty_mask) == 0.0
