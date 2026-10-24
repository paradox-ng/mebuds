#!/bin/sh
# Re-extract translatable strings into the .ts files (keeping existing
# translations), then compile them to the .qm files the app loads.
# Needs pyside6-lupdate and pyside6-lrelease (from PySide6).
set -e
cd "$(dirname "$0")/.."
pyside6-lupdate mebuds/*.py -ts mebuds/data/i18n/*.ts
pyside6-lrelease mebuds/data/i18n/*.ts
