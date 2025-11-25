#!/bin/bash
# Quick test wrapper - starts testing immediately while scanning continues

cd /home/laptop/reversible_text_optimizer

# Clean up
sudo rm -rf /tmp/rto_work 2>/dev/null
rm -f /tmp/rto_all_files.txt 2>/dev/null
mkdir -p /tmp/rto_work
chmod 777 /tmp/rto_work

# Compile if needed
if [ ! -f "./src/rto" ]; then
    echo "⚙️  Compiling..."
    g++ -O3 -std=c++17 -o ./src/rto ./src/reversible_text.cpp 2>/dev/null || {
        echo "❌ Compilation failed"
        exit 1
    }
fi

RTO="./src/rto"
STATS="./testing/stress_stats.json"
DISPLAY="./testing/show_stats_matrix.py"

echo "[]" > "$STATS"

echo "🚀 Quick Test Mode - Testing starts immediately!"
echo "Scanning ~/Projects for test files..."

# Quick scan of just Projects directory
find ~/Projects -type f -size +1 -size -40M \
    \( -name "*.txt" -o -name "*.md" -o -name "*.py" -o -name "*.js" -o \
       -name "*.ts" -o -name "*.c" -o -name "*.cpp" -o -name "*.h" -o \
       -name "*.java" -o -name "*.rs" -o -name "*.go" -o -name "*.sh" -o \
       -name "*.json" -o -name "*.xml" -o -name "*.yaml" -o -name "*.yml" -o \
       -name "*.toml" -o -name "*.ini" -o -name "*.conf" -o -name "*.html" -o \
       -name "*.css" -o -name "*.kt" -o -name "README" -o -name "LICENSE" \
    \) 2>/dev/null > /tmp/rto_all_files.txt &

SCAN_PID=$!

# Wait just 2 seconds to get some initial files
sleep 2

# Start processing whatever we have
echo "Starting workers with initial file set..."

# Worker function (same as main script)
worker() {
    local worker_id=$1
    local queue_file=$2
    local batch_file="/tmp/rto_work/batch_${worker_id}.jsonl"
    local work_dir="/tmp/rto_work/w${worker_id}_$$"
    
    mkdir -p "$work_dir" 2>/dev/null
    > "$batch_file"
    
    local count=0
    
    while IFS= read -r file; do
        [ ! -r "$file" ] 2>/dev/null && continue
        
        local basename="${file##*/}"
        local ext="${basename##*.}"
        
        case "$basename" in
            README|README.*) ext="README" ;;
            LICENSE|LICENSE.*) ext="LICENSE" ;;
            Makefile|Makefile.*) ext="Makefile" ;;
            CHANGELOG|CHANGELOG.*) ext="CHANGELOG" ;;
        esac
        
        if [ "$ext" = "$basename" ] || [[ "$ext" == *"/"* ]]; then
            case "$basename" in
                README|LICENSE|Makefile|CHANGELOG) ;;
                *) continue ;;
            esac
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
        
        [ -d "$work_dir" ] || mkdir -p "$work_dir" 2>/dev/null
        local cfile="$work_dir/c"
        local rfile="$work_dir/r"
        
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
    
    rm -rf "$work_dir"
    echo "Worker $worker_id: Processed $count files" >> /tmp/rto_work/progress.log
}

export -f worker
export RTO

# Launch workers (fewer for quick test)
WORKERS=12

while true; do
    CURRENT_COUNT=$(wc -l < /tmp/rto_all_files.txt 2>/dev/null || echo 0)
    
    if [ "$CURRENT_COUNT" -gt 100 ]; then
        echo "Got $CURRENT_COUNT files, splitting and starting workers..."
        
        split -n l/$WORKERS /tmp/rto_all_files.txt /tmp/rto_work/queue_
        
        worker_id=0
        for queue in /tmp/rto_work/queue_*; do
            worker $worker_id "$queue" &
            ((worker_id++))
        done
        
        break
    fi
    
    sleep 1
done

# Get final count once scan completes
wait $SCAN_PID
TOTAL=$(wc -l < /tmp/rto_all_files.txt)
echo "✓ Scan complete: $TOTAL files total"

# Live monitor
{
    sleep 3
    while pgrep -f "worker" >/dev/null 2>&1; do
        cat /tmp/rto_work/batch_*.jsonl 2>/dev/null | python3 -c "
import json, sys
r = [json.loads(l) for l in sys.stdin if l.strip()]
json.dump(r, open('$STATS', 'w'))
" 2>/dev/null
        
        clear
        python3 "$DISPLAY" "$STATS" $TOTAL 2>/dev/null || true
        
        if [ -f /tmp/rto_work/progress.log ]; then
            echo ""
            echo "Worker Progress:"
            tail -$WORKERS /tmp/rto_work/progress.log 2>/dev/null | sort
        fi
        
        sleep 2
    done
} &
MONITOR_PID=$!

# Wait for workers
wait

kill $MONITOR_PID 2>/dev/null || true

echo ""
echo "✓ Test complete!"

# Clean up
rm -rf /tmp/rto_work /tmp/rto_all_files.txt
