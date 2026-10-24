"""PyInstaller entry point (it needs a script, not `python -m mebuds`)."""

from mebuds.__main__ import main

raise SystemExit(main())
