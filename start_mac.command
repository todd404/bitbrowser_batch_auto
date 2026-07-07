#!/bin/zsh

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
ROOT_DIR="$SCRIPT_DIR"
VENV_DIR="$ROOT_DIR/.venv"
VENV_PY="$VENV_DIR/bin/python"
DEFAULT_CONFIG="configs/app.example.yaml"

print_usage() {
  cat <<'EOF'
Usage:
  ./start_mac.command
  ./start_mac.command desktop [extra ui args...]
  ./start_mac.command web [extra ui args...]

Modes:
  desktop   Launch the native desktop UI (default)
  web       Launch the web UI in the default browser

Examples:
  ./start_mac.command
  ./start_mac.command web --port 8765
  ./start_mac.command desktop --host 127.0.0.1
EOF
}

ensure_python3() {
  if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 was not found. Please install Python 3 first."
    exit 1
  fi
}

ensure_venv() {
  ensure_python3
  python3 "$ROOT_DIR/scripts/setup_venv.py"
}

MODE="desktop"

if [[ $# -gt 0 ]]; then
  case "$1" in
    desktop|web)
      MODE="$1"
      shift
      ;;
    -h|--help|help)
      print_usage
      exit 0
      ;;
    *)
      echo "Unknown mode: $1"
      echo
      print_usage
      exit 1
      ;;
  esac
fi

cd "$ROOT_DIR"
ensure_venv

CMD=("$VENV_PY" -m bitbrowser_auto ui --config "$DEFAULT_CONFIG")
if [[ "$MODE" == "web" ]]; then
  CMD+=("--web")
fi
CMD+=("$@")

echo "Starting bitbrowser-auto in $MODE mode ..."
exec "${CMD[@]}"
