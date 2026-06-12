import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Import the demo app from the demo package
from demo.app import demo

if __name__ == "__main__":
    demo.launch()
