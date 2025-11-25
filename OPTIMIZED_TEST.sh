#!/bin/bash
# OPTIMIZED RTO Stress Test - Fresh Start
# Auto-scales workers, batched updates, minimal overhead

set -euo pipefail

# Auto-detect optimal workers (2x CPU cores)
NUM_WORKERS=$(( $(nproc) * 2 ))
RTO="/home/laptop/reversible_text_optimizer/src/rto"
PROJECTS_DIR="$HOME/Projects"
WORK_DIR="/tmp/rto_stress_$$"
STATS_FILE="/home/laptop/reversible_text_optimizer/testing/stress_stats.json"
QUEUE_FILE="$WORK_DIR/queue.txt"
LOCK_FILE="$WORK_DIR/queue.lock"
STATS_DISPLAY="/home/laptop/reversible_text_optimizer/testing/show_stats_v2.py"

mkdir -p "$WORK_DIR"
echo "[]" > "$STATS_FILE"

echo "Scanning $PROJECTS_DIR for files (1B-40MB)..."
find "$PROJECTS_DIR" -type f -size +0 -size -40M \( \
    -name "*.py" -o -name "*.js" -o -name "*.ts" -o -name "*.jsx" -o -name "*.tsx" -o \
    -name "*.c" -o -name "*.cpp" -o -name "*.h" -o -name "*.hpp" -o \
    -name "*.rs" -o -name "*.sh" -o -name "*.bash" -o \
    -name "*.md" -o -name "*.txt" -o -name "*.json" -o -name "*.yml" -o -name "*.yaml" \
\) 2>/dev/null > "$QUEUE_FILE" || true

TOTAL_FILES=$(wc -l < "$QUEUE_FILE")
echo "Found $TOTAL_FILES files"
echo "Starting $NUM_WORKERS workers..."

get_next_file() {
    (
        flock -x 200
        if [ -s "$QUEUE_FILE" ]; then
            head -n1 "$QUEUE_FILE"
            tail -n +2 "$QUEUE_FILE" > "$QUEUE_FILE.tmp" && mv "$QUEUE_FILE.tmp" "$QUEUE_FILE"
        fi
    ) 200>"$LOCK_FILE"
}

update_stats_batch() {
    local batch_file="$1"
    (
        flock -x 201
        python3 -c "
import json
stats = json.load(open('$STATS_FILE'))
with open('$batch_file') as f:
    batch = [json.loads(line) for line in f if line.strip()]
stats.extend(batch)
json.dump(stats, open('$STATS_FILE', 'w'))
" 2>/dev/null || true
    ) 201>"${STATS_FILE}.lock"
}

worker() {
    local worker_id=$1
    local work_dir="$WORK_DIR/w$worker_id"
    local batch_file="$work_dir/b.jsonl"
    mkdir -p "$work_dir"
    > "$batch_file"
    
    local batch_count=0
    local BATCH_SIZE=200
    
    while true; do
        local file=$(get_next_file)
        [ -z "$file" ] && break
        
        local ext="${file##*.}"
        case "$ext" in
            jsx|tsx) ext="js" ;; hpp) ext="cpp" ;; yaml) ext="yml" ;; bash) ext="sh" ;;
        esac
        
        local orig_size=$(stat -c%s "$file" 2>/dev/null || echo 0)
        [ "$orig_size" -gt 41943040 ] || [ "$orig_size" -eq 0 ] && continue
        
        local success=false comp_size=0 error_msg=""
        
        if timeout 20 "$RTO" --compress --ext "$ext" < "$file" > "$work_dir/c" 2>/dev/null; then
            comp_size=$(stat -c%s "$work_dir/c" 2>/dev/null || echo 0)
            if timeout 20 "$RTO" --expand < "$work_dir/c" > "$work_dir/r" 2>/dev/null; then
                diff -q "$file" "$work_dir/r" >/dev/null 2>&1 && success=true || error_msg="diff"
            else
                error_msg="expand"
            fi
        else
            error_msg="compress"
        fi
        
        local ratio=0
        [ "$orig_size" -gt 0 ] && ratio=$(python3 -c "print(round((1-$comp_size/$orig_size)*100,2))" 2>/dev/null || echo 0)
        
        local s="false"; [ "$success" = true ] && s="true"
        echo "{\"worker\":$worker_id,\"file\":\"$(basename "$file")\",\"ext\":\"$ext\",\"success\":$s,\"original_bytes\":$orig_size,\"compressed_bytes\":$comp_size,\"compression_ratio\":$ratio,\"compress_time_ms\":0,\"expand_time_ms\":0,\"error\":\"$error_msg\",\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}" >> "$batch_file"
        
        ((batch_count++))
        if [ $batch_count -ge $BATCH_SIZE ]; then
            update_stats_batch "$batch_file"
            > "$batch_file"
            batch_count=0
        fi
        
        rm -f "$work_dir/c" "$work_dir/r"
    done
    
    [ -s "$batch_file" ] && update_stats_batch "$batch_file"
    rm -rf "$work_dir"
}

# Launch workers
for i in $(seq 1 $NUM_WORKERS); do worker $i & done

# Monitor - wait for workers to actually finish
sleep 2
MONITOR_ACTIVE=true
while $MONITOR_ACTIVE; do
    python3 "$STATS_DISPLAY" "$STATS_FILE" $TOTAL_FILES 2>/dev/null || true
    sleep 1
    
    # Check if any workers still running
    jobs %1 >/dev/null 2>&1 || MONITOR_ACTIVE=false
done

# Wait for all workers
wait

# Final report
python3 << 'EOPY'
import sys
sys.path.insert(0, '/home/laptop/reversible_text_optimizer/testing')
from show_stats_v2 import save_final_report
save_final_report('/home/laptop/reversible_text_optimizer/testing/stress_stats.json', 650762, '/home/laptop/reversible_text_optimizer/testing/final_report.txt')
EOPY

rm -rf "$WORK_DIR"
echo "Complete!"
