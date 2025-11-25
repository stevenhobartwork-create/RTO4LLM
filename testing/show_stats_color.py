#!/usr/bin/env python3
"""
Colorized live statistics dashboard with throughput
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
    
    # Extension counts
    ext_counts = defaultdict(int)
    ext_stats = defaultdict(lambda: {'orig': 0, 'comp': 0})
    
    for s in stats:
        if s['success']:
            ext = s['ext']
            ext_counts[ext] += 1
            ext_stats[ext]['orig'] += s['original_bytes']
            ext_stats[ext]['comp'] += s['compressed_bytes']
    
    top_exts = sorted(ext_counts.items(), key=lambda x: x[1], reverse=True)[:20]
    
    latest = stats[-1] if stats else None
    
    # Clear screen
    print("\033[2J\033[H", end='')
    
    # Header
    print(f"{BOLD}{CYAN}{'=' * 140}{RESET}")
    print(f"{BOLD}{MAGENTA}RTO STRESS TEST - LIVE STATISTICS{RESET}".center(150))
    print(f"{BOLD}{CYAN}{'=' * 140}{RESET}")
    
    # Progress bar
    bar_width = 50
    filled = int(bar_width * progress_pct / 100)
    bar = '█' * filled + '░' * (bar_width - filled)
    print(f"{GREEN}{total_processed:,}/{total_files:,} files ({progress_pct:.1f}%) {RESET}[{CYAN}{bar}{RESET}]")
    
    # Success/Fail
    success_color = GREEN if failed == 0 else YELLOW
    print(f"{success_color}Success: {successful:,} ({successful*100/total_processed:.1f}%){RESET} | {RED}Failed: {failed}{RESET}")
    
    # Data stats
    print(f"{BLUE}Data Scanned: {format_bytes(total_orig_bytes)}{RESET} | " +
          f"{MAGENTA}Compressed: {format_bytes(total_comp_bytes)}{RESET} | " +
          f"{GREEN}Saved: {format_bytes(bytes_saved)} ({avg_ratio:.1f}%){RESET}")
    
    # Throughput
    print(f"{YELLOW}Speed: {files_per_sec:.1f} files/s avg | {inst_files_per_sec:.1f} files/s now{RESET}")
    print(f"{YELLOW}Throughput: {format_bytes(bytes_per_sec)}/s avg | {format_bytes(inst_bytes_per_sec)}/s now{RESET}")
    
    # Time
    hrs, rem = divmod(int(elapsed), 3600)
    mins, secs = divmod(rem, 60)
    eta_total = elapsed * total_files / total_processed if total_processed > 0 else 0
    eta_remaining = eta_total - elapsed
    eta_hrs, eta_rem = divmod(int(eta_remaining), 3600)
    eta_mins, eta_secs = divmod(eta_rem, 60)
    
    print(f"{CYAN}Elapsed: {hrs}h {mins}m {secs}s{RESET} | {CYAN}ETA: {eta_hrs}h {eta_mins}m {eta_secs}s{RESET} | {WHITE}{datetime.now().strftime('%H:%M:%S')}{RESET}")
    
    if latest:
        latest_ratio_color = GREEN if latest['compression_ratio'] > 0 else RED
        print(f"{WHITE}Latest: {latest['file']}{RESET} ({format_bytes(latest['original_bytes'])} → {format_bytes(latest['compressed_bytes'])}, {latest_ratio_color}{latest['compression_ratio']:.1f}%{RESET})")
    
    print(f"{BOLD}{CYAN}{'=' * 140}{RESET}")
    print()
    
    # Top extensions table
    print(f"{BOLD}{WHITE}Top 20 File Types:{RESET}")
    print(f"{CYAN}{'Ext':<8} {'Files':>10} {'Original':>12} {'Compressed':>12} {'Saved':>12} {'Ratio':>8}{RESET}")
    print(f"{CYAN}{'-' * 72}{RESET}")
    
    for ext, count in top_exts[:20]:
        orig = ext_stats[ext]['orig']
        comp = ext_stats[ext]['comp']
        saved = orig - comp
        ratio = (saved / orig * 100) if orig > 0 else 0
        ratio_color = GREEN if ratio > 10 else YELLOW if ratio > 0 else RED
        
        print(f"{WHITE}{ext:<8}{RESET} {count:>10,} {format_bytes(orig):>12} {format_bytes(comp):>12} {format_bytes(saved):>12} {ratio_color}{ratio:>7.1f}%{RESET}")
    
    print(f"{CYAN}{'=' * 140}{RESET}")
    print(f"{YELLOW}Press Ctrl+C to stop{RESET}")

if __name__ == "__main__":
    stats_file = sys.argv[1] if len(sys.argv) > 1 else "stress_stats.json"
    total_files = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    
    display_stats(stats_file, total_files)
