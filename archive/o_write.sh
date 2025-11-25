#!/usr/bin/env bash
# Unified Write Optimizer (Expander) - Restore original text
# SPDX-License-Identifier: GPL-3.0-or-later
# Usage: cat optimized.txt | ./o_write.sh > original.txt

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODULE="$SCRIPT_DIR/../src/reversible_text.py"

python3 "$MODULE" --expand
