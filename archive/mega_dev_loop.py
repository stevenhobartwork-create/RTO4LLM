#!/usr/bin/env python3
"""
Mega Dev Loop - Extended parameter optimization testing
Archive utility for RTO4LLM development
SPDX-License-Identifier: GPL-3.0-or-later

Note: This script was used during development to find optimal compression
parameters by testing many variations. The actual AI assistance came from
GitHub Copilot (Claude) during interactive development sessions.
"""
import os
import sys
import random
import subprocess
import time
from pathlib import Path

# Configuration - use environment variable or default to user's Projects folder
PROJECTS_DIR = Path(os.environ.get("PROJECTS_DIR", Path.home() / "Projects"))
BASE_DIR = Path(__file__).parent.parent
OPTIMIZER_SCRIPT = BASE_DIR / "src" / "reversible_text.py"

def get_random_files(count=1, exclude=None):
    """Find random candidate files for testing."""
    candidates = []
    for root, _, files in os.walk(PROJECTS_DIR):
        for file in files:
            if file.endswith(('.py', '.js', '.ts', '.md', '.c', '.cpp', '.h', '.json', '.txt')):
                path = Path(root) / file
                try:
                    if 100 < os.path.getsize(path) < 500 * 1024:
                        candidates.append(path)
                except:
                    pass
            if len(candidates) > 500:
                break
    
    if exclude:
        candidates = [c for c in candidates if c not in exclude]
        
    if not candidates:
        return []
    return random.sample(candidates, min(count, len(candidates)))

def run_test(file_path, min_len, top_n, fuzz, seed):
    """Run compress/expand cycle and verify roundtrip."""
    try:
        with open(file_path, 'rb') as f:
            original_data = f.read()
    except:
        return None

    orig_size = len(original_data)
    if orig_size == 0:
        return None

    cmd = [
        sys.executable, str(OPTIMIZER_SCRIPT),
        '--compress', '--filename', file_path.name,
        '--min-len', str(min_len), '--top-n', str(top_n), '--seed', str(seed)
    ]
    if fuzz:
        cmd.append('--fuzz')

    try:
        proc = subprocess.run(cmd, input=original_data, capture_output=True, check=True)
        compressed_data = proc.stdout
    except:
        return None

    comp_size = len(compressed_data)
    pct = ((orig_size - comp_size) / orig_size) * 100

    cmd_exp = [sys.executable, str(OPTIMIZER_SCRIPT), '--expand']
    try:
        proc_exp = subprocess.run(cmd_exp, input=compressed_data, capture_output=True, check=True)
        restored_data = proc_exp.stdout
    except:
        return None

    status = "PASS" if original_data == restored_data else "FAIL"
    return {'pct': pct, 'status': status, 'orig': orig_size, 'comp': comp_size}

def main():
    """Run parameter sweep to find optimal compression settings."""
    print("RTO4LLM Parameter Optimization Loop")
    print("=" * 80)
    
    # Phase 1: Focused testing on 2 files
    target_files = get_random_files(2)
    if not target_files:
        print("No files found. Set PROJECTS_DIR environment variable.")
        return
        
    print(f"Phase 1 Targets: {[f.name for f in target_files]}")
    
    best_savings = {f.name: -1.0 for f in target_files}
    
    print(f"\n{'Iter':<4} | {'File':<20} | {'Fuzz':<5} | {'Save%':<6} | {'Status':<4} | {'Note'}")
    print("-" * 80)
    
    for i in range(1, 51):
        fuzz = (i % 2 == 0)
        for f in target_files:
            min_len = random.randint(3, 8)
            top_n = random.randint(50, 400)
            seed = random.randint(1, 9999)
            
            res = run_test(f, min_len, top_n, fuzz, seed)
            if not res:
                continue
            
            note = ""
            if res['status'] == 'PASS':
                if res['pct'] > best_savings[f.name]:
                    best_savings[f.name] = res['pct']
                    note = "BEST"
            
            fuzz_flag = "YES" if fuzz else "NO"
            print(f"{i:<4} | {f.name[:20]:<20} | {fuzz_flag:<5} | {res['pct']:>5.1f}% | {res['status']:<4} | {note}")
    
    # Phase 2: Bulk validation
    print("\n" + "=" * 80)
    print("Phase 2: Bulk Validation (50 random files)")
    print("=" * 80)
    
    random_files = get_random_files(50, exclude=target_files)
    passed = failed = 0
    
    for i, f in enumerate(random_files):
        fuzz = (i % 2 == 0)
        res = run_test(f, 4, 200, fuzz, 42)
        if not res:
            continue
        
        if res['status'] == 'PASS':
            passed += 1
        else:
            failed += 1
            print(f"  FAIL: {f.name}")
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Best savings in Phase 1: {max(best_savings.values()):.1f}%")
    print(f"Phase 2 validation: {passed}/{passed+failed} passed")
    if failed == 0:
        print("✅ All roundtrip tests passed!")
    else:
        print(f"❌ {failed} files failed roundtrip")

if __name__ == "__main__":
    main()
