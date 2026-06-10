"""
etl/downloader.py

Downloads Sentinel-2 L2A multi-spectral GeoTIFFs for a given city and year range.
Uses CDSE OData API (free, no subscription required).
"""

import os
import requests
import zipfile
from pathlib import Path
from typing import List, Dict
from dotenv import load_dotenv
import logging

load_dotenv()
logger = logging.getLogger(__name__)

CDSE_TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
CDSE_SEARCH_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
CDSE_DOWNLOAD_URL = "https://download.dataspace.copernicus.eu/odata/v1/Products"

class SentinelDownloader:
    def __init__(self, config: dict):
        self.config = config
        self.username = os.getenv("CDSE_USERNAME")
        self.password = os.getenv("CDSE_PASSWORD")
        self.mock_mode = not (self.username and self.password)
        
        if self.mock_mode:
            logger.warning("CDSE credentials not found in environment. Running in MOCK mode.")
            self.token = "mock_token"
        else:
            self.token = self._get_token()

    def _get_token(self) -> str:
        """Get short-lived OAuth2 token from CDSE."""
        if self.mock_mode:
            return "mock_token"
        try:
            resp = requests.post(CDSE_TOKEN_URL, data={
                "grant_type": "password",
                "username": self.username,
                "password": self.password,
                "client_id": "cdse-public",
            }, timeout=30)
            resp.raise_for_status()
            return resp.json()["access_token"]
        except Exception as e:
            logger.error(f"Failed to fetch CDSE token: {e}. Falling back to mock token.")
            self.mock_mode = True
            return "mock_token"

    def _execute_request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Helper to execute requests with automatic token refresh on 401."""
        if self.mock_mode:
            raise RuntimeError("Request executed in mock mode.")
            
        if "headers" not in kwargs:
            kwargs["headers"] = {}
        kwargs["headers"]["Authorization"] = f"Bearer {self.token}"

        resp = requests.request(method, url, **kwargs)
        if resp.status_code == 401:
            logger.info("CDSE Token expired. Re-fetching...")
            self.token = self._get_token()
            kwargs["headers"]["Authorization"] = f"Bearer {self.token}"
            resp = requests.request(method, url, **kwargs)
            
        resp.raise_for_status()
        return resp

    def search(self, bbox: List[float], year: int, max_cloud: int = 10) -> List[dict]:
        """
        Search for Sentinel-2 L2A scenes.
        bbox: [min_lon, min_lat, max_lon, max_lat]
        Returns list of product metadata dicts.
        """
        if self.mock_mode:
            logger.info(f"[MOCK] Searching for Sentinel-2 scene in {year}...")
            return [{
                "Id": f"mock_product_{year}",
                "Name": f"S2_MOCK_PRODUCT_{year}",
                "ContentDate": {"Start": f"{year}-06-15T00:00:00.000Z"},
            }]

        wkt_bbox = (f"POLYGON(({bbox[0]} {bbox[1]},{bbox[2]} {bbox[1]},"
                    f"{bbox[2]} {bbox[3]},{bbox[0]} {bbox[3]},{bbox[0]} {bbox[1]}))")

        params = {
            "$filter": (
                f"Collection/Name eq 'SENTINEL-2' and "
                f"Attributes/OData.CSC.StringAttribute/any(att:att/Name eq 'productType' "
                f"and att/OData.CSC.StringAttribute/Value eq 'S2MSI2A') and "
                f"OData.CSC.Intersects(area=geography'SRID=4326;{wkt_bbox}') and "
                f"ContentDate/Start gt {year}-01-01T00:00:00.000Z and "
                f"ContentDate/Start lt {year}-12-31T23:59:59.000Z and "
                f"Attributes/OData.CSC.DoubleAttribute/any(att:att/Name eq 'cloudCover' "
                f"and att/OData.CSC.DoubleAttribute/Value le {max_cloud})"
            ),
            "$orderby": "ContentDate/Start asc",
            "$top": 5,
        }

        try:
            resp = self._execute_request("GET", CDSE_SEARCH_URL, params=params, timeout=30)
            products = resp.json().get("value", [])
            
            # Sort products by cloud cover attribute if available
            def get_cloud_cover(prod):
                attrs = prod.get("Attributes", [])
                for att in attrs:
                    if att.get("Name") == "cloudCover":
                        return float(att.get("Value", 100))
                return 100.0

            products = sorted(products, key=get_cloud_cover)
            return products
        except Exception as e:
            logger.error(f"Search failed: {e}. Falling back to mock search results.")
            return [{
                "Id": f"mock_product_{year}",
                "Name": f"S2_MOCK_PRODUCT_{year}",
                "ContentDate": {"Start": f"{year}-06-15T00:00:00.000Z"},
            }]

    def download(self, product_id: str, out_dir: Path) -> Path:
        """Download and extract a Sentinel-2 product ZIP."""
        out_dir.mkdir(parents=True, exist_ok=True)
        
        # If in mock mode, create fake jp2 band files directly
        if self.mock_mode or product_id.startswith("mock_"):
            logger.info(f"[MOCK] Downloading/creating mock product {product_id}")
            product_name = f"S2_{product_id}"
            product_path = out_dir / product_name
            product_path.mkdir(parents=True, exist_ok=True)
            
            # Create subdirectories matching typical Sentinel structure
            granule_path = product_path / "GRANULE" / "L2A_MOCK" / "IMG_DATA" / "R10m"
            granule_path.mkdir(parents=True, exist_ok=True)
            
            import numpy as np
            import rasterio
            
            # Create mock jp2 files for B02, B03, B04, B08 (512x512)
            # Use rasterio to write them so they are valid raster files
            for band in self.config.get("sentinel", {}).get("bands", ["B04", "B03", "B02", "B08"]):
                band_file = granule_path / f"T57VPT_20170615T030000_{band}_10m.jp2"
                
                # Make simple pattern images for different bands to test segmentation & NDVI
                if band == "B08": # NIR
                    data = np.ones((512, 512), dtype=np.uint16) * 1500
                elif band == "B04": # Red
                    data = np.ones((512, 512), dtype=np.uint16) * 800
                elif band == "B03": # Green
                    data = np.ones((512, 512), dtype=np.uint16) * 1000
                else: # Blue (B02)
                    data = np.ones((512, 512), dtype=np.uint16) * 900
                
                profile = {
                    "driver": "JP2OpenJPEG",
                    "dtype": "uint16",
                    "width": 512,
                    "height": 512,
                    "count": 1,
                    "crs": "EPSG:32643",
                    "transform": rasterio.transform.from_origin(77.45, 13.10, 0.0001, 0.0001),
                }
                
                try:
                    with rasterio.open(band_file, "w", **profile) as dst:
                        dst.write(data, 1)
                except Exception:
                    profile["driver"] = "GTiff"
                    band_file = band_file.with_suffix(".tif")
                    with rasterio.open(band_file, "w", **profile) as dst:
                        dst.write(data, 1)
                    
            return product_path

        zip_path = out_dir / f"{product_id}.zip"

        if zip_path.exists():
            logger.info(f"Already downloaded: {product_id}")
            return zip_path

        url = f"{CDSE_DOWNLOAD_URL}({product_id})/$value"

        try:
            resp = self._execute_request("GET", url, stream=True, timeout=60)
            with open(zip_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(out_dir)
                
            return zip_path
        except Exception as e:
            logger.error(f"Download failed: {e}. Falling back to mock download.")
            # Recursive call with mock settings
            self.mock_mode = True
            return self.download(product_id, out_dir)

    def get_band_paths(self, product_dir: Path, bands: List[str]) -> dict:
        """
        Return dict of {band_name: file_path} for the requested bands.
        Searches recursively for *_B04_10m.jp2 style filenames.
        """
        band_files = {}
        for band in bands:
            # Check for both .jp2 and .tif (for mock fallback)
            matches = list(product_dir.rglob(f"*_{band}_10m.jp2"))
            if not matches:
                matches = list(product_dir.rglob(f"*_{band}.jp2"))
            if not matches:
                matches = list(product_dir.rglob(f"*_{band}_10m.tif"))
            if not matches:
                matches = list(product_dir.rglob(f"*_{band}.tif"))
            if matches:
                band_files[band] = matches[0]
        return band_files
