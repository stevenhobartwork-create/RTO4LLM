#!/usr/bin/env python3
"""
RTO4LLM - Test Harness
======================
Automated testing suite for Reversible Text Optimizer.

License: GPL-3.0-or-later
Repository: https://github.com/StevenGITHUBwork/RTO4LLM

Code contributions and optimizations by:
  - GitHub Copilot (Claude Opus 4.5)

SAFETY: This script NEVER deletes any files, including zero-byte files.
All operations are read-only on source files, write-only to temp/reports.
"""
import os
import sys
import random
import subprocess
import tempfile
import difflib
import time
from pathlib import Path
from collections import defaultdict

# Import safety rails FIRST
sys.path.insert(0, str(Path(__file__).parent / "modules"))
from safety_rails import SafeFileOps, DeletionBlocked, safe_temp_file

# Configuration - Use environment variables or sensible defaults
# Set PROJECTS_DIR env var to your test corpus, or it defaults to current dir
PROJECTS_DIR = Path(os.environ.get("PROJECTS_DIR", "."))
# Project root is parent of testing/ directory
PROJECT_ROOT = Path(__file__).parent.parent
REPORT_DIR = PROJECT_ROOT / "testing" / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
REPORT_FILE = REPORT_DIR / "random_file_test_report.md"

# Initialize safe file operations
SAFE_OPS = SafeFileOps()

def get_random_files(directory, count=100):
    """
    Collect random files for testing.
    SAFETY: Zero-byte files are LOGGED but NEVER deleted.
    """
    text_files = []
    binary_files = []
    problematic_files = []
    
    problem_exts = ('.js', '.c', '.h', '.json')
    zero_byte_log = REPORT_DIR / "zero_byte_files.log"
    zero_byte_log.parent.mkdir(parents=True, exist_ok=True)
    
    for root, _, files in os.walk(directory):
        for file in files:
            path = Path(root) / file
            try:
                file_size = os.path.getsize(path)
                # Zero-byte file handling - LOG ONLY, NEVER DELETE
                if file_size == 0:
                    with open(zero_byte_log, "a") as log:
                        log.write(f"{time.ctime()} | {path} | 0 bytes | SKIPPED (not deleted)\n")
                    # Skip but DO NOT DELETE
                    continue
            except OSError:
                continue

            if file.endswith(problem_exts):
                problematic_files.append(path)
            elif file.endswith(('.py', '.sh', '.md', '.txt', '.cpp', '.ts')):
                text_files.append(path)
            else:
                # Assume others are potentially binary or other types
                binary_files.append(path)
    
    # Target distribution: 25% binary, rest text (with priority to problematic)
    target_binary = int(count * 0.25)
    target_text = count - target_binary
    
    selected = []
    
    # Select binary
    if binary_files:
        selected.extend(random.sample(binary_files, min(target_binary, len(binary_files))))
        
    # Select text (prioritizing problematic)
    remaining_slots = count - len(selected)
    
    if problematic_files:
        # Give higher weight to problematic files (e.g. 50% of text slots)
        prob_slots = min(int(remaining_slots * 0.5), len(problematic_files))
        selected.extend(random.sample(problematic_files, prob_slots))
        remaining_slots -= prob_slots
        
    if text_files and remaining_slots > 0:
        selected.extend(random.sample(text_files, min(remaining_slots, len(text_files))))
        
    # Shuffle
    random.shuffle(selected)
    return selected

def get_random_chunk(file_path, size=None):
    try:
        file_size = os.path.getsize(file_path)
        if file_size == 0:
            return None
            
        # Random size between 256b and 64kb if not specified
        if size is None:
            size = random.randint(256, 65536)

        with open(file_path, 'rb') as f:
            if file_size <= size:
                return f.read()
            
            start = random.randint(0, file_size - size)
            f.seek(start)
            return f.read(size)
    except Exception:
        return None

def run_test():
    print(f"Starting Random File Test...")
    print(f"Source: {PROJECTS_DIR}")
    
    files = get_random_files(PROJECTS_DIR, count=100)
    results = []
    
    os.makedirs(REPORT_DIR, exist_ok=True)
    
    with open(REPORT_FILE, 'w') as report:
        report.write("# Optimizer Random File Test Report\n")
        report.write(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        print(f"\n{'#':<4} | {'File':<30} | {'Size':<6} | {'Entr':<4} | {'Comp':<4} | {'Stat':<4} | {'Save':<6}")
        print("-" * 80)

        for i, file_path in enumerate(files):
            # Progress Table every 10 files
            if i > 0 and i % 10 == 0:
                print(f"--- Progress: {i}/{len(files)} files processed ---")

            # 1. Get Content (Binary)
            original_bytes = get_random_chunk(file_path)
            if not original_bytes:
                # Skip 0-byte or unreadable files
                continue
            
            current_size = len(original_bytes)
                
            # 2. Optimize (Read)
            start_time = time.time()
            tmp_in_path = None
            tmp_opt_path = None
            
            # Metrics
            entropy = 0.0
            ws_ratio = 0.0
            file_type = "unknown"
            
            try:
                # Use safe temp file for input to ensure isolation
                tmp_in_path = SAFE_OPS.safe_write_temp(original_bytes, suffix='.in')
                
                # Get file metadata
                stat = os.stat(file_path)
                
                # Construct command with metadata args
                cmd = [
                    str(READ_OPT),
                    '--filename', file_path.name,
                    '--mtime', str(stat.st_mtime),
                    '--mode', str(stat.st_mode)
                ]
                
                # We need to call the python script directly to pass args, 
                # or update o_read.sh to pass them.
                # Since o_read.sh is a wrapper, let's call the python module directly for the test
                # to ensure we test the metadata feature.
                # Wait, o_read.sh might just be `python3 reversible_text.py --compress`.
                # Let's check o_read.sh content.
                # Assuming we can just call the python script directly for now to support args.
                
                python_script = PROJECT_ROOT / "src" / "reversible_text.py"
                cmd = [sys.executable, str(python_script), '--compress', 
                       '--filename', file_path.name,
                       '--mtime', str(stat.st_mtime),
                       '--mode', str(stat.st_mode)]
                
                with open(tmp_in_path, 'rb') as f_in:
                    proc = subprocess.run(
                        cmd, 
                        stdin=f_in,
                        capture_output=True,
                        check=True
                    )
                optimized_bytes = proc.stdout
                
                # Parse metrics from stderr
                stderr_output = proc.stderr.decode('utf-8', errors='ignore')
                for line in stderr_output.splitlines():
                    if line.startswith("[METRICS]"):
                        # [METRICS] entropy=4.5 ws_ratio=0.1 type=text
                        parts = line.split()
                        for p in parts:
                            if p.startswith("entropy="): entropy = float(p.split('=')[1])
                            if p.startswith("ws_ratio="): ws_ratio = float(p.split('=')[1])
                            if p.startswith("type="): file_type = p.split('=')[1]
                
            except subprocess.CalledProcessError as e:
                print(f"  Optimization Failed: {e}")
                results.append({'file': file_path, 'status': 'FAIL_OPT', 'ext': file_path.suffix})
                if tmp_in_path and os.path.exists(tmp_in_path): SAFE_OPS.cleanup_temp(tmp_in_path)
                continue
            finally:
                if tmp_in_path and os.path.exists(tmp_in_path): SAFE_OPS.cleanup_temp(tmp_in_path)
                
            # 3. Expand (Write/Reverse)
            try:
                # Use safe temp file for optimized input
                tmp_opt_path = SAFE_OPS.safe_write_temp(optimized_bytes, suffix='.opt')
                    
                # Call python script directly for expand
                cmd_expand = [sys.executable, str(python_script), '--expand']
                    
                with open(tmp_opt_path, 'rb') as f_opt:
                    proc = subprocess.run(
                        cmd_expand,
                        stdin=f_opt,
                        capture_output=True,
                        check=True
                    )
                restored_bytes = proc.stdout
                
            except subprocess.CalledProcessError as e:
                print(f"  Expansion Failed: {e}")
                results.append({'file': file_path, 'status': 'FAIL_EXP', 'ext': file_path.suffix})
                if tmp_opt_path and os.path.exists(tmp_opt_path): SAFE_OPS.cleanup_temp(tmp_opt_path)
                continue
            finally:
                if tmp_opt_path and os.path.exists(tmp_opt_path): SAFE_OPS.cleanup_temp(tmp_opt_path)
                
            end_time = time.time()
            duration = (end_time - start_time) * 1000
            
            # 4. Verify
            orig_size = len(original_bytes)
            opt_size = len(optimized_bytes)
            savings = orig_size - opt_size
            savings_pct = (savings / orig_size * 100) if orig_size > 0 else 0
            
            # Compressibility Score (1 - opt/orig)
            comp_score = savings_pct / 100.0
            
            if original_bytes == restored_bytes:
                status = "PASS"
            else:
                status = "FAIL (Diff)"
                print(f"  FAIL: Content mismatch for {file_path.name}")
                # Log diff (text only)
                try:
                    orig_text = original_bytes.decode('utf-8')
                    rest_text = restored_bytes.decode('utf-8')
                    diff = difflib.unified_diff(
                        orig_text.splitlines(), 
                        rest_text.splitlines(), 
                        fromfile='Original', 
                        tofile='Restored'
                    )
                    with open(REPORT_DIR / f"fail_{file_path.name}.diff", 'w') as f:
                        f.writelines(diff)
                except UnicodeDecodeError:
                    print("  (Binary diff mismatch)")
            
            # Compact columns
            # File | Size | Entr | Comp | Stat | Save
            print(f"{i+1:<4} | {file_path.name[:30]:<30} | {current_size:<6} | {entropy:<4.2f} | {comp_score:<4.2f} | {status:<4} | {savings_pct:.1f}%")

            results.append({
                'file': file_path,
                'orig': orig_size,
                'opt': opt_size,
                'pct': savings_pct,
                'time': duration,
                'status': status,
                'ext': file_path.suffix,
                'entropy': entropy,
                'comp': comp_score
            })
            
            # 5. AI Simulation (Only for the first file to satisfy user request)
            if i == 0:
                try:
                    optimized_content = optimized_bytes.decode('utf-8')
                    restored_content = restored_bytes.decode('utf-8')
                    report.write("\n## AI Simulation (First File)\n")
                    report.write(f"**File**: {file_path}\n")
                    report.write("**Optimized Content Snippet**:\n```\n")
                    report.write(optimized_content[:200] + "...\n```\n")
                    report.write("**Restored Content Snippet**:\n```\n")
                    report.write(restored_content[:200] + "...\n```\n")
                except UnicodeDecodeError:
                    report.write("\n## AI Simulation (First File)\n")
                    report.write("(Binary content skipped for display)\n")

        # Generate Report Summary
        report.write("\n## Summary by File Type\n\n")
        report.write("| Extension | Count | Pass | Fail | Avg Savings |\n")
        report.write("|-----------|-------|------|------|-------------|\n")
        
        stats = defaultdict(lambda: {'count': 0, 'pass': 0, 'fail': 0, 'savings': []})
        
        for r in results:
            ext = r['ext'] if r['ext'] else '(no ext)'
            stats[ext]['count'] += 1
            if 'PASS' in r['status']:
                stats[ext]['pass'] += 1
                stats[ext]['savings'].append(r['pct'])
            else:
                stats[ext]['fail'] += 1
                
        for ext, data in sorted(stats.items()):
            avg_sav = sum(data['savings']) / len(data['savings']) if data['savings'] else 0
            report.write(f"| {ext} | {data['count']} | {data['pass']} | {data['fail']} | {avg_sav:.1f}% |\n")
            
        report.write("\n## Detailed Results\n\n")
        report.write("| File | Original | Opt | Savings | Time | Status |\n")
        report.write("|------|----------|-----|---------|------|--------|\n")
        
        for r in results:
            report.write(f"| {r['file'].name} | {r.get('orig','-')} | {r.get('opt','-')} | {r.get('pct',0):.1f}% | {r.get('time',0):.0f}ms | {r['status']} |\n")

        # Final Stats
        total_orig = sum(r['orig'] for r in results)
        total_opt = sum(r['opt'] for r in results)
        total_saved = total_orig - total_opt
        total_pct = (total_saved / total_orig * 100) if total_orig > 0 else 0
        avg_savings = sum(r['pct'] for r in results) / len(results) if results else 0
        
        print("\n" + "="*60)
        print(f"FINAL RESULTS ({len(results)} files)")
        print(f"Total Original Size: {total_orig:,} bytes")
        print(f"Total Optimized Size: {total_opt:,} bytes")
        print(f"Total Saved: {total_saved:,} bytes ({total_pct:.1f}%)")
        print(f"Average Savings per File: {avg_savings:.1f}%")
        print("="*60 + "\n")
        
        report.write(f"\n## Final Stats\n")
        report.write(f"- Total Original: {total_orig:,} bytes\n")
        report.write(f"- Total Optimized: {total_opt:,} bytes\n")
        report.write(f"- Total Saved: {total_saved:,} bytes ({total_pct:.1f}%)\n")
        report.write(f"- Avg Savings: {avg_savings:.1f}%\n")

    print(f"Test complete. Report saved to {REPORT_FILE}")

if __name__ == "__main__":
    run_test()
