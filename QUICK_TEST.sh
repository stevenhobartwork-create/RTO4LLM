#!/bin/bash
# Quick test wrapper - starts testing immediately without waiting for full file scan

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
WHITE='\033[1;37m'
BOLD='\033[1m'
RESET='\033[0m'

# Configuration
RTO="$SCRIPT_DIR/src/rto"
NUM_WORKERS=24
MIN_SIZE=1
MAX_SIZE=$((40 * 1024 * 1024))  # 40MB
WORK_DIR="/tmp/rto_quick_test"
SAMPLE_SIZE=50000  # Test on first 50k files found

echo -e "${CYAN}${BOLD}"
echo "═══════════════════════════════════════════════════════════════"
echo "  RTO QUICK STRESS TEST"
echo "═══════════════════════════════════════════════════════════════"
echo -e "${RESET}"

# Check if RTO exists
if [ ! -f "$RTO" ]; then
    echo -e "${RED}Error: RTO binary not found at $RTO${RESET}"
    echo "Compiling..."
    cd src && make && cd ..
fi

# Clean up old runs
sudo rm -rf "$WORK_DIR" 2>/dev/null || true
mkdir -p "$WORK_DIR"
chmod 777 "$WORK_DIR"

# Size buckets
SIZE_BUCKETS=("0-1KB" "1-10KB" "10-100KB" "100KB-1MB" "1-10MB" "10-40MB")

echo -e "${YELLOW}Finding files quickly (first ${SAMPLE_SIZE})...${RESET}"

# Start finding files in background, but don't wait for it to finish
(
    find /home /usr -type f \
        -size "+${MIN_SIZE}c" -size "-${MAX_SIZE}c" \
        ! -path "*/proc/*" \
        ! -path "*/sys/*" \
        ! -path "*/dev/*" \
        ! -path "*/run/*" \
        ! -path "*/.git/*" \
        ! -path "*/node_modules/*" \
        ! -path "*/__pycache__/*" \
        ! -path "*/venv/*" \
        ! -path "*/.venv/*" \
        ! -path "*/build/*" \
        ! -path "*/dist/*" \
        ! -path "*/.cache/*" \
        ! -path "*/tmp/*" \
        ! -path "*/.Trash/*" \
        2>/dev/null | head -n $SAMPLE_SIZE > "$WORK_DIR/all_files.txt"
    echo "DONE" > "$WORK_DIR/scan_done"
) &

SCAN_PID=$!

# Wait for at least 1000 files to be found
echo -e "${CYAN}Waiting for initial files...${RESET}"
while [ ! -f "$WORK_DIR/all_files.txt" ] || [ $(wc -l < "$WORK_DIR/all_files.txt" 2>/dev/null || echo 0) -lt 1000 ]; do
    sleep 0.5
    printf "."
done
echo ""

TOTAL_FILES=$(wc -l < "$WORK_DIR/all_files.txt")
echo -e "${GREEN}Found $TOTAL_FILES files so far, starting test NOW!${RESET}"

# Split files into worker queues
CHUNK_SIZE=$((TOTAL_FILES / NUM_WORKERS + 1))
split -l $CHUNK_SIZE --numeric-suffixes=1 --additional-suffix=.txt "$WORK_DIR/all_files.txt" "$WORK_DIR/queue_"

# Worker function (identical to RUN_SYSTEM_WIDE.sh)
worker() {
    local worker_id=$1
    local queue_file=$2
    local batch_file="$WORK_DIR/batch_${worker_id}.jsonl"
    local work_dir="$WORK_DIR/w${worker_id}_$$"
    
    mkdir -p "$work_dir" 2>/dev/null
    > "$batch_file"
    
    local count=0
    
    while IFS= read -r file; do
        [ ! -r "$file" ] 2>/dev/null && continue
        
        # Smart extension extraction
        local basename="${file##*/}"
        local ext="${basename##*.}"
        
        # Handle special files
        case "$basename" in
            README|README.*) ext="README" ;;
            LICENSE|LICENSE.*) ext="LICENSE" ;;
            Makefile|Makefile.*) ext="Makefile" ;;
            CHANGELOG|CHANGELOG.*) ext="CHANGELOG" ;;
            CONTRIBUTING|CONTRIBUTING.*) ext="CONTRIBUTING" ;;
            Dockerfile|Dockerfile.*) ext="Dockerfile" ;;
            CMakeLists.txt) ext="cmake" ;;
            *.tar.gz|*.tar.bz2|*.tar.xz) ext="archive" ;;
        esac
        
        # Skip if extension is same as filename (no real extension) or full path
        if [ "$ext" = "$basename" ] || [ "$ext" = "$file" ] || [[ "$ext" == *"/"* ]]; then
            ext="no-ext"
        fi
        
        local orig=$(stat -c%s "$file" 2>/dev/null || echo 0)
        [ "$orig" -eq 0 ] && continue
        
        local size_bucket
        if [ "$orig" -lt 1024 ]; then size_bucket="0-1KB"
        elif [ "$orig" -lt 10240 ]; then size_bucket="1-10KB"
        elif [ "$orig" -lt 102400 ]; then size_bucket="10-100KB"
        elif [ "$orig" -lt 1048576 ]; then size_bucket="100KB-1MB"
        elif [ "$orig" -lt 10485760 ]; then size_bucket="1-10MB"
        else size_bucket="10-40MB"
        fi
        
        # Create temp files with unique names
        local cfile="$work_dir/c_$$_$count"
        local rfile="$work_dir/r_$$_$count"
        
        # Compress and verify
        if timeout 15 $RTO --compress --ext "$ext" < "$file" > "$cfile" 2>/dev/null; then
            local comp=$(stat -c%s "$cfile" 2>/dev/null || echo 0)
            
            if timeout 15 $RTO --expand < "$cfile" > "$rfile" 2>/dev/null && cmp -s "$file" "$rfile" 2>/dev/null; then
                local ratio=$(( (orig - comp) * 100 / orig ))
                echo "{\"file\":\"$(basename "$file")\",\"ext\":\"$ext\",\"success\":true,\"original_bytes\":$orig,\"compressed_bytes\":$comp,\"compression_ratio\":$ratio,\"size_bucket\":\"$size_bucket\",\"worker\":$worker_id}" >> "$batch_file"
                ((count++))
            fi
            rm -f "$cfile" "$rfile" 2>/dev/null
        fi
    done < "$queue_file"
    
    echo "$count" > "$WORK_DIR/worker_${worker_id}_count.txt"
}

# Start workers
echo -e "${BLUE}Starting $NUM_WORKERS workers...${RESET}"
for i in $(seq 1 $NUM_WORKERS); do
    queue="$WORK_DIR/queue_$(printf "%02d" $i).txt"
    if [ -f "$queue" ]; then
        worker $i "$queue" &
    fi
done

# Live stats viewer
echo -e "${GREEN}Starting live stats display...${RESET}"
sleep 2

while true; do
    # Check if all workers are done
    RUNNING_WORKERS=$(jobs -r | wc -l)
    if [ $RUNNING_WORKERS -le 1 ]; then
        # Only the scan job (or nothing) is running
        break
    fi
    
    # Aggregate results
    cat "$WORK_DIR"/batch_*.jsonl 2>/dev/null > "$WORK_DIR/all_results.jsonl" || true
    
    # Show matrix
    clear
    python3 "$SCRIPT_DIR/testing/show_stats_matrix.py" "$WORK_DIR/all_results.jsonl" $TOTAL_FILES
    
    sleep 3
done

# Final display
clear
cat "$WORK_DIR"/batch_*.jsonl 2>/dev/null > "$WORK_DIR/all_results.jsonl" || true
python3 "$SCRIPT_DIR/testing/show_stats_matrix.py" "$WORK_DIR/all_results.jsonl" $TOTAL_FILES

echo ""
echo -e "${GREEN}${BOLD}Test complete!${RESET}"
echo ""
echo -e "Results saved to: ${CYAN}$WORK_DIR/all_results.jsonl${RESET}"
echo ""

# Show summary stats
TOTAL_TESTED=$(wc -l < "$WORK_DIR/all_results.jsonl" 2>/dev/null || echo 0)
echo -e "${WHITE}Summary:${RESET}"
echo -e "  Files scanned: ${YELLOW}$TOTAL_FILES${RESET}"
echo -e "  Files tested:  ${GREEN}$TOTAL_TESTED${RESET}"
echo -e "  Coverage:      ${CYAN}$(( TOTAL_TESTED * 100 / TOTAL_FILES ))%${RESET}"
echo ""

# Cleanup
wait
rm -rf "$WORK_DIR"

echo -e "${CYAN}Done!${RESET}"
