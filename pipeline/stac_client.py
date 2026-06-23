"""
pipeline/stac_client.py

Authenticated STAC API client factory for Microsoft Planetary Computer.

Isolates client initialization so that all pipeline modules share a
single, consistently-configured client without repeating boilerplate.

Usage:
    from pipeline.stac_client import create_stac_client
    client = create_stac_client()
    items = list(client.search(...).items())
"""

import logging

logger = logging.getLogger(__name__)

PLANETARY_COMPUTER_ENDPOINT = "https://planetarycomputer.microsoft.com/api/stac/v1"


def create_stac_client():
    """
    Create and return an authenticated pystac_client.Client pointed at
    Microsoft Planetary Computer.

    The ``planetary_computer.sign_inplace`` modifier automatically
    appends SAS tokens to asset HREFs so that COG reads succeed
    without requiring a registered account.

    Returns:
        pystac_client.Client — ready to search.

    Raises:
        ImportError: if pystac-client or planetary-computer are not installed.
    """
    try:
        import planetary_computer
        import pystac_client
    except ImportError:
        raise ImportError(
            "Required packages missing. Install with:\n"
            "  pip install pystac-client planetary-computer rasterio"
        )

    logger.debug("Opening STAC client at %s", PLANETARY_COMPUTER_ENDPOINT)
    return pystac_client.Client.open(
        PLANETARY_COMPUTER_ENDPOINT,
        modifier=planetary_computer.sign_inplace,
    )
