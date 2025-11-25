#!/bin/bash
# Resume stress test from existing work dir

WORK_DIR="/tmp/rto_stress_575792"
STATS_FILE="/home/laptop/reversible_text_optimizer/testing/stress_stats.json"  
LOG_FILE="/home/laptop/reversible_text_optimizer/testing/stress_test.log"
RTO="/home/laptop/reversible_text_optimizer/src/rto"
QUEUE_FILE="$WORK_DIR/queue.txt"
LOCK_FILE="$WORK_DIR/queue.lock"

if [ ! -f "$QUEUE_FILE" ]; then
    echo "Error: Queue file not found!"
    exit 1
fi

TOTAL_FILES=$(wc -l < "$QUEUE_FILE")
echo "Resuming with $TOTAL_FILES files remaining..."

# Copy original functions
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

update_stats() {
    local result="$1"
    (
        flock -x 201
        echo "$result" | python3 -c "
import sys, json
stats = json.load(open('$STATS_FILE'))
new_result = json.load(sys.stdin)
stats.append(new_result)
json.dump(stats, open('$STATS_FILE', 'w'), indent=2)
" 2>/dev/null || true
    ) 201>"${STATS_FILE}.lock"
}

worker() {
    local worker_id=$1
    local work_dir="$WORK_DIR/worker_$worker_id"
    mkdir -p "$work_dir"
    
    while true; do
        local file=$(get_next_file)
        [ -z "$file" ] && break
        
        local ext="${file##*.}"
        case "$ext" in
            jsx|tsx) ext="js" ;;
            hpp) ext="cpp" ;;
            yaml) ext="yml" ;;
            bash) ext="sh" ;;
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
        
        local ratio=$(python3 -c "print(round((1 - $comp_size / $orig_size) * 100, 2))" 2>/dev/null || echo 0)
        local success_str="false"; [ "$success" = true ] && success_str="true"
        
        local result="{\"worker\":$worker_id,\"file\":\"$filename\",\"ext\":\"$ext\",\"success\":$success_str,\"original_bytes\":$orig_size,\"compressed_bytes\":$comp_size,\"compression_ratio\":$ratio,\"compress_time_ms\":$compress_time,\"expand_time_ms\":$expand_time,\"error\":\"$error_msg\",\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
        
        update_stats "$result"
        rm -f "$work_dir/c.rto" "$work_dir/r"
    done
    rmdir "$work_dir" 2>/dev/null || true
}

# Start 12 workers
for i in {1..12}; do worker $i & done

# Monitor
while jobs %1 >/dev/null 2>&1; do
    python3 /home/laptop/reversible_text_optimizer/testing/show_stats.py "$STATS_FILE" $TOTAL_FILES 2>/dev/null || true
    sleep 5
done

wait
echo "Complete!"
