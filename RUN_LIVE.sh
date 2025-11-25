#!/bin/bash
# LIVE UPDATING VERSION

cd /home/laptop/reversible_text_optimizer

RTO="./src/rto"
STATS="./testing/stress_stats.json"
DISPLAY="./testing/show_stats_matrix.py"

echo "[]" > "$STATS"

clear
echo "╔════════════════════════════════════════════════════════════╗"
echo "║          RTO STRESS TEST - LIVE VERSION                   ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo "Finding files in /home..."

find /home -type f -size +1k -size -40M \( \
    -name "*.py" -o -name "*.js" -o -name "*.md" -o -name "*.txt" -o \
    -name "*.c" -o -name "*.cpp" -o -name "*.sh" -o -name "*.json" \
\) 2>/dev/null > /tmp/rto_files.txt &

FIND_PID=$!

while kill -0 $FIND_PID 2>/dev/null; do
    COUNT=$(wc -l < /tmp/rto_files.txt 2>/dev/null || echo 0)
    echo -ne "\rScanning... found $COUNT files"
    sleep 1
done
echo ""

TOTAL=$(wc -l < /tmp/rto_files.txt)
echo "✓ Found $TOTAL files"
echo "✓ Starting test..."
echo ""

process_files() {
    local count=0
    
    while IFS= read -r file; do
        [ ! -r "$file" ] && continue
        
        local ext="${file##*.}"
        local orig=$(stat -c%s "$file" 2>/dev/null || echo 0)
        [ "$orig" -eq 0 ] && continue
        
        if $RTO --compress --ext "$ext" < "$file" 2>/dev/null | $RTO --expand 2>/dev/null | diff -q "$file" - >/dev/null 2>&1; then
            local comp=$($RTO --compress --ext "$ext" < "$file" 2>/dev/null | wc -c)
            local ratio=$(( (orig - comp) * 100 / orig ))
            echo "{\"file\":\"$(basename "$file")\",\"ext\":\"$ext\",\"success\":true,\"original_bytes\":$orig,\"compressed_bytes\":$comp,\"compression_ratio\":$ratio}" >> /tmp/rto_batch.jsonl
            
            ((count++))
            
            if [ $((count % 50)) -eq 0 ]; then
                cat /tmp/rto_batch.jsonl | python3 -c "
import json, sys
r = [json.loads(l) for l in sys.stdin if l.strip()]
json.dump(r, open('$STATS', 'w'))
" 2>/dev/null
                
                clear
                python3 "$DISPLAY" "$STATS" $TOTAL 2>/dev/null || echo "Processed $count files..."
            fi
        fi
    done < /tmp/rto_files.txt
}

process_files

cat /tmp/rto_batch.jsonl | python3 -c "
import json, sys
r = [json.loads(l) for l in sys.stdin if l.strip()]
json.dump(r, open('$STATS', 'w'))

total_orig = sum(x['original_bytes'] for x in r)
total_comp = sum(x['compressed_bytes'] for x in r)
saved = total_orig - total_comp

print('\n╔════════════════════════════════════════════════════════════╗')
print('║                    FINAL RESULTS                           ║')
print('╚════════════════════════════════════════════════════════════╝')
print(f'Files: {len(r):,}')
print(f'Scanned: {total_orig/1024/1024:.1f} MB')
print(f'Saved: {saved/1024/1024:.1f} MB ({saved*100/total_orig:.1f}%)')
"

rm -f /tmp/rto_*
echo "✓ Done!"
