# RTO Stress Test Monitoring

## Test is Running!

**PID**: Check with `ps aux | grep parallel_stress_test | grep -v grep`

## Monitor Commands

### Watch live progress output:
```bash
tail -f /tmp/rto_live.log
```

### Watch worker activity (updates every 10sec):
```bash
tail -f /home/laptop/reversible_text_optimizer/testing/stress_test.log
```

### Check current statistics:
```bash
cd /home/laptop/reversible_text_optimizer/testing
python3 << 'EOF'
import json
try:
    with open("stress_stats.json") as f:
        stats = json.load(f)
    
    if not stats:
        print("No results yet - still scanning or starting up")
    else:
        total = len(stats)
        success = sum(1 for s in stats if s['success'])
        print(f"Files processed: {total}")
        print(f"Successful: {success} ({success*100/total:.1f}%)")
        print(f"Failed: {total-success}")
        
        total_orig = sum(s['original_bytes'] for s in stats)
        total_comp = sum(s['compressed_bytes'] for s in stats)
        print(f"\nTotal original: {total_orig/1024/1024:.1f} MB")
        print(f"Total compressed: {total_comp/1024/1024:.1f} MB")
        print(f"Avg compression: {(1-total_comp/total_orig)*100:.2f}%")
except FileNotFoundError:
    print("Stats file not created yet")
except Exception as e:
    print(f"Error: {e}")
EOF
```

### Quick stats check:
```bash
wc -l testing/stress_test.log
ls -lh testing/stress_stats.json
```

### Stop the test:
```bash
pkill -f parallel_stress_test
```

## What's Happening

1. **Scanning phase**: Finding all files (may take 1-2 minutes for large dirs)
2. **Processing phase**: 12 workers compress/decompress files in parallel
3. **Completion**: Final statistics displayed

## Expected Runtime

- **~674,600 files** found in ~/Projects
- **12 workers** in parallel
- **~3.3 MB/s** throughput per worker
- **Estimated time**: Several hours (depends on file sizes)

The test will run until all files are processed or you stop it.
