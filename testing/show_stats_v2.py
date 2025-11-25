#!/usr/bin/env python3
"""
Enhanced live statistics dashboard - shows 100 extensions + throughput
"""

import json
import sys
import time
from collections import defaultdict
from datetime import datetime

START_TIME = time.time()
LAST_UPDATE = {'count': 0, 'time': time.time(), 'bytes': 0}

def format_bytes(bytes_val):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_val < 1024.0:
            return f"{bytes_val:.1f}{unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.1f}TB"

def get_size_bin(size):
    if size == 0: return "0B"
    elif size < 1024: return "1B-1KB"
    elif size < 10 * 1024: return "1-10KB"
    elif size < 100 * 1024: return "10-100KB"
    elif size < 500 * 1024: return "100-500KB"
    elif size < 1024 * 1024: return "500KB-1MB"
    elif size < 5 * 1024 * 1024: return "1-5MB"
    elif size < 10 * 1024 * 1024: return "5-10MB"
    elif size < 20 * 1024 * 1024: return "10-20MB"
    else: return "20-40MB"

def display_stats(stats_file, total_files=0):
    try:
        with open(stats_file) as f:
            stats = json.load(f)
    except:
        print("Waiting for stats data...")
        return
    
    if not stats:
        print("No data yet...")
        return
    
    # Overall stats
    total_processed = len(stats)
    successful = sum(1 for s in stats if s['success'])
    failed = total_processed - successful
    
    total_orig_bytes = sum(s['original_bytes'] for s in stats)
    total_comp_bytes = sum(s['compressed_bytes'] for s in stats)
    bytes_saved = total_orig_bytes - total_comp_bytes
    
    avg_ratio = (bytes_saved / total_orig_bytes * 100) if total_orig_bytes > 0 else 0
    progress_pct = (total_processed / total_files * 100) if total_files > 0 else 0
    
    # Throughput calculation
    elapsed = time.time() - START_TIME
    files_per_sec = total_processed / elapsed if elapsed > 0 else 0
    bytes_per_sec = total_orig_bytes / elapsed if elapsed > 0 else 0
    
    # Instantaneous throughput
    now = time.time()
    delta_time = now - LAST_UPDATE['time']
    delta_count = total_processed - LAST_UPDATE['count']
    delta_bytes = total_orig_bytes - LAST_UPDATE['bytes']
    inst_files_per_sec = delta_count / delta_time if delta_time > 0 else 0
    inst_bytes_per_sec = delta_bytes / delta_time if delta_time > 0 else 0
    
    LAST_UPDATE['count'] = total_processed
    LAST_UPDATE['time'] = now
    LAST_UPDATE['bytes'] = total_orig_bytes
    
    # Build extension/size matrix
    matrix = defaultdict(lambda: {'count': 0, 'orig': 0, 'comp': 0})
    ext_counts = defaultdict(int)
    
    for s in stats:
        if not s['success']:
            continue
        ext = s['ext']
        size_bin = get_size_bin(s['original_bytes'])
        
        key = (ext, size_bin)
        matrix[key]['count'] += 1
        matrix[key]['orig'] += s['original_bytes']
        matrix[key]['comp'] += s['compressed_bytes']
        ext_counts[ext] += 1
    
    # Get top 100 extensions
    top_exts = sorted(ext_counts.items(), key=lambda x: x[1], reverse=True)[:100]
    top_ext_names = [ext for ext, _ in top_exts]
    
    size_bins = ["0B", "1B-1KB", "1-10KB", "10-100KB", "100-500KB", "500KB-1MB", "1-5MB", "5-10MB", "10-20MB", "20-40MB"]
    
    # Latest file info
    latest = stats[-1] if stats else None
    
    # Clear screen
    print("\033[2J\033[H", end='')
    
    # Header
    print("=" * 200)
    print(f"RTO STRESS TEST - LIVE STATISTICS (100 EXTENSIONS)".center(200))
    print("=" * 200)
    print(f"Progress: {total_processed:,}/{total_files:,} files ({progress_pct:.1f}%) | " +
          f"Success: {successful:,} ({successful*100/total_processed:.1f}%) | " +
          f"Failed: {failed:,}")
    print(f"Data: {format_bytes(total_orig_bytes)} scanned | " +
          f"{format_bytes(total_comp_bytes)} compressed | " +
          f"{format_bytes(bytes_saved)} saved ({avg_ratio:.1f}%)")
    print(f"Speed: {files_per_sec:.1f} files/s avg | {inst_files_per_sec:.1f} files/s now | " +
          f"{format_bytes(bytes_per_sec)}/s avg | {format_bytes(inst_bytes_per_sec)}/s now")
    print(f"Elapsed: {int(elapsed//3600)}h {int((elapsed%3600)//60)}m {int(elapsed%60)}s | " +
          f"Updated: {datetime.now().strftime('%H:%M:%S')}")
    
    if latest:
        print(f"Latest: {latest['file']} ({format_bytes(latest['original_bytes'])} → {format_bytes(latest['compressed_bytes'])}, {latest['compression_ratio']:.1f}%)")
    
    print("=" * 200)
    print()
    
    # Table header - compact
    print(f"{'Ext':<6}", end='')
    for bin_name in size_bins:
        print(f"{bin_name:>11}", end='')
    print(f"{'TOTAL':>15}")
    print("-" * 200)
    
    # Table rows - top 100 extensions
    for ext in top_ext_names[:100]:
        print(f"{ext:<6}", end='')
        
        ext_total_count = 0
        ext_total_orig = 0
        ext_total_comp = 0
        
        for size_bin in size_bins:
            key = (ext, size_bin)
            if key in matrix:
                count = matrix[key]['count']
                orig = matrix[key]['orig']
                comp = matrix[key]['comp']
                ratio = ((orig - comp) / orig * 100) if orig > 0 else 0
                
                ext_total_count += count
                ext_total_orig += orig
                ext_total_comp += comp
                
                print(f"{count:>4} {ratio:>3.0f}% ", end='')
            else:
                print(f"{'':>10}", end='')
        
        # Row total
        total_ratio = ((ext_total_orig - ext_total_comp) / ext_total_orig * 100) if ext_total_orig > 0 else 0
        print(f"{ext_total_count:>6} {total_ratio:>4.0f}%")
    
    print("-" * 200)
    
    # Column totals
    print(f"{'TOTAL':<6}", end='')
    for size_bin in size_bins:
        bin_total_count = 0
        bin_total_orig = 0
        bin_total_comp = 0
        
        for ext in top_ext_names:
            key = (ext, size_bin)
            if key in matrix:
                bin_total_count += matrix[key]['count']
                bin_total_orig += matrix[key]['orig']
                bin_total_comp += matrix[key]['comp']
        
        if bin_total_count > 0:
            bin_ratio = ((bin_total_orig - bin_total_comp) / bin_total_orig * 100) if bin_total_orig > 0 else 0
            print(f"{bin_total_count:>4} {bin_ratio:>3.0f}% ", end='')
        else:
            print(f"{'':>10}", end='')
    
    print(f"{successful:>6} {avg_ratio:>4.0f}%")
    print("=" * 200)
    print()
    print(f"Showing top 100 of {len(ext_counts)} extensions | Format: [count] [%] | Press Ctrl+C to stop")

def save_final_report(stats_file, total_files, output_file):
    import io
    old_stdout = sys.stdout
    sys.stdout = buffer = io.StringIO()
    
    display_stats(stats_file, total_files)
    
    output = buffer.getvalue()
    sys.stdout = old_stdout
    
    with open(output_file, 'w') as f:
        f.write(output)
        f.write("\n\nFINAL REPORT\n")
        f.write(f"Generated: {datetime.now()}\n")
    
    print(output)
    print(f"\nReport saved to: {output_file}")

if __name__ == "__main__":
    stats_file = sys.argv[1] if len(sys.argv) > 1 else "stress_stats.json"
    total_files = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    
    display_stats(stats_file, total_files)
