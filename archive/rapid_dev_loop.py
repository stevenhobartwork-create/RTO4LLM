#!/usr/bin/env python3
"""
Rapid Dev Loop - Quick parameter optimization testing
Archive utility for RTO4LLM development
SPDX-License-Identifier: GPL-3.0-or-later
"""
import os
import sys
import random
import subprocess
import time
from pathlib import Path

# Configuration - use environment variable or default to user's Projects folder
PROJECTS_DIR = Path(os.environ.get("PROJECTS_DIR", Path.home() / "Projects"))
OPTIMIZER_SCRIPT = Path(__file__).parent.parent / "src" / "reversible_text.py"

def find_candidate_files(count=3):
    """Finds files that are likely to be compressible (text, >1KB)."""
    candidates = []
    print("Scanning for candidate files...")
    for root, _, files in os.walk(PROJECTS_DIR):
        for file in files:
            if file.endswith(('.py', '.js', '.ts', '.md', '.c', '.cpp', '.h', '.json', '.txt')):
                path = Path(root) / file
                try:
                    size = os.path.getsize(path)
                    if 1024 < size < 100 * 1024:
                        candidates.append(path)
                except OSError:
                    pass
            if len(candidates) > 100:
                break
    
    if not candidates:
        print("No suitable files found.")
        return []
        
    return random.sample(candidates, min(count, len(candidates)))

def run_variation(file_path, iteration):
    """Runs a single variation of compression parameters."""
    min_len = random.randint(3, 8)
    top_n = random.randint(50, 500)
    fuzz = random.choice([True, False]) if random.random() < 0.1 else False
    seed = random.randint(1, 10000)
    
    try:
        with open(file_path, 'rb') as f:
            original_data = f.read()
    except Exception as e:
        return {'error': str(e)}
        
    orig_size = len(original_data)
    if orig_size == 0:
        return {'error': 'empty'}

    cmd_compress = [
        sys.executable, str(OPTIMIZER_SCRIPT),
        '--compress', '--filename', file_path.name,
        '--min-len', str(min_len), '--top-n', str(top_n), '--seed', str(seed)
    ]
    if fuzz:
        cmd_compress.append('--fuzz')
        
    try:
        start_t = time.time()
        proc = subprocess.run(cmd_compress, input=original_data, capture_output=True, check=True)
        compressed_data = proc.stdout
        comp_time = (time.time() - start_t) * 1000
    except subprocess.CalledProcessError:
        return {'error': 'compress_fail'}
        
    comp_size = len(compressed_data)
    pct = ((orig_size - comp_size) / orig_size) * 100
    
    cmd_expand = [sys.executable, str(OPTIMIZER_SCRIPT), '--expand']
    try:
        proc_exp = subprocess.run(cmd_expand, input=compressed_data, capture_output=True, check=True)
        restored_data = proc_exp.stdout
    except subprocess.CalledProcessError:
        return {'error': 'expand_fail'}
        
    status = "PASS" if original_data == restored_data else "FAIL"
    
    return {
        'iter': iteration, 'file': file_path.name,
        'params': f"len={min_len} top={top_n} fuzz={fuzz}",
        'orig': orig_size, 'comp': comp_size, 'pct': pct, 'time': comp_time, 'status': status
    }

def main():
    print("Rapid Development Loop (30 Iterations x 3 Files)")
    
    files = find_candidate_files(3)
    if not files:
        return

    print(f"Targets: {[f.name for f in files]}")
    print("-" * 80)
    print(f"{'Iter':<4} | {'File':<20} | {'Params':<25} | {'Save%':<6} | {'Time':<6} | {'Status'}")
    print("-" * 80)
    
    best_configs = {}

    for i in range(1, 31):
        for file_path in files:
            result = run_variation(file_path, i)
            
            if 'error' in result:
                print(f"{i:<4} | {file_path.name[:20]:<20} | ERROR: {result['error']}")
                continue
                
            if result['status'] == 'PASS':
                current_best = best_configs.get(file_path.name, {'pct': -1})
                if result['pct'] > current_best['pct']:
                    best_configs[file_path.name] = result
                    is_new_best = "*"
                else:
                    is_new_best = ""
            else:
                is_new_best = "!"
            
            print(f"{i:<4} | {file_path.name[:20]:<20} | {result['params']:<25} | {result['pct']:>5.1f}%{is_new_best} | {result['time']:>4.0f}ms | {result['status']}")
    
    print("-" * 80)
    print("Best Configurations:")
    for fname, data in best_configs.items():
        print(f"  {fname}: {data['pct']:.2f}% with {data['params']}")

if __name__ == "__main__":
    main()
