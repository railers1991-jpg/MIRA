#!/usr/bin/env bash
# Run the MIRA brain in development mode.
set -euo pipefail

cd "$(dirname "$0")/../brain"

if [[ ! -d .venv ]]; then
    python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

pip install -q -e .

exec mira-brain
