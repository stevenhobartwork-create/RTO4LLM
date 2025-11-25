#!/bin/bash
# =============================================================================
# RTO4LLM - Benchmark Script
# =============================================================================
# Benchmark script for Reversible Text Optimizer
# Tests Python and C++ implementations
#
# License: GPL-3.0-or-later
# Repository: https://github.com/StevenGITHUBwork/RTO4LLM
# Code contributions by GitHub Copilot (Claude Opus 4.5)
#
# Usage: ./benchmark.sh [test_file]
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_FILE="${1:-}"
ITERATIONS=10

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}"
echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║              REVERSIBLE TEXT OPTIMIZER - BENCHMARK (Python + C++)            ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Check/compile implementations
echo -e "${YELLOW}Checking implementations...${NC}"

# Python - always available
PYTHON_OK=true
echo -e "  ${GREEN}✓${NC} Python (reversible_text.py)"

# C++ - compile if needed
CPP_OK=false
CPP_BIN="$SCRIPT_DIR/rto_cpp"
if [[ -f "$SCRIPT_DIR/reversible_text.cpp" ]]; then
    echo -e "  ${YELLOW}⟳${NC} Compiling C++ (g++ -O3)..."
    if g++ -O3 -std=c++17 -o "$CPP_BIN" "$SCRIPT_DIR/reversible_text.cpp" 2>/dev/null; then
        CPP_OK=true
        echo -e "  ${GREEN}✓${NC} C++ (rto_cpp)"
    else
        echo -e "  ${RED}✗${NC} C++ compilation failed"
    fi
else
    echo -e "  ${RED}✗${NC} C++ source not found"
fi

echo ""

# Generate or use test file
if [[ -z "$TEST_FILE" ]]; then
    echo -e "${YELLOW}Generating test data...${NC}"
    TEST_FILE="/tmp/rto_benchmark_input.txt"
    
    # Combine multiple Python files for realistic test
    find "$SCRIPT_DIR" -name "*.py" -exec cat {} \; > "$TEST_FILE" 2>/dev/null || true
    
    # Add more if too small
    if [[ $(wc -c < "$TEST_FILE") -lt 10000 ]]; then
        for i in {1..10}; do
            cat "$TEST_FILE" >> "${TEST_FILE}.tmp" 2>/dev/null || true
        done
        mv "${TEST_FILE}.tmp" "$TEST_FILE" 2>/dev/null || true
    fi
fi

INPUT_SIZE=$(wc -c < "$TEST_FILE")
INPUT_LINES=$(wc -l < "$TEST_FILE")
echo -e "  Test file: $TEST_FILE"
echo -e "  Size: $INPUT_SIZE bytes, $INPUT_LINES lines"
echo ""

# Function to run benchmark
run_benchmark() {
    local name="$1"
    local cmd="$2"
    local iterations="${3:-$ITERATIONS}"
    
    echo -e "${BLUE}Testing: $name${NC}"
    
    # Warmup
    eval "$cmd" < "$TEST_FILE" > /tmp/rto_output_$$.tmp 2>/dev/null || true
    
    # Time compression
    local start=$(date +%s.%N)
    for ((i=0; i<iterations; i++)); do
        eval "$cmd" < "$TEST_FILE" > /tmp/rto_output_$$.tmp 2>/dev/null
    done
    local end=$(date +%s.%N)
    local compress_time=$(echo "$end - $start" | bc)
    local avg_compress=$(echo "scale=4; $compress_time / $iterations * 1000" | bc)
    
    # Get output size
    local output_size=$(wc -c < /tmp/rto_output_$$.tmp)
    local ratio=$(echo "scale=1; (1 - $output_size / $INPUT_SIZE) * 100" | bc)
    
    # Time expansion (if C++ or Python)
    if [[ "$cmd" == *"--compress"* ]]; then
        local expand_cmd="${cmd/--compress/--expand}"
        local expand_start=$(date +%s.%N)
        for ((i=0; i<iterations; i++)); do
            eval "$expand_cmd" < /tmp/rto_output_$$.tmp > /tmp/rto_expanded_$$.tmp 2>/dev/null
        done
        local expand_end=$(date +%s.%N)
        local expand_time=$(echo "$expand_end - $expand_start" | bc)
        local avg_expand=$(echo "scale=4; $expand_time / $iterations * 1000" | bc)
        
        # Check roundtrip
        if diff -q "$TEST_FILE" /tmp/rto_expanded_$$.tmp > /dev/null 2>&1; then
            local roundtrip="${GREEN}✓ OK${NC}"
        else
            local roundtrip="${RED}✗ MISMATCH${NC}"
        fi
    else
        local avg_expand="N/A"
        local roundtrip="N/A"
    fi
    
    # Calculate throughput
    local throughput=$(echo "scale=2; $INPUT_SIZE * $iterations / $compress_time / 1024 / 1024" | bc)
    
    echo -e "  Compress:   ${avg_compress} ms/iter"
    echo -e "  Expand:     ${avg_expand} ms/iter"
    echo -e "  Ratio:      ${ratio}%"
    echo -e "  Throughput: ${throughput} MB/s"
    echo -e "  Roundtrip:  $roundtrip"
    echo ""
    
    # Store results for comparison
    echo "$name,$avg_compress,$avg_expand,$ratio,$throughput" >> /tmp/rto_benchmark_results_$$.csv
    
    rm -f /tmp/rto_output_$$.tmp /tmp/rto_expanded_$$.tmp
}

# Clear results
echo "impl,compress_ms,expand_ms,ratio_pct,throughput_mbps" > /tmp/rto_benchmark_results_$$.csv

echo -e "${YELLOW}Running benchmarks ($ITERATIONS iterations each)...${NC}"
echo ""

# Python
run_benchmark "Python" "python3 $SCRIPT_DIR/reversible_text.py --compress --no-check" $ITERATIONS

# C++
if $CPP_OK; then
    run_benchmark "C++" "$CPP_BIN --compress" $ITERATIONS
fi

# Summary table
echo -e "${BLUE}"
echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║                              BENCHMARK SUMMARY                               ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

echo -e "${YELLOW}Results (lower is better for time, higher for throughput):${NC}"
echo ""
printf "%-12s %12s %12s %10s %12s\n" "Impl" "Compress(ms)" "Expand(ms)" "Ratio(%)" "Throughput"
printf "%-12s %12s %12s %10s %12s\n" "------------" "------------" "------------" "----------" "------------"

while IFS=',' read -r impl compress expand ratio throughput; do
    [[ "$impl" == "impl" ]] && continue  # Skip header
    printf "%-12s %12s %12s %10s %12s\n" "$impl" "$compress" "$expand" "$ratio" "${throughput} MB/s"
done < /tmp/rto_benchmark_results_$$.csv

echo ""

# Find winner
if [[ -f /tmp/rto_benchmark_results_$$.csv ]]; then
    winner=$(tail -n +2 /tmp/rto_benchmark_results_$$.csv | sort -t',' -k2 -n | head -1 | cut -d',' -f1)
    echo -e "${GREEN}Fastest: $winner${NC}"
fi

# Cleanup
rm -f /tmp/rto_benchmark_results_$$.csv

echo ""
echo -e "${BLUE}Benchmark complete.${NC}"
