#!/usr/bin/env bash
set -euo pipefail

PDF_PATH="${1:-/Users/j/Documents/Dataclever/Manuales técnicos TEST/DOC-0136477A.pdf}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUT_DIR="${2:-$SCRIPT_DIR/pages}"

mkdir -p "$OUT_DIR"

render_page() {
  local page="$1"
  local name="$2"
  pdftoppm -f "$page" -l "$page" -r 160 -singlefile -png \
    "$PDF_PATH" "$OUT_DIR/$name"
}

render_page 17 p17
render_page 26 p26
render_page 27 p27
render_page 41 p41
render_page 69 p69
render_page 71 p71
render_page 200 p200
render_page 205 p205
render_page 231 end-231
render_page 232 end-232
render_page 233 end-233
render_page 236 p236
render_page 237 p237
render_page 238 p238
render_page 240 p240

echo "Rendered benchmark pages to $OUT_DIR"
