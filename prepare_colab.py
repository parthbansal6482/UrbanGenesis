import zipfile
from pathlib import Path

def main():
    zip_path = Path("colab_package.zip")
    print("Creating colab_package.zip for Google Colab...")
    
    # We use a stride of 4 to select every 4th tile. 
    # This reduces the dataset size, which is perfect for fine-tuning Segformer on a Colab T4 GPU.
    stride = 4
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # 1. Zip source directories (excluding pycache)
        for folder in ["model", "config", "scripts", "analytics", "etl"]:
            p = Path(folder)
            if p.exists():
                print(f"  Zipping source directory: {folder}...")
                for path in p.rglob('*'):
                    if path.is_file() and "__pycache__" not in str(path):
                        zipf.write(path)
                        
        # 2. Zip tiles and labels (strided to reduce size)
        tile_paths = sorted(Path("data/tiles").glob("**/*.tif"))
        selected_tiles = tile_paths[::stride]
        
        print(f"  Selected {len(selected_tiles)} representative tiles out of {len(tile_paths)} total across all zones.")
        
        zipped_count = 0
        for path in selected_tiles:
            # Locate corresponding label PNG (replaces /tiles/ with /labels/ and .tif with .png)
            label_path = Path(str(path).replace("/tiles/", "/labels/").replace(".tif", ".png"))
            if label_path.exists():
                zipf.write(path)
                zipf.write(label_path)
                zipped_count += 1
                
        print(f"  Zipped {zipped_count} image/label pairs successfully.")
            
    print(f"\nCreated archive: {zip_path}")
    if zip_path.exists():
        print(f"File size: {zip_path.stat().st_size / 1024 / 1024:.2f} MB")
    print("You can now download this zip, upload it to Colab, and run the notebook.")

if __name__ == "__main__":
    main()
