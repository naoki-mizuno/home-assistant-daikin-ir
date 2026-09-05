"""Pure-Python IR protocol + codec library.

No Home Assistant imports live below this package, so it can be unit tested (or
reused by a CLI) on its own.
"""

from __future__ import annotations

from . import daikin312  # noqa: F401 - imported for its side effect: registration
from .protocol import get_protocol, protocol_labels

__all__ = ["get_protocol", "protocol_labels"]
