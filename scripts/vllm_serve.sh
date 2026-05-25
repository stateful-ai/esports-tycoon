#!/usr/bin/env bash
#
# Local vLLM bring-up for esports-tycoon's vLLM content backend.
#
# Boots an OpenAI-compatible Qwen 7B/8B server at http://localhost:8000/v1 — the
# endpoint `.env.example` / GAME_LLM_* point at, and the one the demo gate
# (`python -m esports_tycoon.vllm_demo preflight`) talks to. vLLM downloads the
# weights from the Hugging Face Hub on first boot (to ~/.cache/huggingface), so
# the first run is slow; subsequent runs reuse the cache.
#
# Requirements (not installable in CI — this is a GPU host script):
#   * an NVIDIA GPU with CUDA drivers (Qwen 7B needs ~16 GB VRAM at bf16; drop to
#     a smaller --max-model-len or an AWQ/GPTQ quant on smaller cards),
#   * Python 3.10+, and outbound access to the Hugging Face Hub for the weights.
#
# Usage:
#   scripts/vllm_serve.sh                 # install vllm if missing, then serve
#   scripts/vllm_serve.sh --no-install    # serve only (vllm already installed)
#   VLLM_MODEL=Qwen/Qwen3-8B scripts/vllm_serve.sh   # serve a different model
#
# Once it prints "Application startup complete", smoke it from another shell:
#   python -m esports_tycoon.vllm_demo smoke
#
set -euo pipefail

# --- Knobs (override via env) ------------------------------------------------
# The HF repo to serve. Qwen2.5-7B-Instruct is the M0 default (right-sized: 7B
# beats 32B on cost for this dialogue). Qwen3-8B is the 8B option.
VLLM_MODEL="${VLLM_MODEL:-Qwen/Qwen2.5-7B-Instruct}"
# The name clients ask for. MUST equal GAME_LLM_MODEL in your .env, or requests
# 404. Defaults to the value shipped in .env.example.
VLLM_SERVED_NAME="${VLLM_SERVED_NAME:-qwen2.5-7b-instruct}"
VLLM_HOST="${VLLM_HOST:-127.0.0.1}"
VLLM_PORT="${VLLM_PORT:-8000}"
# Cap the context to bound the KV-cache VRAM footprint; raise it if your card has
# headroom and you need longer prompts.
VLLM_MAX_MODEL_LEN="${VLLM_MAX_MODEL_LEN:-8192}"
# Anything extra to pass straight through to `vllm serve`
# (e.g. VLLM_EXTRA_ARGS="--quantization awq --gpu-memory-utilization 0.85").
VLLM_EXTRA_ARGS="${VLLM_EXTRA_ARGS:-}"

INSTALL=1
for arg in "$@"; do
    case "$arg" in
        --no-install) INSTALL=0 ;;
        -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
        *) echo "unknown flag: $arg" >&2; exit 2 ;;
    esac
done

# --- Install (idempotent) ----------------------------------------------------
if ! python -c "import vllm" >/dev/null 2>&1; then
    if [ "$INSTALL" -eq 1 ]; then
        echo ">> vllm not found; installing (this is a large, GPU-targeted download)..."
        python -m pip install --upgrade pip
        python -m pip install vllm
    else
        echo "ERROR: vllm is not installed and --no-install was given." >&2
        echo "       Run without --no-install, or: python -m pip install vllm" >&2
        exit 1
    fi
fi

# --- Serve -------------------------------------------------------------------
echo ">> Serving '$VLLM_MODEL' as '$VLLM_SERVED_NAME' at http://${VLLM_HOST}:${VLLM_PORT}/v1"
echo ">> First boot downloads the weights from Hugging Face; later boots reuse the cache."
echo ">> Smoke it once it's up:  python -m esports_tycoon.vllm_demo smoke"

# shellcheck disable=SC2086  # VLLM_EXTRA_ARGS is intentionally word-split.
exec vllm serve "$VLLM_MODEL" \
    --served-model-name "$VLLM_SERVED_NAME" \
    --host "$VLLM_HOST" \
    --port "$VLLM_PORT" \
    --max-model-len "$VLLM_MAX_MODEL_LEN" \
    --dtype auto \
    $VLLM_EXTRA_ARGS
