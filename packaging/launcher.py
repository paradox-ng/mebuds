"""Entry point for PyInstaller builds and the autostart entry of a source
checkout (both need a script rather than `python -m mebuds`)."""

import sys
from pathlib import Path

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mebuds.__main__ import main  # noqa: E402

raise SystemExit(main())
