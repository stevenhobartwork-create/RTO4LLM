#!/bin/bash
#
# RTO Parallel Stress Test
# Runs 12 concurrent workers testing compression/decompression on ~/Projects
# Collects statistics until all files are processed
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

# Initialize
mkdir -p "$WORK_DIR"
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

TOTAL_FILES=$(wc -l < "$QUEUE_FILE")
echo "Found $TOTAL_FILES files to test"
echo "Starting $NUM_WORKERS workers..."

# Statistics tracking
declare -A STATS
STATS[total_files]=0
STATS[success]=0
STATS[failures]=0
STATS[total_original_bytes]=0
STATS[total_compressed_bytes]=0
STATS[total_compress_time_ms]=0
STATS[total_expand_time_ms]=0

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

# Function to update statistics
update_stats() {
    local result="$1"
    (
        flock -x 201
        # Read current stats
        local current=$(cat "$STATS_FILE")
        # Append new result (pass JSON as stdin)
        echo "$result" | python3 -c "
import sys, json
stats = json.load(open('$STATS_FILE'))
new_result = json.load(sys.stdin)
stats.append(new_result)
json.dump(stats, sys.stdout, indent=2)
" > "$STATS_FILE.tmp"
        mv "$STATS_FILE.tmp" "$STATS_FILE"
    ) 201>"${STATS_FILE}.lock"
}

# Worker function
worker() {
    local worker_id=$1
    local work_dir="$WORK_DIR/worker_$worker_id"
    mkdir -p "$work_dir"
    
    while true; do
        # Get next file
        local file=$(get_next_file)
        if [ -z "$file" ]; then
            echo "Worker $worker_id: No more files, exiting"
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
        
        # Test the file
        local filename=$(basename "$file")
        local orig_size=$(stat -f%z "$file" 2>/dev/null || stat -c%s "$file" 2>/dev/null || echo 0)
        
        # Skip if file too large (>40MB) or empty
        if [ "$orig_size" -gt 41943040 ] || [ "$orig_size" -eq 0 ]; then
            echo "Worker $worker_id: Skipping $filename (size: $orig_size)" >> "$LOG_FILE"
            continue
        fi
        
        local success=false
        local comp_size=0
        local compress_time=0
        local expand_time=0
        local error_msg=""
        
        # Compress
        local start_ms=$(date +%s%3N)
        if cat "$file" | timeout 30 "$RTO" --compress --ext "$ext" > "$work_dir/compressed.rto" 2>/dev/null; then
            compress_time=$(($(date +%s%3N) - start_ms))
            comp_size=$(stat -f%z "$work_dir/compressed.rto" 2>/dev/null || stat -c%s "$work_dir/compressed.rto" 2>/dev/null || echo 0)
            
            # Expand
            start_ms=$(date +%s%3N)
            if cat "$work_dir/compressed.rto" | timeout 30 "$RTO" --expand > "$work_dir/restored" 2>/dev/null; then
                expand_time=$(($(date +%s%3N) - start_ms))
                
                # Verify
                if diff -q "$file" "$work_dir/restored" >/dev/null 2>&1; then
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
        
        # Calculate compression ratio
        local ratio=0
        if [ "$orig_size" -gt 0 ]; then
            ratio=$(python3 -c "print(round((1 - $comp_size / $orig_size) * 100, 2))" 2>/dev/null || echo 0)
        fi
        
        # Build JSON result (convert bash bool to Python bool)
        local success_str="false"
        if [ "$success" = true ]; then
            success_str="true"
        fi
        
        local result=$(cat <<EOF
{
  "worker": $worker_id,
  "file": "$filename",
  "ext": "$ext",
  "success": $success_str,
  "original_bytes": $orig_size,
  "compressed_bytes": $comp_size,
  "compression_ratio": $ratio,
  "compress_time_ms": $compress_time,
  "expand_time_ms": $expand_time,
  "error": "$error_msg",
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
)
        
        # Update statistics
        update_stats "$result"
        
        # Log
        if [ "$success" = true ]; then
            echo "Worker $worker_id: ✓ $filename ($orig_size → $comp_size bytes, ${ratio}%)" | tee -a "$LOG_FILE"
        else
            echo "Worker $worker_id: ✗ $filename - $error_msg" | tee -a "$LOG_FILE"
        fi
        
        # Cleanup
        rm -f "$work_dir/compressed.rto" "$work_dir/restored"
    done
    
    rmdir "$work_dir" 2>/dev/null || true
}

# Start workers in background
echo "Launching workers..."
for i in $(seq 1 $NUM_WORKERS); do
    worker $i &
done

# Monitor progress
echo ""
echo "Workers running in background (PIDs: $(jobs -p | tr '\n' ' '))"
echo "Log file: $LOG_FILE"
echo "Stats file: $STATS_FILE"
echo ""
echo "Press Ctrl+C to view current stats, or wait for completion..."
echo ""

# Progress monitor (runs in background)
monitor_progress() {
    sleep 5  # Initial delay
    while jobs %1 >/dev/null 2>&1; do
        # Display live stats table
        python3 "$STATS_DISPLAY" "$STATS_FILE" "$TOTAL_FILES" 2>/dev/null || true
        sleep 5
    done
}

STATS_DISPLAY="/home/laptop/reversible_text_optimizer/testing/show_stats.py"

# Start progress monitor in background
monitor_progress &
MONITOR_PID=$!

# Handle Ctrl+C to show stats
trap 'show_stats; exit' INT

show_stats() {
    echo ""
    echo "=========================================="
    echo "          CURRENT STATISTICS"
    echo "=========================================="
    python3 <<'EOPY'
import json
try:
    with open("/home/laptop/reversible_text_optimizer/testing/stress_stats.json") as f:
        stats = json.load(f)
    
    if not stats:
        print("No results yet")
        exit(0)
    
    total = len(stats)
    success = sum(1 for s in stats if s['success'])
    failed = total - success
    
    total_orig = sum(s['original_bytes'] for s in stats)
    total_comp = sum(s['compressed_bytes'] for s in stats)
    avg_ratio = sum(s['compression_ratio'] for s in stats) / total if total > 0 else 0
    
    total_compress_time = sum(s['compress_time_ms'] for s in stats)
    total_expand_time = sum(s['expand_time_ms'] for s in stats)
    
    print(f"Files processed:     {total}")
    print(f"Successful:          {success} ({success*100/total:.1f}%)")
    print(f"Failed:              {failed}")
    print(f"")
    print(f"Total original:      {total_orig:,} bytes ({total_orig/1024/1024:.1f} MB)")
    print(f"Total compressed:    {total_comp:,} bytes ({total_comp/1024/1024:.1f} MB)")
    print(f"Bytes saved:         {total_orig - total_comp:,} bytes")
    print(f"Avg compression:     {avg_ratio:.2f}%")
    print(f"")
    print(f"Total compress time: {total_compress_time:,} ms ({total_compress_time/1000:.1f}s)")
    print(f"Total expand time:   {total_expand_time:,} ms ({total_expand_time/1000:.1f}s)")
    print(f"Avg compress speed:  {total_orig/total_compress_time*1000/1024/1024:.2f} MB/s" if total_compress_time > 0 else "")
    print(f"Avg expand speed:    {total_orig/total_expand_time*1000/1024/1024:.2f} MB/s" if total_expand_time > 0 else "")
    
    # By extension
    by_ext = {}
    for s in stats:
        ext = s['ext']
        if ext not in by_ext:
            by_ext[ext] = {'count': 0, 'success': 0, 'ratios': []}
        by_ext[ext]['count'] += 1
        if s['success']:
            by_ext[ext]['success'] += 1
            by_ext[ext]['ratios'].append(s['compression_ratio'])
    
    print(f"\nBy file type:")
    print(f"{'Ext':<8} {'Files':<8} {'Success':<10} {'Avg Ratio'}")
    print("-" * 50)
    for ext, data in sorted(by_ext.items()):
        avg = sum(data['ratios'])/len(data['ratios']) if data['ratios'] else 0
        print(f"{ext:<8} {data['count']:<8} {data['success']:<10} {avg:>6.1f}%")
    
    # Errors
    errors = [s['error'] for s in stats if s['error']]
    if errors:
        from collections import Counter
        print(f"\nErrors:")
        for err, count in Counter(errors).items():
            print(f"  {err}: {count}")

except Exception as e:
    print(f"Error reading stats: {e}")
EOPY
}

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

echo ""
echo "Full results saved to: $STATS_FILE"
echo "Log saved to: $LOG_FILE"
echo ""
echo "Done!"
