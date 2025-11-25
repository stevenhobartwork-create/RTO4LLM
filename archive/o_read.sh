#!/usr/bin/env bash
# Unified Read Optimizer - Compress text for LLM context windows
# SPDX-License-Identifier: GPL-3.0-or-later
# Usage: cat file | ./o_read.sh > optimized.txt

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODULE="$SCRIPT_DIR/../src/reversible_text.py"

python3 "$MODULE" --compress --fuzz
