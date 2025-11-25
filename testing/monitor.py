#!/usr/bin/env python3
"""
RTO4LLM - Progress Monitor
=========================
Progress Monitor & Command Injector
====================================
Smart monitoring dashboard for ML training and optimization.
Supports command injection to running processes.

Usage:
    ./monitor.py                    # Interactive dashboard
    ./monitor.py status             # Quick status check
    ./monitor.py inject pause       # Pause training
    ./monitor.py inject resume      # Resume training
    ./monitor.py inject stop        # Stop training
    ./monitor.py summary            # Generate summary tables

License: GPL-3.0-or-later
Repository: https://github.com/StevenGITHUBwork/RTO4LLM

Code contributions by GitHub Copilot (Claude Opus 4.5)
"""

import os
import sys
import json
import time
import curses
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent.parent
STATE_DIR = BASE_DIR / ".state"
IPC_DIR = STATE_DIR / "ipc"
LOG_DIR = BASE_DIR / "logs"

sys.path.insert(0, str(BASE_DIR / "testing"))
from ml_background import IPCChannel, ModelState, generate_summary_table, MODEL_DIR

# ============================================================================
# Summary Tables
# ============================================================================

def generate_progress_table(progress: dict) -> str:
    """Generate progress summary table"""
    if not progress:
        return "No progress data available"
    
    lines = []
    lines.append("┌─────────────────────────────────────────────────────┐")
    lines.append("│          ML TRAINING PROGRESS                       │")
    lines.append("├─────────────────────────────────────────────────────┤")
    
    status = progress.get('status', 'unknown')
    iteration = progress.get('iteration', 0)
    max_iter = progress.get('max_iterations', 100)
    pct = (iteration / max_iter * 100) if max_iter else 0
    
    # Progress bar
    bar_width = 30
    filled = int(bar_width * pct / 100)
    bar = "█" * filled + "░" * (bar_width - filled)
    
    lines.append(f"│ Status:    {status:<38} │")
    lines.append(f"│ Progress:  [{bar}] {pct:5.1f}% │")
    lines.append(f"│ Iteration: {iteration}/{max_iter:<36} │")
    
    if 'batch_success' in progress:
        lines.append(f"│ Batch:     {progress['batch_success']}/{progress['batch_total']} passed{' ':<26}│")
    
    if 'avg_ratio' in progress:
        lines.append(f"│ Avg Ratio: {progress['avg_ratio']:.1f}% compression{' ':<23}│")
    
    if 'total_samples' in progress:
        lines.append(f"│ Samples:   {progress['total_samples']:<38} │")
    
    lines.append("└─────────────────────────────────────────────────────┘")
    
    # Best params table
    if 'best_params' in progress and progress['best_params']:
        lines.append("")
        lines.append("┌────────────────────────────────────────┐")
        lines.append("│ BEST PARAMS BY TYPE                    │")
        lines.append("├──────────┬──────────┬──────────────────┤")
        lines.append("│ Ext      │ min_len  │ top_n            │")
        lines.append("├──────────┼──────────┼──────────────────┤")
        for ext, params in progress['best_params'].items():
            ml = params.get('min_len', 'N/A')
            tn = params.get('top_n', 'N/A')
            lines.append(f"│ .{ext:<7} │ {ml:<8} │ {tn:<16} │")
        lines.append("└──────────┴──────────┴──────────────────┘")
    
    # Top words
    if 'top_words' in progress and progress['top_words']:
        lines.append("")
        lines.append("┌────────────────────────────────────────┐")
        lines.append("│ TOP FREQUENT WORDS                     │")
        lines.append("├────────────────────────┬───────────────┤")
        for word, freq in list(progress['top_words'].items())[:10]:
            lines.append(f"│ {word:<22} │ {freq:>13} │")
        lines.append("└────────────────────────┴───────────────┘")
    
    return "\n".join(lines)


def generate_savings_table() -> str:
    """Generate cumulative savings tracking table"""
    # Load model state
    model_path = MODEL_DIR / "compression_model.pkl"
    if not model_path.exists():
        return "No training data yet"
    
    state = ModelState.load(model_path)
    
    lines = []
    lines.append("┌─────────────────────────────────────────────────────────────┐")
    lines.append("│                    SAVINGS SUMMARY                          │")
    lines.append("├─────────────────────────────────────────────────────────────┤")
    
    # Calculate cumulative savings
    total_original = sum(s.original_size for s in state.samples)
    total_compressed = sum(s.compressed_size for s in state.samples)
    total_savings = total_original - total_compressed
    savings_pct = (total_savings / total_original * 100) if total_original else 0
    
    lines.append(f"│ Total Original:    {total_original:>15,} bytes                 │")
    lines.append(f"│ Total Compressed:  {total_compressed:>15,} bytes                 │")
    lines.append(f"│ Total Savings:     {total_savings:>15,} bytes ({savings_pct:.1f}%)        │")
    lines.append("├─────────────────────────────────────────────────────────────┤")
    
    # Per-type breakdown
    from collections import defaultdict
    by_type = defaultdict(lambda: {'orig': 0, 'comp': 0, 'count': 0, 'success': 0})
    for s in state.samples:
        by_type[s.file_ext]['orig'] += s.original_size
        by_type[s.file_ext]['comp'] += s.compressed_size
        by_type[s.file_ext]['count'] += 1
        if s.success:
            by_type[s.file_ext]['success'] += 1
    
    lines.append("│ TYPE      SAMPLES   SUCCESS%   AVG RATIO                   │")
    lines.append("├─────────────────────────────────────────────────────────────┤")
    
    for ext, data in sorted(by_type.items(), key=lambda x: x[1]['count'], reverse=True)[:8]:
        success_pct = (data['success'] / data['count'] * 100) if data['count'] else 0
        ratio = ((data['orig'] - data['comp']) / data['orig'] * 100) if data['orig'] else 0
        lines.append(f"│ .{ext:<8} {data['count']:>6}   {success_pct:>6.1f}%    {ratio:>6.1f}%                    │")
    
    lines.append("└─────────────────────────────────────────────────────────────┘")
    
    return "\n".join(lines)


# ============================================================================
# Interactive Dashboard (curses)
# ============================================================================

def dashboard(stdscr, job_name: str = "ml_train"):
    """Interactive monitoring dashboard"""
    curses.curs_set(0)
    stdscr.nodelay(True)
    
    channel = IPCChannel(job_name)
    
    # Colors
    curses.start_color()
    curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)
    curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLACK)
    curses.init_pair(3, curses.COLOR_RED, curses.COLOR_BLACK)
    curses.init_pair(4, curses.COLOR_CYAN, curses.COLOR_BLACK)
    
    last_update = 0
    progress = None
    
    while True:
        # Check for input
        try:
            key = stdscr.getch()
            if key == ord('q'):
                break
            elif key == ord('p'):
                channel.send_command('pause')
            elif key == ord('r'):
                channel.send_command('resume')
            elif key == ord('s'):
                channel.send_command('stop')
            elif key == ord('R'):
                # Refresh
                last_update = 0
        except:
            pass
        
        # Update progress every second
        now = time.time()
        if now - last_update >= 1:
            progress = channel.read_progress()
            last_update = now
        
        # Clear and draw
        stdscr.clear()
        height, width = stdscr.getmaxyx()
        
        # Header
        header = f" ML Monitor - {job_name} "
        stdscr.addstr(0, (width - len(header)) // 2, header, curses.A_REVERSE)
        
        # Progress display
        if progress:
            lines = generate_progress_table(progress).split('\n')
            for i, line in enumerate(lines[:height-4]):
                try:
                    stdscr.addstr(2 + i, 2, line[:width-4])
                except:
                    pass
        else:
            stdscr.addstr(2, 2, "Waiting for progress data...", curses.color_pair(2))
        
        # Footer with commands
        footer = " [q]uit  [p]ause  [r]esume  [s]top  [R]efresh "
        stdscr.addstr(height-1, (width - len(footer)) // 2, footer, curses.A_REVERSE)
        
        stdscr.refresh()
        time.sleep(0.1)


# ============================================================================
# CLI
# ============================================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Progress Monitor & Command Injector')
    parser.add_argument('command', nargs='?', default='dashboard',
                       choices=['dashboard', 'status', 'inject', 'summary', 'savings'])
    parser.add_argument('--name', default='ml_train', help='Job name')
    parser.add_argument('action', nargs='?', help='Action for inject (pause/resume/stop)')
    
    args = parser.parse_args()
    
    if args.command == 'dashboard':
        curses.wrapper(dashboard, args.name)
    
    elif args.command == 'status':
        channel = IPCChannel(args.name)
        progress = channel.read_progress()
        print(generate_progress_table(progress))
    
    elif args.command == 'inject':
        if not args.action:
            print("Usage: monitor.py inject <pause|resume|stop>")
            return
        channel = IPCChannel(args.name)
        channel.send_command(args.action)
        print(f"✓ Sent '{args.action}' command to {args.name}")
    
    elif args.command == 'summary':
        model_path = MODEL_DIR / "compression_model.pkl"
        if model_path.exists():
            state = ModelState.load(model_path)
            print(generate_summary_table(state))
        else:
            print("No model found. Run training first.")
    
    elif args.command == 'savings':
        print(generate_savings_table())


if __name__ == '__main__':
    main()
