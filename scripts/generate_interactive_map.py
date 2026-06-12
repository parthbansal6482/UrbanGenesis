import rasterio
from rasterio.warp import transform_bounds
import folium
from pathlib import Path
import sys

def main():
    print("Generating interactive Folium map for Bengaluru...")
    
    precomputed_dir = Path("/Users/parthbansal/Projects/UrbanGenesis/demo/precomputed/bengaluru")
    raw_2017_tiff = Path("/Users/parthbansal/Projects/UrbanGenesis/data/raw/bengaluru/2017/stacked.tif")
    
    if not raw_2017_tiff.exists():
        print(f"Error: Reference TIFF not found at {raw_2017_tiff}. Cannot compute bounds.")
        sys.exit(1)
        
    # 1. Compute geographic bounds in WGS84 (lat/lon)
    with rasterio.open(raw_2017_tiff) as src:
        # transform bounds from EPSG:32643 (UTM 43N) to EPSG:4326 (WGS84)
        min_lon, min_lat, max_lon, max_lat = transform_bounds(src.crs, "EPSG:4326", *src.bounds)
        
    # Folium expects [[min_lat, min_lon], [max_lat, max_lon]]
    bounds = [[min_lat, min_lon], [max_lat, max_lon]]
    center_lat = (min_lat + max_lat) / 2
    center_lon = (min_lon + max_lon) / 2
    
    # 2. Initialize Folium Map centered on the target area
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=12,
        control_scale=True,
    )
    
    # 3. Add Google Satellite Base Map
    folium.TileLayer(
        tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
        attr="Google",
        name="Google Satellite (Base)",
        overlay=False,
        control=True
    ).add_to(m)
    
    # OpenStreetMap is added by default, but let's label it clearly
    folium.TileLayer(
        tiles="openstreetmap",
        name="OpenStreetMap (Base)",
        overlay=False,
        control=True
    ).add_to(m)
    
    # 4. Add overlays
    overlay_files = {
        "2017 True Color (RGB)": precomputed_dir / "true_color_2017.png",
        "2023 True Color (RGB)": precomputed_dir / "true_color_2023.png",
        "2017 NDVI Vegetation": precomputed_dir / "ndvi_map_2017.png",
        "2023 NDVI Vegetation": precomputed_dir / "ndvi_map_2023.png",
    }
    
    for layer_name, path in overlay_files.items():
        if path.exists():
            folium.raster_layers.ImageOverlay(
                image=str(path),
                bounds=bounds,
                name=layer_name,
                opacity=0.75,
                show=False, # uncheck by default so it's not cluttered
                interactive=True,
                cross_origin=False,
                zindex=1
            ).add_to(m)
            print(f"Added layer: {layer_name}")
        else:
            print(f"Warning: Layer file not found at {path}")
            
    # Add layer control panel
    folium.LayerControl(collapsed=False).add_to(m)
    
    # 5. Save the final interactive HTML
    output_html = Path("/Users/parthbansal/Projects/UrbanGenesis/demo/interactive_map.html")
    m.save(str(output_html))
    print(f"Interactive map successfully saved to: {output_html}")

if __name__ == "__main__":
    main()
