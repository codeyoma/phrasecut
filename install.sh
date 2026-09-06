#!/bin/bash
set -euo pipefail

phrasecut_project="$(cd "$(dirname "$0")" && pwd)"
phrasecut_app_dir="${PHRASECUT_APP_DIR:-$HOME/.local/share/phrasecut}"
phrasecut_bin_dir="${PHRASECUT_BIN_DIR:-$HOME/.local/bin}"
phrasecut_python="${PHRASECUT_PYTHON:-}"
if [[ -z "$phrasecut_python" ]]; then
  for candidate in python3.13 python3.12 python3.11 python3.14 python3; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; assert sys.version_info >= (3, 11)' 2>/dev/null; then
      phrasecut_python="$(command -v "$candidate")"
      break
    fi
  done
fi
if [[ -z "$phrasecut_python" ]]; then
  echo 'Python 3.11+ is required. Install Python, or set PHRASECUT_PYTHON to its executable.' >&2
  exit 1
fi
"$phrasecut_python" -c 'import sys, platform; assert sys.version_info >= (3, 11), "Python 3.11+ required"; assert (platform.system(), platform.machine()) == ("Darwin", "arm64"), "Local ASR requires Apple Silicon macOS"'
if [[ -d "$phrasecut_app_dir" && ! -f "$phrasecut_app_dir/.phrasecut-install" ]]; then
  echo "Refusing to replace an unmanaged directory: $phrasecut_app_dir" >&2
  exit 1
fi
if [[ -e "$phrasecut_bin_dir/phrasecut" || -L "$phrasecut_bin_dir/phrasecut" ]]; then
  if [[ "$(readlink "$phrasecut_bin_dir/phrasecut" || true)" != "$phrasecut_app_dir/venv/bin/phrasecut" ]]; then
    echo "An unrelated phrasecut command already exists in $phrasecut_bin_dir" >&2
    exit 1
  fi
fi
mkdir -p "$phrasecut_app_dir" "$phrasecut_bin_dir"
touch "$phrasecut_app_dir/.phrasecut-install"
if [[ ! -x "$phrasecut_app_dir/venv/bin/python" ]]; then
  "$phrasecut_python" -m venv "$phrasecut_app_dir/venv"
fi
"$phrasecut_app_dir/venv/bin/python" -m pip install --disable-pip-version-check "$phrasecut_project[asr]"
ln -sfn "$phrasecut_app_dir/venv/bin/phrasecut" "$phrasecut_bin_dir/phrasecut"
"$phrasecut_bin_dir/phrasecut" --version
case ":$PATH:" in
  *":$phrasecut_bin_dir:"*) ;;
  *) echo "Add this directory to your shell PATH: $phrasecut_bin_dir" ;;
esac
