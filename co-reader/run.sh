#!/bin/bash
# Co-Reader — one-command local launch.
set -e
cd "$(dirname "$0")"

# A conda/mamba env active in this shell (e.g. from your shell profile)
# leaves native library search paths set that our own venv's PyTorch/MLX
# don't expect — mixing them is a real cause of a native "malloc: double
# free" crash on macOS. Deactivate any active conda env and clear the
# DYLD_* vars conda's activation sets, before activating our own venv.
if [ -n "$CONDA_DEFAULT_ENV" ] && command -v conda >/dev/null 2>&1; then
  echo "Deactivating conda env '$CONDA_DEFAULT_ENV' to avoid native library conflicts…"
  eval "$(conda shell.bash hook)"
  while [ -n "$CONDA_DEFAULT_ENV" ]; do conda deactivate; done
fi
unset DYLD_LIBRARY_PATH DYLD_FALLBACK_LIBRARY_PATH DYLD_INSERT_LIBRARIES

# Make sure Ollama (the local preprocessing + narration brain) is running.
if ! curl -s -m 2 http://localhost:11434/api/version >/dev/null 2>&1; then
  echo "Starting Ollama…"
  brew services start ollama >/dev/null 2>&1 || (ollama serve &)
  sleep 2
fi

source .venv/bin/activate
echo "Co-Reader running at http://localhost:8765"
uvicorn app.main:app --port 8765
