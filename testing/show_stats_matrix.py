#!/usr/bin/env python3
"""
Matrix view: File Extensions × Size Buckets
Shows count and compression ratio for each cell
"""

import json
import sys
import time
from collections import defaultdict
from datetime import datetime

# ANSI colors
RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
MAGENTA = '\033[95m'
CYAN = '\033[96m'
WHITE = '\033[97m'
BOLD = '\033[1m'
RESET = '\033[0m'

START_TIME = time.time()
LAST_UPDATE = {'count': 0, 'time': time.time(), 'bytes': 0}

def format_bytes(b):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if b < 1024.0:
            return f"{b:.1f}{unit}"
        b /= 1024.0
    return f"{b:.1f}PB"

def display_stats(stats_file, total_files=0):
    try:
        with open(stats_file) as f:
            stats = json.load(f)
    except:
        print(f"{YELLOW}Waiting for stats data...{RESET}")
        return
    
    if not stats:
        print(f"{YELLOW}No data yet...{RESET}")
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
    
    # Throughput
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
    
    # Build MATRIX: extension × size_bucket
    matrix = defaultdict(lambda: {'count': 0, 'orig': 0, 'comp': 0})
    ext_totals = defaultdict(lambda: {'count': 0, 'orig': 0, 'comp': 0})
    bucket_totals = defaultdict(lambda: {'count': 0, 'orig': 0, 'comp': 0})
    
    size_buckets = ["0-1KB", "1-10KB", "10-100KB", "100KB-1MB", "1-10MB", "10-40MB"]
    
    for s in stats:
        if not s['success']:
            continue
        ext = s['ext']
        bucket = s.get('size_bucket', 'unknown')
        
        key = (ext, bucket)
        matrix[key]['count'] += 1
        matrix[key]['orig'] += s['original_bytes']
        matrix[key]['comp'] += s['compressed_bytes']
        
        ext_totals[ext]['count'] += 1
        ext_totals[ext]['orig'] += s['original_bytes']
        ext_totals[ext]['comp'] += s['compressed_bytes']
        
        bucket_totals[bucket]['count'] += 1
        bucket_totals[bucket]['orig'] += s['original_bytes']
        bucket_totals[bucket]['comp'] += s['compressed_bytes']
    
    # Top extensions by count - now showing 200!
    top_exts = sorted(ext_totals.items(), key=lambda x: x[1]['count'], reverse=True)[:200]
    top_ext_names = [ext for ext, _ in top_exts]
    
    # Initialize all matrix cells to zero (prevents empty bin issues)
    for ext in top_ext_names:
        for bucket in size_buckets:
            key = (ext, bucket)
            if key not in matrix:
                matrix[key] = {'count': 0, 'orig': 0, 'comp': 0}
    
    # Initialize bucket totals to zero
    for bucket in size_buckets:
        if bucket not in bucket_totals:
            bucket_totals[bucket] = {'count': 0, 'orig': 0, 'comp': 0}
    
    latest = stats[-1] if stats else None
    
    # Clear screen
    print("\033[2J\033[H", end='')
    
    # Header
    print(f"{BOLD}{CYAN}{'=' * 180}{RESET}")
    print(f"{BOLD}{MAGENTA}RTO STRESS TEST - MATRIX VIEW (Extensions × Size Buckets){RESET}".center(190))
    print(f"{BOLD}{CYAN}{'=' * 180}{RESET}")
    
    # Progress
    bar_width = 50
    filled = int(bar_width * progress_pct / 100)
    bar = '█' * filled + '░' * (bar_width - filled)
    print(f"{GREEN}{total_processed:,}/{total_files:,} files ({progress_pct:.1f}%) {RESET}[{CYAN}{bar}{RESET}]")
    
    # Overall stats
    success_color = GREEN if failed == 0 else YELLOW
    print(f"{success_color}Success: {successful:,} ({successful*100/total_processed:.1f}%){RESET} | {RED}Failed: {failed}{RESET}")
    print(f"{BLUE}Scanned: {format_bytes(total_orig_bytes)}{RESET} | {MAGENTA}Compressed: {format_bytes(total_comp_bytes)}{RESET} | {GREEN}Saved: {format_bytes(bytes_saved)} ({avg_ratio:.1f}%){RESET}")
    print(f"{YELLOW}Speed: {files_per_sec:.0f} files/s | {format_bytes(bytes_per_sec)}/s{RESET}")
    
    # Time
    hrs, rem = divmod(int(elapsed), 3600)
    mins, secs = divmod(rem, 60)
    eta_total = elapsed * total_files / total_processed if total_processed > 0 else 0
    eta_remaining = eta_total - elapsed
    eta_hrs, eta_rem = divmod(int(eta_remaining), 3600)
    eta_mins, eta_secs = divmod(eta_rem, 60)
    print(f"{CYAN}Elapsed: {hrs}h {mins}m {secs}s | ETA: {eta_hrs}h {eta_mins}m {eta_secs}s{RESET} | {WHITE}{datetime.now().strftime('%H:%M:%S')}{RESET}")
    
    if latest:
        latest_ratio_color = GREEN if latest.get('compression_ratio', 0) > 0 else RED
        print(f"{WHITE}Latest: {latest['file']}{RESET} ({format_bytes(latest['original_bytes'])} → {format_bytes(latest['compressed_bytes'])}, {latest_ratio_color}{latest.get('compression_ratio', 0):.1f}%{RESET})")
    
    print(f"{BOLD}{CYAN}{'=' * 180}{RESET}")
    print()
    
    # MATRIX TABLE - ROBUST FIXED-WIDTH FORMATTING (No ANSI in width calculations)
    print(f"{BOLD}{WHITE}Extension × Size Matrix (Top 200 Extensions):{RESET}")
    print()
    
    # Define exact column widths (raw character counts, no ANSI escapes)
    EXT_COL_WIDTH = 20
    BUCKET_COL_WIDTH = 16  # "count  ratio%"
    TOTAL_COL_WIDTH = 24   # "count  ratio%  MB"
    
    # Helper to print with exact width (compensates for ANSI codes)
    def print_cell(text, width, color='', align='<'):
        """Print text in color with exact visible width"""
        visible_len = len(text)
        padding = width - visible_len
        if padding < 0:
            text = text[:width]
            padding = 0
        
        if align == '<':
            result = text + ' ' * padding
        elif align == '>':
            result = ' ' * padding + text
        else:  # center
            left_pad = padding // 2
            right_pad = padding - left_pad
            result = ' ' * left_pad + text + ' ' * right_pad
        
        return f"{color}{result}{RESET}" if color else result
    
    # Header row
    print(print_cell("Extension", EXT_COL_WIDTH, f"{CYAN}{BOLD}", '<'), end='')
    for bucket in size_buckets:
        print(print_cell(bucket, BUCKET_COL_WIDTH, f"{CYAN}{BOLD}", '^'), end='')
    print(print_cell("ALL BUCKETS", TOTAL_COL_WIDTH, f"{CYAN}{BOLD}", '^'))
    
    # Separator
    total_width = EXT_COL_WIDTH + (BUCKET_COL_WIDTH * len(size_buckets)) + TOTAL_COL_WIDTH
    print(f"{CYAN}{'-' * total_width}{RESET}")
    
    # Data rows
    for ext in top_ext_names[:200]:
        # Extension name
        ext_display = ext[:EXT_COL_WIDTH-1] if len(ext) >= EXT_COL_WIDTH else ext
        print(print_cell(ext_display, EXT_COL_WIDTH, WHITE, '<'), end='')
        
        # Each size bucket
        for bucket in size_buckets:
            key = (ext, bucket)
            m = matrix[key]
            count = m['count']
            ratio = ((m['orig'] - m['comp']) / m['orig'] * 100) if m['orig'] > 0 else 0
            
            if count > 0:
                if ratio > 15:
                    color = GREEN
                elif ratio > 5:
                    color = YELLOW
                elif ratio > 0:
                    color = WHITE
                else:
                    color = RED
                
                cell_text = f"{count:>6,} {ratio:>3.0f}%"
                print(print_cell(cell_text, BUCKET_COL_WIDTH, color, '>'), end='')
            else:
                print(' ' * BUCKET_COL_WIDTH, end='')
        
        # Row total
        et = ext_totals[ext]
        total_ratio = ((et['orig'] - et['comp']) / et['orig'] * 100) if et['orig'] > 0 else 0
        total_mb = et['orig'] / (1024 * 1024)
        total_color = GREEN if total_ratio > 10 else YELLOW if total_ratio > 0 else RED
        
        total_text = f"{et['count']:>7,} {total_ratio:>3.0f}% {total_mb:>6.1f}MB"
        print(print_cell(total_text, TOTAL_COL_WIDTH, total_color, '>'))
    
    # Separator
    print(f"{CYAN}{'-' * total_width}{RESET}")
    
    # Totals row
    print(print_cell("ALL TYPES", EXT_COL_WIDTH, f"{BOLD}{WHITE}", '<'), end='')
    
    for bucket in size_buckets:
        bt = bucket_totals[bucket]
        ratio = ((bt['orig'] - bt['comp']) / bt['orig'] * 100) if bt['orig'] > 0 else 0
        
        if bt['count'] > 0:
            color = GREEN if ratio > 10 else YELLOW if ratio > 0 else RED
            cell_text = f"{bt['count']:>6,} {ratio:>3.0f}%"
            print(print_cell(cell_text, BUCKET_COL_WIDTH, color, '>'), end='')
        else:
            print(' ' * BUCKET_COL_WIDTH, end='')
    
    # Grand total
    grand_mb = total_orig_bytes / (1024 * 1024)
    grand_text = f"{successful:>7,} {avg_ratio:>3.0f}% {grand_mb:>6.1f}MB"
    print(print_cell(grand_text, TOTAL_COL_WIDTH, f"{BOLD}{GREEN}", '>'))
    
    # Bottom border
    print(f"{BOLD}{CYAN}{'=' * total_width}{RESET}")
    print()
    print(f"{CYAN}Format: [count] [ratio%] [MB] | Top 200 extensions | Ctrl+C to stop{RESET}")

if __name__ == "__main__":
    stats_file = sys.argv[1] if len(sys.argv) > 1 else "stress_stats.json"
    total_files = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    
    display_stats(stats_file, total_files)
