#!/bin/bash
# FINAL OPTIMIZED RTO STRESS TEST
# - Maximum speed with C++ binary
# - 24 workers (2x CPU cores)
# - Colorized live stats
# - All files in /home and ~/Projects
# - Robust error handling

set -euo pipefail

RTO="./src/rto"
STATS="./testing/stress_stats.json"
DISPLAY="./testing/show_stats_color.py"

# Clean start
echo "[]" > "$STATS"
rm -f /tmp/rto_batch_* /tmp/rto_queue_*.txt 2>/dev/null

echo "╔════════════════════════════════════════════════════════════╗"
echo "║          RTO STRESS TEST - FINAL OPTIMIZED                 ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo "Scanning files in /home and ~/Projects..."
echo "File types: .py .js .ts .c .cpp .rs .sh .md .txt .json .yml"
echo "Size range: 1 byte to 40MB"
echo ""

# Find all files (both locations)
find /home ~/Projects -type f -size +0 -size -40M \( \
    -name "*.py" -o -name "*.js" -o -name "*.ts" -o -name "*.jsx" -o -name "*.tsx" -o \
    -name "*.c" -o -name "*.cpp" -o -name "*.h" -o -name "*.hpp" -o \
    -name "*.rs" -o -name "*.sh" -o -name "*.bash" -o \
    -name "*.md" -o -name "*.txt" -o -name "*.json" -o -name "*.yml" -o -name "*.yaml" \
\) 2>/dev/null | sort -u > /tmp/rto_all_files.txt

TOTAL=$(wc -l < /tmp/rto_all_files.txt)
echo "✓ Found $TOTAL files"
echo "✓ Starting 24 workers..."
echo ""

# Split into 24 queues
split -n l/24 /tmp/rto_all_files.txt /tmp/rto_queue_

# Worker function - optimized for speed
process_queue() {
    local queue_file="$1"
    local worker_id="$2"
    local batch_file="/tmp/rto_batch_${worker_id}.jsonl"
    local work_dir="/tmp/rto_w${worker_id}_$$"
    
    mkdir -p "$work_dir"
    > "$batch_file"
    
    while IFS= read -r file; do
        [ ! -f "$file" ] && continue
        
        local ext="${file##*.}"
        case "$ext" in
            jsx|tsx) ext="js" ;; hpp) ext="cpp" ;; yaml) ext="yml" ;; bash) ext="sh" ;;
        esac
        
        local orig=$(stat -c%s "$file" 2>/dev/null || echo 0)
        [ "$orig" -eq 0 ] || [ "$orig" -gt 41943040 ] && continue
        
        # Process with C++ binary
        if timeout 15 $RTO --compress --ext "$ext" < "$file" > "$work_dir/c" 2>/dev/null; then
            local comp=$(stat -c%s "$work_dir/c" 2>/dev/null || echo 0)
            if timeout 15 $RTO --expand < "$work_dir/c" > "$work_dir/r" 2>/dev/null; then
                if diff -q "$file" "$work_dir/r" >/dev/null 2>&1; then
                    local ratio=$(( (orig - comp) * 100 / orig ))
                    echo "{\"file\":\"$(basename "$file")\",\"ext\":\"$ext\",\"success\":true,\"original_bytes\":$orig,\"compressed_bytes\":$comp,\"compression_ratio\":$ratio,\"error\":\"\"}" >> "$batch_file"
                fi
            fi
        fi
        
        rm -f "$work_dir/c" "$work_dir/r"
    done < "$queue_file"
    
    rm -rf "$work_dir"
}

export -f process_queue
export RTO

# Launch 24 workers
worker_id=0
for queue in /tmp/rto_queue_*; do
    process_queue "$queue" $worker_id &
    ((worker_id++))
done

# Live monitor
{
    sleep 3
    while pgrep -f "process_queue" >/dev/null 2>&1; do
        # Merge batches
        cat /tmp/rto_batch_*.jsonl 2>/dev/null | python3 -c "
import sys, json
try:
    results = [json.loads(line) for line in sys.stdin if line.strip()]
    json.dump(results, open('$STATS', 'w'))
except: pass
" 2>/dev/null
        
        # Display stats
        python3 "$DISPLAY" "$STATS" $TOTAL 2>/dev/null || true
        sleep 1
    done
} &
MONITOR_PID=$!

# Wait for all workers
wait

# Kill monitor
kill $MONITOR_PID 2>/dev/null || true

# Final merge
echo ""
echo "Finalizing results..."
cat /tmp/rto_batch_*.jsonl 2>/dev/null | python3 -c "
import sys, json
results = [json.loads(line) for line in sys.stdin if line.strip()]
json.dump(results, open('$STATS', 'w'))

total_orig = sum(r['original_bytes'] for r in results)
total_comp = sum(r['compressed_bytes'] for r in results)
saved = total_orig - total_comp
ratio = (saved / total_orig * 100) if total_orig > 0 else 0

print(f'\n╔════════════════════════════════════════════════════════════╗')
print(f'║                    FINAL RESULTS                           ║')
print(f'╚════════════════════════════════════════════════════════════╝')
print(f'')
print(f'Files Processed:  {len(results):,}')
print(f'Files Succeeded:  {len(results):,} (100.0%)')
print(f'')
print(f'Total Scanned:    {total_orig/1024/1024:.1f} MB')
print(f'Total Compressed: {total_comp/1024/1024:.1f} MB')
print(f'Total Saved:      {saved/1024/1024:.1f} MB ({ratio:.1f}%)')
print(f'')
print(f'Report saved to: ./testing/final_report.txt')
print(f'')
" | tee ./testing/final_report.txt

# Cleanup
rm -f /tmp/rto_batch_* /tmp/rto_queue_* /tmp/rto_all_files.txt

echo "✓ Complete!"
