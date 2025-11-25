#!/usr/bin/env python3
"""
Live statistics dashboard for RTO stress test
Reads JSON stats and displays formatted table
"""

import json
import sys
from collections import defaultdict
from datetime import datetime

def format_bytes(bytes):
    """Format bytes to human readable"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes < 1024.0:
            return f"{bytes:.1f}{unit}"
        bytes /= 1024.0
    return f"{bytes:.1f}TB"

def get_size_bin(size):
    """Categorize file size into bins"""
    if size == 0:
        return "0B"
    elif size < 1024:
        return "1B-1KB"
    elif size < 10 * 1024:
        return "1-10KB"
    elif size < 100 * 1024:
        return "10-100KB"
    elif size < 500 * 1024:
        return "100-500KB"
    elif size < 1024 * 1024:
        return "500KB-1MB"
    elif size < 5 * 1024 * 1024:
        return "1-5MB"
    elif size < 10 * 1024 * 1024:
        return "5-10MB"
    elif size < 20 * 1024 * 1024:
        return "10-20MB"
    else:
        return "20-40MB"

def display_stats(stats_file, total_files=0):
    """Display live statistics table"""
    try:
        with open(stats_file) as f:
            stats = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print("Waiting for stats data...")
        return
    
    if not stats:
        print("No data yet...")
        return
    
    # Calculate overall stats
    total_processed = len(stats)
    successful = sum(1 for s in stats if s['success'])
    failed = total_processed - successful
    
    total_orig_bytes = sum(s['original_bytes'] for s in stats)
    total_comp_bytes = sum(s['compressed_bytes'] for s in stats)
    bytes_saved = total_orig_bytes - total_comp_bytes
    
    avg_ratio = (bytes_saved / total_orig_bytes * 100) if total_orig_bytes > 0 else 0
    progress_pct = (total_processed / total_files * 100) if total_files > 0 else 0
    
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
    
    # Get top 20 extensions
    top_exts = sorted(ext_counts.items(), key=lambda x: x[1], reverse=True)[:20]
    top_ext_names = [ext for ext, _ in top_exts]
    
    # Size bins in order
    size_bins = ["0B", "1B-1KB", "1-10KB", "10-100KB", "100-500KB", "500KB-1MB", "1-5MB", "5-10MB", "10-20MB", "20-40MB"]
    
    # Clear screen and display
    print("\033[2J\033[H", end='')  # Clear screen
    
    # Header
    print("=" * 180)
    print(f"RTO STRESS TEST - LIVE STATISTICS".center(180))
    print("=" * 180)
    print(f"Progress: {total_processed:,}/{total_files:,} files ({progress_pct:.1f}%) | " +
          f"Success: {successful:,} ({successful*100/total_processed:.1f}%) | " +
          f"Failed: {failed:,}")
    print(f"Data Scanned: {format_bytes(total_orig_bytes)} | " +
          f"Compressed: {format_bytes(total_comp_bytes)} | " +
          f"Saved: {format_bytes(bytes_saved)} ({avg_ratio:.1f}%)")
    print(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 180)
    print()
    
    # Table header
    print(f"{'Extension':<12}", end='')
    for bin_name in size_bins:
        print(f"{bin_name:>13}", end='')
    print(f"{'TOTAL':>17}")
    print("-" * 180)
    
    # Table rows
    for ext in top_ext_names:
        print(f"{ext:<12}", end='')
        
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
                
                print(f"{count:>4} {ratio:>4.1f}% ", end='')
            else:
                print(f"{'':>11}", end='')
        
        # Row total
        total_ratio = ((ext_total_orig - ext_total_comp) / ext_total_orig * 100) if ext_total_orig > 0 else 0
        print(f"{ext_total_count:>5} {total_ratio:>5.1f}%")
    
    print("-" * 180)
    
    # Column totals
    print(f"{'TOTAL':<12}", end='')
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
            print(f"{bin_total_count:>4} {bin_ratio:>4.1f}% ", end='')
        else:
            print(f"{'':>11}", end='')
    
    print(f"{successful:>5} {avg_ratio:>5.1f}%")
    print("=" * 180)
    print()
    print("Format: [count] [compression%] | Press Ctrl+C to stop")

def save_final_report(stats_file, total_files, output_file):
    """Save final report to file"""
    import io
    
    # Redirect output to string
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
