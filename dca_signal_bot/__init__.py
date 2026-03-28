from __future__ import annotations

from pathlib import Path
from pkgutil import extend_path

__all__ = ["__version__"]

__version__ = "0.1.0"

__path__ = extend_path(__path__, __name__)
_src_package = Path(__file__).resolve().parent.parent / "src" / "dca_signal_bot"
if _src_package.exists():
    __path__.append(str(_src_package))
