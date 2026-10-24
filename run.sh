#!/usr/bin/env bash
# Launch mebuds from the project directory.
cd "$(dirname "$(readlink -f "$0")")" || exit 1
exec python -m mebuds "$@"
