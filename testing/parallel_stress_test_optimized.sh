#!/bin/bash
#
# RTO Parallel Stress Test - OPTIMIZED VERSION
# Improvements:
# - Batch stats updates (reduce locking)
# - Direct file reading (no cat spawns)
# - Faster progress display
# - Pre-compiled RTO path
#

set -euo pipefail

# Configuration
NUM_WORKERS=12
RTO="/home/laptop/reversible_text_optimizer/src/rto"
PROJECTS_DIR="$HOME/Projects"
WORK_DIR="/tmp/rto_stress_$$"
STATS_FILE="/home/laptop/reversible_text_optimizer/testing/stress_stats.json"
LOG_FILE="/home/laptop/reversible_text_optimizer/testing/stress_test.log"
QUEUE_FILE="$WORK_DIR/queue.txt"
LOCK_FILE="$WORK_DIR/queue.lock"

# Resume mode - check for existing state
RESUME_MODE=false
if [ -f "/home/laptop/reversible_text_optimizer/testing/queue_backup.txt" ]; then
    echo "Found previous session - resuming!"
    RESUME_MODE=true
fi

# Initialize
mkdir -p "$WORK_DIR"

if [ "$RESUME_MODE" = true ]; then
    cp "/home/laptop/reversible_text_optimizer/testing/queue_backup.txt" "$QUEUE_FILE"
    echo "$(date): Resuming RTO parallel stress test" >> "$LOG_FILE"
else
    echo "[]" > "$STATS_FILE"
    echo "$(date): Starting RTO parallel stress test" > "$LOG_FILE"
    
    # Find all eligible files (1 byte to 40MB)
    echo "Scanning for files in $PROJECTS_DIR..."
    echo "This may take a minute for large directories..."
    find "$PROJECTS_DIR" -type f -size +0 -size -40M \( \
        -name "*.py" -o \
        -name "*.js" -o \
        -name "*.ts" -o \
        -name "*.jsx" -o \
        -name "*.tsx" -o \
        -name "*.c" -o \
        -name "*.cpp" -o \
        -name "*.h" -o \
        -name "*.hpp" -o \
        -name "*.rs" -o \
        -name "*.sh" -o \
        -name "*.bash" -o \
        -name "*.md" -o \
        -name "*.txt" -o \
        -name "*.json" -o \
        -name "*.yml" -o \
        -name "*.yaml" \
    \) 2>/dev/null > "$QUEUE_FILE" || true
fi

TOTAL_FILES=$(wc -l < "$QUEUE_FILE")
echo "Found $TOTAL_FILES files to test"
echo "Starting $NUM_WORKERS workers..."

# Function to get next file from queue
get_next_file() {
    local file=""
    (
        flock -x 200
        if [ -s "$QUEUE_FILE" ]; then
            file=$(head -n1 "$QUEUE_FILE")
            tail -n +2 "$QUEUE_FILE" > "$QUEUE_FILE.tmp"
            mv "$QUEUE_FILE.tmp" "$QUEUE_FILE"
            echo "$file"
        fi
    ) 200>"$LOCK_FILE"
}

# OPTIMIZED: Batch stats updates
update_stats_batch() {
    local batch_json="$1"
    (
        flock -x 201
        # Append all at once
        python3 -c "
import sys, json
stats = json.load(open('$STATS_FILE'))
batch = json.loads('''$batch_json''')
stats.extend(batch)
json.dump(stats, open('$STATS_FILE', 'w'), indent=2)
" 2>/dev/null || true
    ) 201>"${STATS_FILE}.lock"
}

# OPTIMIZED Worker function
worker() {
    local worker_id=$1
    local work_dir="$WORK_DIR/worker_$worker_id"
    mkdir -p "$work_dir"
    
    local batch=()
    local batch_count=0
    local BATCH_SIZE=50  # Update stats every 50 files
    
    while true; do
        local file=$(get_next_file)
        if [ -z "$file" ]; then
            # Flush remaining batch
            if [ ${#batch[@]} -gt 0 ]; then
                local batch_json="[$(IFS=,; echo "${batch[*]}")]"
                update_stats_batch "$batch_json"
            fi
            break
        fi
        
        # Determine file extension
        local ext="${file##*.}"
        case "$ext" in
            jsx|tsx) ext="js" ;;
            hpp) ext="cpp" ;;
            yaml) ext="yml" ;;
            bash) ext="sh" ;;
        esac
        
        local filename=$(basename "$file")
        local orig_size=$(stat -c%s "$file" 2>/dev/null || echo 0)
        
        # Skip if too large or empty
        if [ "$orig_size" -gt 41943040 ] || [ "$orig_size" -eq 0 ]; then
            continue
        fi
        
        local success=false
        local comp_size=0
        local compress_time=0
        local expand_time=0
        local error_msg=""
        
        # OPTIMIZED: Direct input, no cat spawn
        local start_ms=$(date +%s%3N)
        if timeout 30 "$RTO" --compress --ext "$ext" < "$file" > "$work_dir/c.rto" 2>/dev/null; then
            compress_time=$(($(date +%s%3N) - start_ms))
            comp_size=$(stat -c%s "$work_dir/c.rto" 2>/dev/null || echo 0)
            
            start_ms=$(date +%s%3N)
            if timeout 30 "$RTO" --expand < "$work_dir/c.rto" > "$work_dir/r" 2>/dev/null; then
                expand_time=$(($(date +%s%3N) - start_ms))
                
                if diff -q "$file" "$work_dir/r" >/dev/null 2>&1; then
                    success=true
                else
                    error_msg="diff_failed"
                fi
            else
                error_msg="expand_failed"
            fi
        else
            error_msg="compress_failed"
        fi
        
        local ratio=0
        if [ "$orig_size" -gt 0 ]; then
            ratio=$(python3 -c "print(round((1 - $comp_size / $orig_size) * 100, 2))" 2>/dev/null || echo 0)
        fi
        
        # Build JSON for batch
        local success_str="false"
        [ "$success" = true ] && success_str="true"
        
        local result="{\"worker\":$worker_id,\"file\":\"$filename\",\"ext\":\"$ext\",\"success\":$success_str,\"original_bytes\":$orig_size,\"compressed_bytes\":$comp_size,\"compression_ratio\":$ratio,\"compress_time_ms\":$compress_time,\"expand_time_ms\":$expand_time,\"error\":\"$error_msg\",\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
        
        batch+=("$result")
        ((batch_count++))
        
        # Batch update every BATCH_SIZE files
        if [ $batch_count -ge $BATCH_SIZE ]; then
            local batch_json="[$(IFS=,; echo "${batch[*]}")]"
            update_stats_batch "$batch_json"
            batch=()
            batch_count=0
        fi
        
        # Cleanup
        rm -f "$work_dir/c.rto" "$work_dir/r"
    done
    
    rmdir "$work_dir" 2>/dev/null || true
}

# Start workers in background
echo "Launching workers..."
for i in $(seq 1 $NUM_WORKERS); do
    worker $i &
done

# OPTIMIZED progress monitor
monitor_progress() {
    sleep 5
    local STATS_DISPLAY="/home/laptop/reversible_text_optimizer/testing/show_stats.py"
    while jobs %1 >/dev/null 2>&1; do
        python3 "$STATS_DISPLAY" "$STATS_FILE" "$TOTAL_FILES" 2>/dev/null || true
        sleep 5
    done
}

monitor_progress &
MONITOR_PID=$!

# Wait for all workers
wait

# Kill monitor
kill $MONITOR_PID 2>/dev/null || true

echo ""
echo "=========================================="
echo "       ALL WORKERS COMPLETED!"
echo "=========================================="
echo ""

# Show and save final statistics
FINAL_REPORT="/home/laptop/reversible_text_optimizer/testing/final_report.txt"
python3 <<EOPY
import sys
sys.path.insert(0, '/home/laptop/reversible_text_optimizer/testing')
from show_stats import save_final_report
save_final_report("$STATS_FILE", $TOTAL_FILES, "$FINAL_REPORT")
EOPY

# Cleanup
rm -rf "$WORK_DIR"
rm -f "/home/laptop/reversible_text_optimizer/testing/queue_backup.txt"

echo ""
echo "Full results saved to: $STATS_FILE"
echo "Log saved to: $LOG_FILE"
echo ""
echo "Done!"
