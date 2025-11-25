#!/usr/bin/env python3
"""
RTO4LLM - Module Contribution Tracker
====================================
Module Contribution Tracker
============================
Tracks how much each compression module contributes to overall savings.
Enables detection and disabling of redundant modules.

DEV MODE ONLY - Adds overhead, don't use in production.

Usage:
    from module_tracker import ModuleTracker, DEV_MODE
    
    if DEV_MODE:
        tracker = ModuleTracker()
        tracker.start_module("dict_compress")
        # ... do work ...
        tracker.end_module("dict_compress", before_size, after_size)
        tracker.report()

License: GPL-3.0-or-later
Repository: https://github.com/StevenGITHUBwork/RTO4LLM

Code contributions by GitHub Copilot (Claude Opus 4.5)
"""

import os
import sys
import json
import time
import random
import statistics
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime

# ============================================================================
# Configuration
# ============================================================================

# DEV_MODE controlled by environment variable
DEV_MODE = os.environ.get('OPTIMIZER_DEV_MODE', '0') == '1'

# State file for tracking across runs
STATE_DIR = Path(__file__).parent.parent / "state"
TRACKER_STATE = STATE_DIR / "module_contributions.json"

# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class ModuleStats:
    """Statistics for a single module"""
    name: str
    calls: int = 0
    total_bytes_in: int = 0
    total_bytes_out: int = 0
    total_savings: int = 0  # bytes saved
    total_time_ms: float = 0.0
    savings_history: List[float] = field(default_factory=list)  # % savings per call
    
    @property
    def avg_savings_pct(self) -> float:
        if not self.savings_history:
            return 0.0
        return statistics.mean(self.savings_history)
    
    @property
    def savings_stddev(self) -> float:
        if len(self.savings_history) < 2:
            return 0.0
        return statistics.stdev(self.savings_history)
    
    @property
    def avg_time_ms(self) -> float:
        return self.total_time_ms / max(1, self.calls)
    
    def record(self, bytes_in: int, bytes_out: int, time_ms: float):
        """Record a module execution"""
        self.calls += 1
        self.total_bytes_in += bytes_in
        self.total_bytes_out += bytes_out
        self.total_savings += (bytes_in - bytes_out)
        self.total_time_ms += time_ms
        
        if bytes_in > 0:
            pct = ((bytes_in - bytes_out) / bytes_in) * 100
            self.savings_history.append(pct)
            # Keep only last 100 samples
            if len(self.savings_history) > 100:
                self.savings_history = self.savings_history[-100:]
    
    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'calls': self.calls,
            'total_bytes_in': self.total_bytes_in,
            'total_bytes_out': self.total_bytes_out,
            'total_savings': self.total_savings,
            'total_time_ms': self.total_time_ms,
            'savings_history': self.savings_history[-20:],  # Save only last 20
            'avg_savings_pct': self.avg_savings_pct,
            'savings_stddev': self.savings_stddev,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'ModuleStats':
        stats = cls(name=data['name'])
        stats.calls = data.get('calls', 0)
        stats.total_bytes_in = data.get('total_bytes_in', 0)
        stats.total_bytes_out = data.get('total_bytes_out', 0)
        stats.total_savings = data.get('total_savings', 0)
        stats.total_time_ms = data.get('total_time_ms', 0.0)
        stats.savings_history = data.get('savings_history', [])
        return stats


@dataclass
class ModuleOrder:
    """Tracks module execution order for shuffling"""
    default_order: List[str] = field(default_factory=list)
    current_order: List[str] = field(default_factory=list)
    shuffle_enabled: bool = True
    
    def shuffle(self) -> List[str]:
        """Return shuffled order (if enabled)"""
        if self.shuffle_enabled and self.current_order:
            random.shuffle(self.current_order)
        return self.current_order
    
    def reset(self):
        """Reset to default order"""
        self.current_order = self.default_order.copy()


# ============================================================================
# Tracker Class
# ============================================================================

class ModuleTracker:
    """
    Tracks module contributions to compression.
    
    Usage:
        tracker = ModuleTracker()
        tracker.start_module("my_module")
        # ... do compression work ...
        tracker.end_module("my_module", input_size, output_size)
        tracker.report()
    """
    
    def __init__(self, enabled: bool = None):
        """Initialize tracker. Enabled by DEV_MODE unless overridden."""
        self.enabled = enabled if enabled is not None else DEV_MODE
        self.modules: Dict[str, ModuleStats] = {}
        self.active_module: Optional[str] = None
        self.active_start_time: float = 0.0
        self.order = ModuleOrder()
        self.session_start = datetime.now().isoformat()
        
        # Load existing state
        if self.enabled:
            self._load_state()
    
    def _load_state(self):
        """Load persisted state from disk"""
        if TRACKER_STATE.exists():
            try:
                with open(TRACKER_STATE, 'r') as f:
                    data = json.load(f)
                    for name, stats_data in data.get('modules', {}).items():
                        self.modules[name] = ModuleStats.from_dict(stats_data)
                    self.order.default_order = data.get('default_order', [])
                    self.order.current_order = data.get('current_order', self.order.default_order.copy())
            except (json.JSONDecodeError, KeyError):
                pass  # Start fresh on error
    
    def _save_state(self):
        """Persist state to disk"""
        if not self.enabled:
            return
            
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            'modules': {name: stats.to_dict() for name, stats in self.modules.items()},
            'default_order': self.order.default_order,
            'current_order': self.order.current_order,
            'last_updated': datetime.now().isoformat(),
        }
        with open(TRACKER_STATE, 'w') as f:
            json.dump(data, f, indent=2)
    
    def register_module(self, name: str, order_index: int = None):
        """Register a module for tracking"""
        if name not in self.modules:
            self.modules[name] = ModuleStats(name=name)
        
        if name not in self.order.default_order:
            if order_index is not None:
                self.order.default_order.insert(order_index, name)
            else:
                self.order.default_order.append(name)
            self.order.current_order = self.order.default_order.copy()
    
    def start_module(self, name: str):
        """Mark module as starting (for timing)"""
        if not self.enabled:
            return
        
        self.register_module(name)
        self.active_module = name
        self.active_start_time = time.time()
    
    def end_module(self, name: str, bytes_in: int, bytes_out: int):
        """Record module completion with results"""
        if not self.enabled:
            return
        
        elapsed_ms = (time.time() - self.active_start_time) * 1000
        
        if name not in self.modules:
            self.modules[name] = ModuleStats(name=name)
        
        self.modules[name].record(bytes_in, bytes_out, elapsed_ms)
        self.active_module = None
        
        # Auto-save periodically
        total_calls = sum(m.calls for m in self.modules.values())
        if total_calls % 10 == 0:
            self._save_state()
    
    def get_execution_order(self, shuffle: bool = None) -> List[str]:
        """Get module execution order (optionally shuffled)"""
        if shuffle is None:
            shuffle = self.order.shuffle_enabled
        
        if shuffle:
            return self.order.shuffle()
        return self.order.current_order.copy()
    
    def find_redundant_modules(self, threshold_pct: float = 0.5, min_calls: int = 10) -> List[str]:
        """
        Find modules that contribute less than threshold_pct savings on average.
        
        Args:
            threshold_pct: Modules with avg savings below this are "redundant"
            min_calls: Minimum calls before considering a module for redundancy
            
        Returns:
            List of module names that appear redundant
        """
        redundant = []
        for name, stats in self.modules.items():
            if stats.calls >= min_calls and stats.avg_savings_pct < threshold_pct:
                redundant.append(name)
        return redundant
    
    def report(self, file=None) -> str:
        """Generate human-readable report of module contributions"""
        if file is None:
            file = sys.stderr
        
        lines = [
            "",
            "=" * 70,
            "MODULE CONTRIBUTION REPORT (DEV MODE)",
            "=" * 70,
            "",
            f"{'Module':<25} {'Calls':>8} {'Avg%':>8} {'Stddev':>8} {'Time(ms)':>10} {'Bytes Saved':>12}",
            "-" * 70,
        ]
        
        # Sort by contribution (highest first)
        sorted_modules = sorted(
            self.modules.values(),
            key=lambda m: m.avg_savings_pct,
            reverse=True
        )
        
        for stats in sorted_modules:
            lines.append(
                f"{stats.name:<25} {stats.calls:>8} "
                f"{stats.avg_savings_pct:>7.2f}% {stats.savings_stddev:>7.2f}% "
                f"{stats.avg_time_ms:>10.1f} {stats.total_savings:>12,}"
            )
        
        lines.append("-" * 70)
        
        # Summary
        total_savings = sum(m.total_savings for m in self.modules.values())
        total_in = sum(m.total_bytes_in for m in self.modules.values())
        overall_pct = (total_savings / max(1, total_in)) * 100
        
        lines.append(f"Total savings: {total_savings:,} bytes ({overall_pct:.1f}%)")
        
        # Redundant modules
        redundant = self.find_redundant_modules()
        if redundant:
            lines.append(f"\n⚠️  Potentially redundant modules (< 0.5% avg): {', '.join(redundant)}")
        
        lines.append("=" * 70)
        lines.append("")
        
        report_text = "\n".join(lines)
        
        if file:
            file.write(report_text)
        
        return report_text
    
    def disable_module(self, name: str):
        """Disable a module from execution order"""
        if name in self.order.current_order:
            self.order.current_order.remove(name)
    
    def enable_module(self, name: str):
        """Re-enable a disabled module"""
        if name not in self.order.current_order and name in self.order.default_order:
            # Restore to original position
            idx = self.order.default_order.index(name)
            self.order.current_order.insert(min(idx, len(self.order.current_order)), name)
    
    def save(self):
        """Explicitly save state"""
        self._save_state()


# ============================================================================
# Compression Pipeline with Tracking
# ============================================================================

class TrackedPipeline:
    """
    A compression pipeline that tracks each stage's contribution.
    
    Usage:
        pipeline = TrackedPipeline(shuffle=True)
        pipeline.add_stage("whitespace", remove_whitespace_func)
        pipeline.add_stage("dict", dict_compress_func)
        
        result = pipeline.run(input_text)
        pipeline.report()
    """
    
    def __init__(self, shuffle: bool = True, tracker: ModuleTracker = None):
        self.tracker = tracker or ModuleTracker()
        self.stages: List[Tuple[str, callable]] = []
        self.shuffle = shuffle
    
    def add_stage(self, name: str, func: callable):
        """
        Add a compression stage.
        
        func signature: func(text: str) -> str
        """
        self.stages.append((name, func))
        self.tracker.register_module(name)
    
    def run(self, text: str) -> str:
        """Run all stages, tracking each one's contribution"""
        # Optionally shuffle order
        stage_order = list(range(len(self.stages)))
        if self.shuffle and self.tracker.enabled:
            random.shuffle(stage_order)
        
        current = text
        
        for idx in stage_order:
            name, func = self.stages[idx]
            
            before_size = len(current.encode('utf-8'))
            self.tracker.start_module(name)
            
            try:
                current = func(current)
            except Exception as e:
                # Don't let tracking errors break compression
                sys.stderr.write(f"[TRACKER] Stage {name} failed: {e}\n")
            
            after_size = len(current.encode('utf-8'))
            self.tracker.end_module(name, before_size, after_size)
        
        return current
    
    def report(self):
        """Print contribution report"""
        self.tracker.report()
    
    def save(self):
        """Save tracker state"""
        self.tracker.save()


# ============================================================================
# Redundancy Detector
# ============================================================================

class RedundancyDetector:
    """
    Tests modules on random files to find which ones are useless.
    
    Usage:
        detector = RedundancyDetector(test_dir="/path/to/test/files")
        results = detector.run(iterations=50)
        print(results.report())
    """
    
    def __init__(self, test_dir: str = None, file_extensions: List[str] = None):
        self.test_dir = Path(test_dir) if test_dir else Path(__file__).parent.parent / "testing"
        self.extensions = file_extensions or ['.py', '.sh', '.md', '.txt', '.json']
        self.test_files: List[Path] = []
        self._collect_files()
    
    def _collect_files(self):
        """Collect test files from directory"""
        if not self.test_dir.exists():
            return
        
        for ext in self.extensions:
            self.test_files.extend(self.test_dir.rglob(f"*{ext}"))
        
        # Also check parent directories
        for parent in [self.test_dir.parent, self.test_dir.parent.parent]:
            for ext in self.extensions:
                self.test_files.extend(parent.glob(f"*{ext}"))
    
    def run(self, stages: List[Tuple[str, callable]], iterations: int = 50) -> 'RedundancyResults':
        """
        Test each module's contribution across random files.
        
        Args:
            stages: List of (name, func) tuples for compression stages
            iterations: Number of files to test
            
        Returns:
            RedundancyResults object with analysis
        """
        results = RedundancyResults()
        
        if not self.test_files:
            results.error = "No test files found"
            return results
        
        # Sample files
        sample_size = min(iterations, len(self.test_files))
        test_sample = random.sample(self.test_files, sample_size)
        
        for file_path in test_sample:
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                
                if not content or len(content) < 50:
                    continue
                
                # Test each stage individually
                for name, func in stages:
                    before = len(content.encode('utf-8'))
                    try:
                        after_content = func(content)
                        after = len(after_content.encode('utf-8'))
                        savings_pct = ((before - after) / before) * 100 if before > 0 else 0
                        results.record(name, file_path.suffix, savings_pct)
                    except Exception:
                        results.record_error(name)
                        
            except Exception:
                continue
        
        results.finalize()
        return results


@dataclass
class RedundancyResults:
    """Results from redundancy detection"""
    module_stats: Dict[str, List[float]] = field(default_factory=dict)
    module_by_ext: Dict[str, Dict[str, List[float]]] = field(default_factory=dict)
    module_errors: Dict[str, int] = field(default_factory=dict)
    error: str = None
    redundant_modules: List[str] = field(default_factory=list)
    
    def record(self, module: str, extension: str, savings_pct: float):
        """Record a test result"""
        if module not in self.module_stats:
            self.module_stats[module] = []
            self.module_by_ext[module] = {}
        
        self.module_stats[module].append(savings_pct)
        
        if extension not in self.module_by_ext[module]:
            self.module_by_ext[module][extension] = []
        self.module_by_ext[module][extension].append(savings_pct)
    
    def record_error(self, module: str):
        """Record an error for a module"""
        self.module_errors[module] = self.module_errors.get(module, 0) + 1
    
    def finalize(self, redundancy_threshold: float = 0.5):
        """Analyze results and identify redundant modules"""
        for module, savings in self.module_stats.items():
            if savings and statistics.mean(savings) < redundancy_threshold:
                self.redundant_modules.append(module)
    
    def report(self) -> str:
        """Generate human-readable report"""
        if self.error:
            return f"Error: {self.error}"
        
        lines = [
            "",
            "=" * 70,
            "REDUNDANCY DETECTION RESULTS",
            "=" * 70,
            "",
            f"{'Module':<25} {'Tests':>8} {'Avg%':>8} {'Min%':>8} {'Max%':>8} {'Errors':>8}",
            "-" * 70,
        ]
        
        for module in sorted(self.module_stats.keys()):
            savings = self.module_stats[module]
            if not savings:
                continue
            
            avg = statistics.mean(savings)
            mn = min(savings)
            mx = max(savings)
            errs = self.module_errors.get(module, 0)
            
            marker = " ⚠️" if module in self.redundant_modules else ""
            
            lines.append(
                f"{module:<25} {len(savings):>8} {avg:>7.2f}% {mn:>7.2f}% {mx:>7.2f}% {errs:>8}{marker}"
            )
        
        lines.append("-" * 70)
        
        if self.redundant_modules:
            lines.append(f"\n⚠️  Redundant modules (< 0.5% avg): {', '.join(self.redundant_modules)}")
            lines.append("   Consider disabling these to reduce overhead.")
        else:
            lines.append("\n✓ No redundant modules detected.")
        
        lines.append("=" * 70)
        
        return "\n".join(lines)


# ============================================================================
# CLI
# ============================================================================

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Module Contribution Tracker')
    parser.add_argument('--report', action='store_true', help='Show contribution report')
    parser.add_argument('--reset', action='store_true', help='Reset all statistics')
    parser.add_argument('--redundant', action='store_true', help='List redundant modules')
    parser.add_argument('--enable-dev', action='store_true', help='Show how to enable dev mode')
    
    args = parser.parse_args()
    
    if args.enable_dev:
        print("To enable module tracking, set environment variable:")
        print("  export OPTIMIZER_DEV_MODE=1")
        print("")
        print("Then run your compression. Reports will show module contributions.")
        sys.exit(0)
    
    if args.reset:
        if TRACKER_STATE.exists():
            TRACKER_STATE.unlink()
            print("Statistics reset.")
        else:
            print("No statistics to reset.")
        sys.exit(0)
    
    # Force enable for CLI
    tracker = ModuleTracker(enabled=True)
    
    if args.report:
        if not tracker.modules:
            print("No module statistics yet. Run compressions with OPTIMIZER_DEV_MODE=1 first.")
        else:
            tracker.report(file=sys.stdout)
        sys.exit(0)
    
    if args.redundant:
        redundant = tracker.find_redundant_modules()
        if redundant:
            print("Potentially redundant modules:")
            for m in redundant:
                stats = tracker.modules[m]
                print(f"  {m}: {stats.avg_savings_pct:.2f}% avg savings")
        else:
            print("No redundant modules detected (or insufficient data).")
        sys.exit(0)
    
    parser.print_help()
