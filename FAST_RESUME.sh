#!/bin/bash
# FAST RESUME with batched stats and enhanced display

WORK_DIR="/tmp/rto_stress_575792"
STATS_FILE="/home/laptop/reversible_text_optimizer/testing/stress_stats.json"  
RTO="/home/laptop/reversible_text_optimizer/src/rto"
QUEUE_FILE="$WORK_DIR/queue.txt"
LOCK_FILE="$WORK_DIR/queue.lock"
STATS_DISPLAY="/home/laptop/reversible_text_optimizer/testing/show_stats_v2.py"

[ ! -f "$QUEUE_FILE" ] && echo "Error: Queue not found!" && exit 1

TOTAL_FILES=$(wc -l < "$QUEUE_FILE")
echo "Resuming with $TOTAL_FILES files remaining..."

get_next_file() {
    (
        flock -x 200
        if [ -s "$QUEUE_FILE" ]; then
            head -n1 "$QUEUE_FILE"
            tail -n +2 "$QUEUE_FILE" > "$QUEUE_FILE.tmp" && mv "$QUEUE_FILE.tmp" "$QUEUE_FILE"
        fi
    ) 200>"$LOCK_FILE"
}

# BATCHED stats update
update_stats_batch() {
    local batch_file="$1"
    (
        flock -x 201
        python3 << EOPY 2>/dev/null || true
import json
stats = json.load(open('$STATS_FILE'))
with open('$batch_file') as f:
    batch = [json.loads(line) for line in f if line.strip()]
stats.extend(batch)
with open('$STATS_FILE', 'w') as f:
    json.dump(stats, f, indent=2)
EOPY
    ) 201>"${STATS_FILE}.lock"
}

worker() {
    local worker_id=$1
    local work_dir="$WORK_DIR/worker_$worker_id"
    local batch_file="$work_dir/batch.jsonl"
    mkdir -p "$work_dir"
    
    local batch_count=0
    local BATCH_SIZE=100  # Update every 100 files
    
    > "$batch_file"  # Clear batch file
    
    while true; do
        local file=$(get_next_file)
        [ -z "$file" ] && break
        
        local ext="${file##*.}"
        case "$ext" in
            jsx|tsx) ext="js" ;; hpp) ext="cpp" ;; yaml) ext="yml" ;; bash) ext="sh" ;;
        esac
        
        local filename=$(basename "$file")
        local orig_size=$(stat -c%s "$file" 2>/dev/null || echo 0)
        
        [ "$orig_size" -gt 41943040 ] || [ "$orig_size" -eq 0 ] && continue
        
        local success=false comp_size=0 compress_time=0 expand_time=0 error_msg=""
        
        local start_ms=$(date +%s%3N)
        if timeout 30 "$RTO" --compress --ext "$ext" < "$file" > "$work_dir/c.rto" 2>/dev/null; then
            compress_time=$(($(date +%s%3N) - start_ms))
            comp_size=$(stat -c%s "$work_dir/c.rto" 2>/dev/null || echo 0)
            
            start_ms=$(date +%s%3N)
            if timeout 30 "$RTO" --expand < "$work_dir/c.rto" > "$work_dir/r" 2>/dev/null; then
                expand_time=$(($(date +%s%3N) - start_ms))
                diff -q "$file" "$work_dir/r" >/dev/null 2>&1 && success=true || error_msg="diff_failed"
            else
                error_msg="expand_failed"
            fi
        else
            error_msg="compress_failed"
        fi
        
        local ratio=0
        [ "$orig_size" -gt 0 ] && ratio=$(python3 -c "print(round((1 - $comp_size / $orig_size) * 100, 2))" 2>/dev/null || echo 0)
        
        local success_str="false"; [ "$success" = true ] && success_str="true"
        
        # Append to batch file (JSONL format)
        echo "{\"worker\":$worker_id,\"file\":\"$filename\",\"ext\":\"$ext\",\"success\":$success_str,\"original_bytes\":$orig_size,\"compressed_bytes\":$comp_size,\"compression_ratio\":$ratio,\"compress_time_ms\":$compress_time,\"expand_time_ms\":$expand_time,\"error\":\"$error_msg\",\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}" >> "$batch_file"
        
        ((batch_count++))
        
        # Flush batch
        if [ $batch_count -ge $BATCH_SIZE ]; then
            update_stats_batch "$batch_file"
            > "$batch_file"
            batch_count=0
        fi
        
        rm -f "$work_dir/c.rto" "$work_dir/r"
    done
    
    # Final batch
    [ -s "$batch_file" ] && update_stats_batch "$batch_file"
    rm -f "$batch_file"
    rmdir "$work_dir" 2>/dev/null || true
}

# Start workers
echo "Starting 12 workers with batch updates..."
for i in {1..12}; do worker $i & done

# Monitor with new display
echo "Live stats updating..."
sleep 3
while jobs %1 >/dev/null 2>&1; do
    python3 "$STATS_DISPLAY" "$STATS_FILE" 650762 2>/dev/null || true
    sleep 2  # Update every 2 seconds
done

wait
echo ""
echo "Complete!"

# Final report
python3 << 'EOPY'
import sys
sys.path.insert(0, '/home/laptop/reversible_text_optimizer/testing')
from show_stats_v2 import save_final_report
save_final_report('/home/laptop/reversible_text_optimizer/testing/stress_stats.json', 650762, '/home/laptop/reversible_text_optimizer/testing/final_report.txt')
EOPY
