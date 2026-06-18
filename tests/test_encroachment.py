import numpy as np
from analytics.encroachment import calculate_encroachment_stats, generate_encroachment_heatmap

def test_calculate_encroachment_stats():
    mask_before = np.zeros((10, 10), dtype=np.uint8)
    mask_before[0:5, :] = 3   # 50 dense_veg
    mask_before[5:7, :] = 5   # 20 bare_soil
    mask_before[7:9, :] = 4   # 20 water
    
    mask_after = mask_before.copy()
    mask_after[0, 0:10] = 1   # 10 pixels of dense_veg to buildings
    mask_after[5, 0:5] = 2    # 5 pixels of bare_soil to roads
    mask_after[7, 0:5] = 1    # 5 pixels of water to buildings
    
    stats = calculate_encroachment_stats(mask_before, mask_after, mapping_type="segformer")
    
    # Each pixel = 0.01 hectares
    # cropland_nature (3, 5) to infra (1, 2): 15 pixels = 0.15 ha
    # water (4) to infra (1, 2): 5 pixels = 0.05 ha
    assert np.isclose(stats["total_cropland_lost_ha"], 0.15)
    assert np.isclose(stats["total_water_lost_ha"], 0.05)

def test_generate_encroachment_heatmap():
    mask_before = np.array([
        [3, 4],  # vegetation, water
        [1, 0]   # building, background
    ], dtype=np.uint8)
    
    mask_after = np.array([
        [1, 1],  # transitioned to buildings
        [1, 0]   # building stays building, background stays background
    ], dtype=np.uint8)
    
    heatmap = generate_encroachment_heatmap(mask_before, mask_after, mapping_type="segformer")
    assert heatmap.shape == (2, 2, 3)
    
    # cropland (3) -> building (1): orange-red [239, 68, 68]
    assert np.all(heatmap[0, 0] == [239, 68, 68])
    # water (4) -> building (1): electric cyan [6, 182, 212]
    assert np.all(heatmap[0, 1] == [6, 182, 212])
    # existing infra (1 -> 1): slate grey [71, 85, 105]
    assert np.all(heatmap[1, 0] == [71, 85, 105])
    # background (0 -> 0): background [15, 23, 42]
    assert np.all(heatmap[1, 1] == [15, 23, 42])
