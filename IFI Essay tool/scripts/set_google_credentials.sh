#!/usr/bin/env bash
# Export GOOGLE_APPLICATION_CREDENTIALS for this terminal session.
# Run once per terminal:  source scripts/set_google_credentials.sh
# Or with a specific key file: source scripts/set_google_credentials.sh /path/to/key.json

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ -n "$1" ]]; then
  KEY_PATH="$1"
elif [[ -n "$GOOGLE_CREDENTIALS_PATH" ]]; then
  KEY_PATH="$GOOGLE_CREDENTIALS_PATH"
elif [[ -f "$PROJECT_DIR/google-credentials.json" ]]; then
  KEY_PATH="$PROJECT_DIR/google-credentials.json"
else
  echo "No key file found. Either put google-credentials.json in the project dir, or run:"
  echo "  source scripts/set_google_credentials.sh /path/to/key.json"
  echo "Or: export GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json"
  return 2 2>/dev/null || exit 2
fi

if [[ ! -f "$KEY_PATH" ]]; then
  echo "Error: Key file not found: $KEY_PATH"
  return 1 2>/dev/null || exit 1
fi

export GOOGLE_APPLICATION_CREDENTIALS="$KEY_PATH"
echo "Set for this session: GOOGLE_APPLICATION_CREDENTIALS=$KEY_PATH"
