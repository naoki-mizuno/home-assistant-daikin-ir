"""Make `lib` importable without Home Assistant installed.

The tests only exercise `custom_components/daikin_ir/lib`, which is deliberately
free of Home Assistant imports. Importing it through the integration package
would drag `homeassistant` in.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "custom_components" / "daikin_ir"))
