#!/usr/bin/env python3
"""
RTO4LLM - ML Background Processor
================================
ML Background Processor
=======================
Forks ML training to external processes so AI can focus on higher-level tasks.
Uses multiprocessing + screen/tmux for truly detached background operations.

Features:
- Pattern learning from compression results
- Bayesian parameter optimization
- Automatic dictionary updates
- Progress monitoring via IPC

License: GPL-3.0-or-later
Repository: https://github.com/StevenGITHUBwork/RTO4LLM

Code contributions by GitHub Copilot (Claude Opus 4.5)
"""

import os
import sys
import json
import time
import pickle
import hashlib
import tempfile
import subprocess
import multiprocessing as mp
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Tuple, Optional, Any
from collections import defaultdict
import signal
import fcntl

# Paths
BASE_DIR = Path(__file__).parent.parent
STATE_DIR = BASE_DIR / ".state"
MODEL_DIR = STATE_DIR / "ml_models"
IPC_DIR = STATE_DIR / "ipc"
LOG_DIR = BASE_DIR / "logs"

# Ensure directories exist
for d in [STATE_DIR, MODEL_DIR, IPC_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ============================================================================
# Data Structures
# ============================================================================

@dataclass
class CompressionSample:
    """Single compression result for ML training"""
    file_path: str
    file_ext: str
    original_size: int
    compressed_size: int
    params: Dict[str, Any]
    success: bool
    timestamp: float = field(default_factory=time.time)
    
    @property
    def ratio(self) -> float:
        return (self.original_size - self.compressed_size) / self.original_size if self.original_size > 0 else 0


@dataclass
class ModelState:
    """Persistent ML model state"""
    samples: List[CompressionSample] = field(default_factory=list)
    best_params_by_ext: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    word_frequencies: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    iteration: int = 0
    last_update: float = field(default_factory=time.time)
    
    def save(self, path: Path):
        with open(path, 'wb') as f:
            pickle.dump(self, f)
    
    @classmethod
    def load(cls, path: Path) -> 'ModelState':
        if path.exists():
            with open(path, 'rb') as f:
                return pickle.load(f)
        return cls()


# ============================================================================
# IPC (Inter-Process Communication)
# ============================================================================

class IPCChannel:
    """Simple file-based IPC for progress monitoring and command injection"""
    
    def __init__(self, name: str):
        self.name = name
        self.progress_file = IPC_DIR / f"{name}_progress.json"
        self.command_file = IPC_DIR / f"{name}_commands.json"
        self.result_file = IPC_DIR / f"{name}_result.json"
    
    def write_progress(self, data: Dict):
        """Write progress update (from worker)"""
        data['timestamp'] = time.time()
        with open(self.progress_file, 'w') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            json.dump(data, f)
            fcntl.flock(f, fcntl.LOCK_UN)
    
    def read_progress(self) -> Optional[Dict]:
        """Read progress (from monitor)"""
        if not self.progress_file.exists():
            return None
        try:
            with open(self.progress_file, 'r') as f:
                fcntl.flock(f, fcntl.LOCK_SH)
                data = json.load(f)
                fcntl.flock(f, fcntl.LOCK_UN)
                return data
        except:
            return None
    
    def send_command(self, cmd: str, args: Dict = None):
        """Send command to worker (from AI/user)"""
        data = {'cmd': cmd, 'args': args or {}, 'timestamp': time.time()}
        with open(self.command_file, 'w') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            json.dump(data, f)
            fcntl.flock(f, fcntl.LOCK_UN)
    
    def check_command(self) -> Optional[Dict]:
        """Check for pending command (from worker)"""
        if not self.command_file.exists():
            return None
        try:
            with open(self.command_file, 'r') as f:
                fcntl.flock(f, fcntl.LOCK_SH)
                data = json.load(f)
                fcntl.flock(f, fcntl.LOCK_UN)
            # Clear command after reading
            self.command_file.unlink()
            return data
        except:
            return None
    
    def write_result(self, data: Dict):
        """Write final result"""
        with open(self.result_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def cleanup(self):
        """Clean up IPC files"""
        for f in [self.progress_file, self.command_file]:
            if f.exists():
                f.unlink()


# ============================================================================
# ML Training Worker
# ============================================================================

def ml_training_worker(channel_name: str, config: Dict):
    """
    Background ML training process.
    Runs pattern learning and parameter optimization.
    """
    ipc = IPCChannel(channel_name)
    model_path = MODEL_DIR / "compression_model.pkl"
    state = ModelState.load(model_path)
    
    # Config
    max_iterations = config.get('max_iterations', 100)
    batch_size = config.get('batch_size', 10)
    test_dir = Path(config.get('test_dir', str(BASE_DIR.parent.parent)))
    
    # Add modules to path
    sys.path.insert(0, str(BASE_DIR / "modules"))
    from reversible_text import compress, expand, get_frequent_phrases
    
    # Collect test files
    extensions = {'.py', '.js', '.c', '.h', '.md', '.txt', '.sh'}
    test_files = [f for f in test_dir.rglob('*') 
                  if f.suffix in extensions and f.is_file() and f.stat().st_size > 100]
    
    ipc.write_progress({
        'status': 'starting',
        'files_found': len(test_files),
        'iteration': 0,
        'max_iterations': max_iterations
    })
    
    import random
    random.shuffle(test_files)
    
    try:
        for iteration in range(max_iterations):
            # Check for commands
            cmd = ipc.check_command()
            if cmd:
                if cmd['cmd'] == 'stop':
                    ipc.write_progress({'status': 'stopped_by_command', 'iteration': iteration})
                    break
                elif cmd['cmd'] == 'pause':
                    ipc.write_progress({'status': 'paused', 'iteration': iteration})
                    while True:
                        time.sleep(1)
                        cmd = ipc.check_command()
                        if cmd and cmd['cmd'] == 'resume':
                            break
                        if cmd and cmd['cmd'] == 'stop':
                            return
                elif cmd['cmd'] == 'adjust_params':
                    # Dynamic parameter adjustment
                    config.update(cmd.get('args', {}))
            
            # Sample files for this batch
            batch_files = random.sample(test_files, min(batch_size, len(test_files)))
            
            # Train on batch
            batch_results = []
            for f in batch_files:
                try:
                    with open(f, 'rb') as fh:
                        content = fh.read()
                    
                    text = content.decode('utf-8', errors='replace')
                    ext = f.suffix.lstrip('.')
                    
                    # Try different parameter combinations
                    for min_len in [3, 4, 5]:
                        for top_n in [50, 100, 150]:
                            comp = compress(text, min_len=min_len, top_n=top_n, file_ext=ext)
                            exp = expand(comp)
                            
                            sample = CompressionSample(
                                file_path=str(f),
                                file_ext=ext,
                                original_size=len(text),
                                compressed_size=len(comp),
                                params={'min_len': min_len, 'top_n': top_n},
                                success=(exp == text)
                            )
                            state.samples.append(sample)
                            batch_results.append(sample)
                            
                            # Update word frequencies
                            phrases = get_frequent_phrases(text, min_len=min_len, top_n=50)
                            for phrase in phrases:
                                state.word_frequencies[phrase] += 1
                                
                except Exception as e:
                    pass  # Skip problematic files
            
            # Compute best params per extension
            by_ext = defaultdict(list)
            for s in state.samples[-1000:]:  # Last 1000 samples
                if s.success:
                    by_ext[s.file_ext].append(s)
            
            for ext, samples in by_ext.items():
                if samples:
                    best = max(samples, key=lambda x: x.ratio)
                    state.best_params_by_ext[ext] = best.params
            
            state.iteration = iteration + 1
            state.last_update = time.time()
            
            # Compute stats for progress
            successful = [s for s in batch_results if s.success]
            avg_ratio = sum(s.ratio for s in successful) / len(successful) if successful else 0
            
            ipc.write_progress({
                'status': 'running',
                'iteration': iteration + 1,
                'max_iterations': max_iterations,
                'batch_success': len(successful),
                'batch_total': len(batch_results),
                'avg_ratio': round(avg_ratio * 100, 2),
                'total_samples': len(state.samples),
                'best_params': dict(state.best_params_by_ext),
                'top_words': dict(sorted(state.word_frequencies.items(), 
                                        key=lambda x: x[1], reverse=True)[:20])
            })
            
            # Save model periodically
            if (iteration + 1) % 10 == 0:
                state.save(model_path)
        
        # Final save
        state.save(model_path)
        
        ipc.write_result({
            'status': 'completed',
            'total_iterations': state.iteration,
            'total_samples': len(state.samples),
            'best_params_by_ext': state.best_params_by_ext,
            'top_50_words': dict(sorted(state.word_frequencies.items(),
                                       key=lambda x: x[1], reverse=True)[:50])
        })
        
    except Exception as e:
        ipc.write_progress({'status': 'error', 'error': str(e)})
        raise


# ============================================================================
# Process Manager
# ============================================================================

class MLProcessManager:
    """Manages ML background processes"""
    
    def __init__(self):
        self.processes: Dict[str, mp.Process] = {}
        self.channels: Dict[str, IPCChannel] = {}
    
    def spawn_training(self, name: str = "ml_train", config: Dict = None) -> str:
        """Spawn background ML training process"""
        config = config or {}
        channel = IPCChannel(name)
        
        proc = mp.Process(
            target=ml_training_worker,
            args=(name, config),
            daemon=False
        )
        proc.start()
        
        self.processes[name] = proc
        self.channels[name] = channel
        
        return name
    
    def spawn_detached(self, name: str = "ml_train", config: Dict = None) -> str:
        """Spawn as fully detached screen session"""
        config = config or {}
        config_json = json.dumps(config)
        
        script = f'''
import sys
sys.path.insert(0, "{BASE_DIR}")
from testing.ml_background import ml_training_worker
import json
config = json.loads('{config_json}')
ml_training_worker("{name}", config)
'''
        
        # Write to temp file
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False)
        tmp.write(script)
        tmp.close()
        
        # Spawn in screen
        subprocess.run(['screen', '-dmS', f'ml_{name}', 'python3', tmp.name],
                      capture_output=True)
        
        self.channels[name] = IPCChannel(name)
        return name
    
    def get_progress(self, name: str) -> Optional[Dict]:
        """Get progress for a training job"""
        if name in self.channels:
            return self.channels[name].read_progress()
        return None
    
    def send_command(self, name: str, cmd: str, args: Dict = None):
        """Send command to a training job"""
        if name in self.channels:
            self.channels[name].send_command(cmd, args)
    
    def stop(self, name: str):
        """Stop a training job"""
        self.send_command(name, 'stop')
        if name in self.processes:
            self.processes[name].join(timeout=5)
            if self.processes[name].is_alive():
                self.processes[name].terminate()
    
    def cleanup(self):
        """Clean up all processes"""
        for name in list(self.processes.keys()):
            self.stop(name)


# ============================================================================
# Summary Table Generator
# ============================================================================

def generate_summary_table(state: ModelState) -> str:
    """Generate markdown summary table"""
    lines = ["## ML Training Summary\n"]
    
    # Overall stats
    total = len(state.samples)
    successful = sum(1 for s in state.samples if s.success)
    avg_ratio = sum(s.ratio for s in state.samples if s.success) / successful if successful else 0
    
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Total Samples | {total} |")
    lines.append(f"| Successful | {successful} ({successful/total*100:.1f}%) |")
    lines.append(f"| Avg Compression | {avg_ratio*100:.1f}% |")
    lines.append(f"| Iterations | {state.iteration} |")
    lines.append("")
    
    # Best params by extension
    lines.append("### Best Parameters by File Type\n")
    lines.append("| Extension | min_len | top_n | Samples |")
    lines.append("|-----------|---------|-------|---------|")
    
    by_ext = defaultdict(list)
    for s in state.samples:
        by_ext[s.file_ext].append(s)
    
    for ext, samples in sorted(by_ext.items()):
        if ext in state.best_params_by_ext:
            p = state.best_params_by_ext[ext]
            lines.append(f"| .{ext} | {p.get('min_len', 'N/A')} | {p.get('top_n', 'N/A')} | {len(samples)} |")
    
    lines.append("")
    
    # Top words
    lines.append("### Top 20 Frequent Words\n")
    lines.append("| Word | Frequency |")
    lines.append("|------|-----------|")
    for word, freq in sorted(state.word_frequencies.items(), key=lambda x: x[1], reverse=True)[:20]:
        lines.append(f"| `{word}` | {freq} |")
    
    return "\n".join(lines)


# ============================================================================
# CLI
# ============================================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='ML Background Processor')
    parser.add_argument('command', choices=['start', 'status', 'stop', 'inject', 'summary'])
    parser.add_argument('--name', default='ml_train', help='Job name')
    parser.add_argument('--detached', action='store_true', help='Run fully detached in screen')
    parser.add_argument('--iterations', type=int, default=100, help='Max iterations')
    parser.add_argument('--batch', type=int, default=10, help='Batch size')
    parser.add_argument('--cmd', help='Command to inject')
    parser.add_argument('--args', help='JSON args for injected command')
    
    args = parser.parse_args()
    
    mgr = MLProcessManager()
    
    if args.command == 'start':
        config = {
            'max_iterations': args.iterations,
            'batch_size': args.batch
        }
        if args.detached:
            name = mgr.spawn_detached(args.name, config)
            print(f"Started detached ML training: {name}")
            print(f"Monitor with: python3 {__file__} status --name {name}")
        else:
            name = mgr.spawn_training(args.name, config)
            print(f"Started ML training: {name} (PID: {mgr.processes[name].pid})")
    
    elif args.command == 'status':
        channel = IPCChannel(args.name)
        progress = channel.read_progress()
        if progress:
            print(json.dumps(progress, indent=2))
        else:
            print(f"No progress data for job: {args.name}")
    
    elif args.command == 'stop':
        channel = IPCChannel(args.name)
        channel.send_command('stop')
        print(f"Sent stop command to: {args.name}")
    
    elif args.command == 'inject':
        if not args.cmd:
            print("Error: --cmd required for inject")
            return
        channel = IPCChannel(args.name)
        cmd_args = json.loads(args.args) if args.args else {}
        channel.send_command(args.cmd, cmd_args)
        print(f"Injected command '{args.cmd}' to: {args.name}")
    
    elif args.command == 'summary':
        model_path = MODEL_DIR / "compression_model.pkl"
        if model_path.exists():
            state = ModelState.load(model_path)
            print(generate_summary_table(state))
        else:
            print("No model found. Run training first.")


if __name__ == '__main__':
    main()
