#!/bin/bash
# Output base64-encoded credentials for Render GOOGLE_CLOUD_VISION_CREDENTIALS_B64.
# Run from IFI Essay tool/ or pass path to credentials JSON.
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CREDS="${1:-$ROOT/credentials_vision.json}"
if [[ ! -f "$CREDS" ]]; then
  echo "Usage: $0 [path/to/credentials.json]" >&2
  echo "File not found: $CREDS" >&2
  exit 1
fi
echo "Copy the output below into Render env var GOOGLE_CLOUD_VISION_CREDENTIALS_B64:"
echo "---"
if command -v base64 &>/dev/null; then
  base64 -w0 "$CREDS" 2>/dev/null || base64 -i "$CREDS" | tr -d '\n'
else
  python3 -c "import base64,sys; print(base64.b64encode(open(sys.argv[1],'rb').read()).decode())" "$CREDS"
fi
echo ""
echo "---"
