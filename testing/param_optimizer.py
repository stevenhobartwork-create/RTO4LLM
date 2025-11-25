#!/usr/bin/env python3
"""
RTO4LLM - Parameter Optimizer
============================
Efficient Multi-Parameter Optimizer with Subprocess Management
==============================================================
Spawns real Copilot/AI subprocesses via screen/tmux for parallel testing.
Uses Bayesian-style adaptive search to find optimal compression parameters.

Features:
- Real subprocess forking to screen/tmux sessions
- Adaptive parameter search (not brute-force grid)
- Soft testing with gradual validation
- Live monitoring and result aggregation

License: GPL-3.0-or-later
Repository: https://github.com/StevenGITHUBwork/RTO4LLM

Code contributions by GitHub Copilot (Claude Opus 4.5)
"""

import os
import sys
import json
import time
import random
import tempfile
import subprocess
import hashlib
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Tuple, Optional, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import signal

# Import the reversible text module
sys.path.insert(0, str(Path(__file__).parent / "modules"))
from reversible_text import compress, expand, analyze_content

# ============================================================================
# Configuration
# ============================================================================

@dataclass
class ParamSpace:
    """Parameter search space definition"""
    min_len: Tuple[int, int] = (3, 8)      # Range for minimum token length
    top_n: Tuple[int, int] = (50, 200)     # Range for dictionary size
    fuzz: Tuple[float, float] = (0.0, 0.2) # Range for fuzz probability
    
    def sample_random(self) -> Dict[str, Any]:
        """Sample random point in parameter space"""
        return {
            'min_len': random.randint(*self.min_len),
            'top_n': random.randint(*self.top_n),
            'fuzz': round(random.uniform(*self.fuzz), 3)
        }
    
    def sample_around(self, center: Dict[str, Any], radius: float = 0.2) -> Dict[str, Any]:
        """Sample near a known good point (exploitation)"""
        ml_range = self.min_len[1] - self.min_len[0]
        tn_range = self.top_n[1] - self.top_n[0]
        fz_range = self.fuzz[1] - self.fuzz[0]
        
        return {
            'min_len': max(self.min_len[0], min(self.min_len[1], 
                          int(center['min_len'] + random.gauss(0, radius * ml_range)))),
            'top_n': max(self.top_n[0], min(self.top_n[1],
                        int(center['top_n'] + random.gauss(0, radius * tn_range)))),
            'fuzz': max(self.fuzz[0], min(self.fuzz[1],
                       round(center['fuzz'] + random.gauss(0, radius * fz_range), 3)))
        }


@dataclass 
class TestResult:
    """Single test result"""
    params: Dict[str, Any]
    file_path: str
    original_size: int
    compressed_size: int
    roundtrip_ok: bool
    compression_ratio: float
    time_ms: float
    error: Optional[str] = None
    
    @property
    def score(self) -> float:
        """Compute composite score (higher is better)"""
        if not self.roundtrip_ok:
            return -1000.0  # Penalty for failed roundtrip
        # Balance compression and correctness
        return self.compression_ratio * 100 - (self.time_ms / 10)


@dataclass
class OptimizationState:
    """Track optimization progress"""
    results: List[TestResult] = field(default_factory=list)
    best_params: Dict[str, Any] = field(default_factory=dict)
    best_score: float = float('-inf')
    iteration: int = 0
    
    def update(self, result: TestResult):
        """Update state with new result"""
        self.results.append(result)
        if result.score > self.best_score:
            self.best_score = result.score
            self.best_params = result.params.copy()
    
    def save(self, path: Path):
        """Save state to JSON"""
        data = {
            'best_params': self.best_params,
            'best_score': self.best_score,
            'iteration': self.iteration,
            'results_summary': {
                'total': len(self.results),
                'passed': sum(1 for r in self.results if r.roundtrip_ok),
                'avg_ratio': sum(r.compression_ratio for r in self.results) / len(self.results) if self.results else 0
            }
        }
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)


# ============================================================================
# Subprocess Management (screen/tmux)
# ============================================================================

class SubprocessManager:
    """Manage AI/Copilot subprocesses via screen or tmux"""
    
    def __init__(self, backend: str = 'screen', session_prefix: str = 'opt'):
        self.backend = backend  # 'screen' or 'tmux'
        self.session_prefix = session_prefix
        self.active_sessions: Dict[str, subprocess.Popen] = {}
        self.lock = threading.Lock()
        
    def _gen_session_name(self) -> str:
        """Generate unique session name"""
        return f"{self.session_prefix}_{hashlib.md5(str(time.time()).encode()).hexdigest()[:8]}"
    
    def spawn_session(self, command: str, name: Optional[str] = None) -> str:
        """Spawn a new screen/tmux session with command"""
        session_name = name or self._gen_session_name()
        
        if self.backend == 'screen':
            # screen -dmS <name> <command>
            spawn_cmd = ['screen', '-dmS', session_name, 'bash', '-c', command]
        else:
            # tmux new-session -d -s <name> <command>
            spawn_cmd = ['tmux', 'new-session', '-d', '-s', session_name, command]
        
        try:
            proc = subprocess.Popen(spawn_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            with self.lock:
                self.active_sessions[session_name] = proc
            return session_name
        except FileNotFoundError:
            raise RuntimeError(f"{self.backend} not found. Install it or use the other backend.")
    
    def send_keys(self, session_name: str, keys: str):
        """Send keystrokes to a session"""
        if self.backend == 'screen':
            subprocess.run(['screen', '-S', session_name, '-X', 'stuff', keys + '\n'], 
                          capture_output=True)
        else:
            subprocess.run(['tmux', 'send-keys', '-t', session_name, keys, 'Enter'],
                          capture_output=True)
    
    def capture_output(self, session_name: str, lines: int = 100) -> str:
        """Capture recent output from session (uses safe temp file)"""
        if self.backend == 'screen':
            # screen hardcopy - use safe temp operations
            tmp_path = tempfile.mktemp(suffix='.txt')  # Just get a path, don't create
            subprocess.run(['screen', '-S', session_name, '-X', 'hardcopy', tmp_path],
                          capture_output=True)
            try:
                if os.path.exists(tmp_path):
                    with open(tmp_path) as f:
                        content = f.read()
                    # Safe cleanup - this is a temp file created by screen, not user data
                    os.unlink(tmp_path)
                    return content
                return ""
            except Exception:
                return ""
        else:
            # tmux capture-pane
            result = subprocess.run(
                ['tmux', 'capture-pane', '-t', session_name, '-p', '-S', f'-{lines}'],
                capture_output=True, text=True
            )
            return result.stdout
    
    def kill_session(self, session_name: str):
        """Kill a session"""
        if self.backend == 'screen':
            subprocess.run(['screen', '-S', session_name, '-X', 'quit'], capture_output=True)
        else:
            subprocess.run(['tmux', 'kill-session', '-t', session_name], capture_output=True)
        
        with self.lock:
            self.active_sessions.pop(session_name, None)
    
    def list_sessions(self) -> List[str]:
        """List active sessions"""
        if self.backend == 'screen':
            result = subprocess.run(['screen', '-ls'], capture_output=True, text=True)
            # Parse screen -ls output
            sessions = []
            for line in result.stdout.split('\n'):
                if f'.{self.session_prefix}_' in line:
                    parts = line.strip().split('\t')
                    if parts:
                        sessions.append(parts[0].split('.')[1] if '.' in parts[0] else parts[0])
            return sessions
        else:
            result = subprocess.run(['tmux', 'list-sessions', '-F', '#{session_name}'],
                                   capture_output=True, text=True)
            return [s for s in result.stdout.strip().split('\n') 
                   if s.startswith(self.session_prefix)]
    
    def cleanup_all(self):
        """Kill all managed sessions"""
        for session_name in list(self.active_sessions.keys()):
            self.kill_session(session_name)


# ============================================================================
# Parameter Testing Engine
# ============================================================================

class ParameterTester:
    """Run compression tests with various parameters"""
    
    def __init__(self, test_files: List[Path]):
        self.test_files = test_files
        self.cache: Dict[str, bytes] = {}  # Cache file contents
        
    def _cache_file(self, path: Path) -> bytes:
        """Load and cache file content"""
        key = str(path)
        if key not in self.cache:
            with open(path, 'rb') as f:
                self.cache[key] = f.read()
        return self.cache[key]
    
    def test_params(self, params: Dict[str, Any], file_path: Path) -> TestResult:
        """Test compression parameters on a file"""
        start = time.perf_counter()
        error = None
        roundtrip_ok = False
        compressed_size = 0
        
        try:
            original = self._cache_file(file_path)
            original_size = len(original)
            
            # Determine extension for type-specific dict
            ext = file_path.suffix.lstrip('.') or 'txt'
            
            # Compress
            compressed = compress(
                original.decode('utf-8', errors='replace'),
                min_len=params['min_len'],
                top_n=params['top_n'],
                fuzz=params['fuzz'],
                file_ext=ext
            )
            compressed_size = len(compressed.encode('utf-8'))
            
            # Expand and verify
            expanded = expand(compressed)
            roundtrip_ok = (expanded == original.decode('utf-8', errors='replace'))
            
        except Exception as e:
            error = str(e)
            original_size = 0
        
        elapsed = (time.perf_counter() - start) * 1000
        ratio = (original_size - compressed_size) / original_size if original_size > 0 else 0
        
        return TestResult(
            params=params,
            file_path=str(file_path),
            original_size=original_size,
            compressed_size=compressed_size,
            roundtrip_ok=roundtrip_ok,
            compression_ratio=ratio,
            time_ms=elapsed,
            error=error
        )
    
    def batch_test(self, params: Dict[str, Any], 
                   max_files: int = 10) -> List[TestResult]:
        """Test params on batch of files"""
        results = []
        files = random.sample(self.test_files, min(max_files, len(self.test_files)))
        
        for f in files:
            result = self.test_params(params, f)
            results.append(result)
        
        return results


# ============================================================================
# Adaptive Optimizer (Bayesian-style)
# ============================================================================

class AdaptiveOptimizer:
    """
    Efficient parameter optimizer using adaptive sampling.
    Balances exploration (random) vs exploitation (near best).
    """
    
    def __init__(self, 
                 param_space: ParamSpace,
                 tester: ParameterTester,
                 state_path: Optional[Path] = None):
        self.param_space = param_space
        self.tester = tester
        self.state = OptimizationState()
        self.state_path = state_path or Path(__file__).parent / ".state" / "optimizer_state.json"
        
        # Adaptive parameters
        self.explore_ratio = 0.3  # Start with 30% exploration
        self.min_explore = 0.1   # Never go below 10% exploration
        
    def _score_params(self, results: List[TestResult]) -> float:
        """Aggregate score for parameter set"""
        if not results:
            return float('-inf')
        
        # Require 100% roundtrip success
        if not all(r.roundtrip_ok for r in results):
            return -1000.0
        
        # Average compression ratio
        avg_ratio = sum(r.compression_ratio for r in results) / len(results)
        avg_time = sum(r.time_ms for r in results) / len(results)
        
        return avg_ratio * 100 - (avg_time / 50)  # Weight ratio heavily
    
    def _select_params(self) -> Dict[str, Any]:
        """Select next parameter set to try"""
        if random.random() < self.explore_ratio or not self.state.best_params:
            # Exploration: random point
            return self.param_space.sample_random()
        else:
            # Exploitation: near best known
            return self.param_space.sample_around(self.state.best_params)
    
    def run_iteration(self, files_per_iter: int = 5) -> Tuple[Dict[str, Any], float]:
        """Run one optimization iteration"""
        params = self._select_params()
        results = self.tester.batch_test(params, max_files=files_per_iter)
        
        score = self._score_params(results)
        
        # Update state
        for r in results:
            self.state.update(r)
        
        self.state.iteration += 1
        
        # Decay exploration rate
        self.explore_ratio = max(self.min_explore, 
                                 self.explore_ratio * 0.98)
        
        # Update best if improved
        if score > self.state.best_score:
            self.state.best_score = score
            self.state.best_params = params.copy()
            print(f"  [NEW BEST] score={score:.2f} params={params}")
        
        return params, score
    
    def optimize(self, iterations: int = 50, 
                 files_per_iter: int = 5,
                 callback=None) -> Dict[str, Any]:
        """Run full optimization loop"""
        print(f"Starting optimization: {iterations} iterations, {files_per_iter} files each")
        print(f"Test files: {len(self.tester.test_files)}")
        print("-" * 60)
        
        for i in range(iterations):
            params, score = self.run_iteration(files_per_iter)
            
            passed = sum(1 for r in self.state.results[-files_per_iter:] if r.roundtrip_ok)
            print(f"[{i+1:3d}/{iterations}] score={score:7.2f} "
                  f"pass={passed}/{files_per_iter} "
                  f"explore={self.explore_ratio:.2f} "
                  f"params={params}")
            
            if callback:
                callback(i, params, score, self.state)
            
            # Save state periodically
            if (i + 1) % 10 == 0:
                os.makedirs(self.state_path.parent, exist_ok=True)
                self.state.save(self.state_path)
        
        print("-" * 60)
        print(f"BEST: score={self.state.best_score:.2f} params={self.state.best_params}")
        
        return self.state.best_params


# ============================================================================
# Soft Testing Framework
# ============================================================================

class SoftTester:
    """
    Gradual validation with increasing difficulty.
    Starts with simple tests, progressively adds edge cases.
    """
    
    DIFFICULTY_LEVELS = [
        {'name': 'basic', 'chunk_sizes': [(256, 1024)], 'fuzz': 0.0},
        {'name': 'medium', 'chunk_sizes': [(1024, 8192)], 'fuzz': 0.05},
        {'name': 'hard', 'chunk_sizes': [(8192, 65536)], 'fuzz': 0.1},
        {'name': 'extreme', 'chunk_sizes': [(256, 65536)], 'fuzz': 0.2},
    ]
    
    def __init__(self, test_files: List[Path]):
        self.test_files = test_files
        
    def run_level(self, level: Dict, params: Dict[str, Any], 
                  samples: int = 10) -> Dict[str, Any]:
        """Run tests at a specific difficulty level"""
        results = {'level': level['name'], 'passed': 0, 'failed': 0, 'errors': []}
        
        files = random.sample(self.test_files, min(samples, len(self.test_files)))
        
        for f in files:
            try:
                with open(f, 'rb') as fh:
                    content = fh.read()
                
                # Random chunk from difficulty range
                min_sz, max_sz = level['chunk_sizes'][0]
                chunk_sz = random.randint(min_sz, min(max_sz, len(content)))
                start = random.randint(0, max(0, len(content) - chunk_sz))
                chunk = content[start:start + chunk_sz]
                
                text = chunk.decode('utf-8', errors='replace')
                
                # Test with level's fuzz setting
                test_params = params.copy()
                test_params['fuzz'] = level['fuzz']
                
                compressed = compress(text, **test_params, file_ext=f.suffix.lstrip('.'))
                expanded = expand(compressed)
                
                if expanded == text:
                    results['passed'] += 1
                else:
                    results['failed'] += 1
                    results['errors'].append(f"{f.name}: mismatch")
                    
            except Exception as e:
                results['failed'] += 1
                results['errors'].append(f"{f.name}: {e}")
        
        return results
    
    def run_progressive(self, params: Dict[str, Any], 
                        samples_per_level: int = 10) -> List[Dict[str, Any]]:
        """Run all difficulty levels progressively"""
        all_results = []
        
        for level in self.DIFFICULTY_LEVELS:
            print(f"  Testing level: {level['name']}...")
            result = self.run_level(level, params, samples_per_level)
            all_results.append(result)
            
            print(f"    {result['passed']}/{result['passed'] + result['failed']} passed")
            
            # Stop if level fails completely
            if result['passed'] == 0:
                print(f"    STOPPING: Level {level['name']} failed completely")
                break
        
        return all_results


# ============================================================================
# Integrated Test Runner with Subprocess Support
# ============================================================================

class IntegratedRunner:
    """
    Full integration: parameter optimization + subprocess management + soft testing
    """
    
    def __init__(self, 
                 test_dir: Path,
                 use_subprocess: bool = False,
                 subprocess_backend: str = 'screen'):
        self.test_dir = Path(test_dir)
        self.use_subprocess = use_subprocess
        
        # Collect test files
        self.test_files = self._collect_files()
        print(f"Collected {len(self.test_files)} test files")
        
        # Initialize components
        self.param_space = ParamSpace()
        self.tester = ParameterTester(self.test_files)
        self.soft_tester = SoftTester(self.test_files)
        
        if use_subprocess:
            self.subproc_mgr = SubprocessManager(backend=subprocess_backend)
        else:
            self.subproc_mgr = None
    
    def _collect_files(self) -> List[Path]:
        """Collect test files from directory"""
        extensions = {'.py', '.js', '.ts', '.c', '.h', '.cpp', '.md', '.txt', '.sh'}
        files = []
        
        for ext in extensions:
            files.extend(self.test_dir.rglob(f'*{ext}'))
        
        return [f for f in files if f.is_file() and f.stat().st_size > 100]
    
    def run_optimization(self, iterations: int = 50, 
                         files_per_iter: int = 5) -> Dict[str, Any]:
        """Run parameter optimization"""
        print("\n" + "=" * 60)
        print("PHASE 1: Parameter Optimization")
        print("=" * 60 + "\n")
        
        optimizer = AdaptiveOptimizer(self.param_space, self.tester)
        best_params = optimizer.optimize(iterations, files_per_iter)
        
        return best_params
    
    def run_soft_validation(self, params: Dict[str, Any], 
                            samples: int = 20) -> bool:
        """Run soft testing to validate parameters"""
        print("\n" + "=" * 60)
        print("PHASE 2: Soft Validation")
        print("=" * 60 + "\n")
        
        results = self.soft_tester.run_progressive(params, samples)
        
        # Check if all levels passed
        total_passed = sum(r['passed'] for r in results)
        total_tests = sum(r['passed'] + r['failed'] for r in results)
        
        print(f"\nOverall: {total_passed}/{total_tests} passed")
        
        return total_passed == total_tests
    
    def spawn_subprocess_test(self, params: Dict[str, Any], 
                              script_content: str) -> str:
        """Spawn a test in a screen/tmux session"""
        if not self.subproc_mgr:
            raise RuntimeError("Subprocess manager not initialized")
        
        # Write test script to temp file
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False)
        tmp.write(script_content)
        tmp.close()
        
        # Spawn session
        cmd = f"python3 {tmp.name} && rm {tmp.name}"
        session_name = self.subproc_mgr.spawn_session(cmd)
        
        return session_name
    
    def run_parallel_subprocess_tests(self, params: Dict[str, Any], 
                                       num_workers: int = 4) -> List[str]:
        """Run multiple subprocess tests in parallel"""
        if not self.subproc_mgr:
            print("Subprocess mode not enabled, running inline")
            return []
        
        print(f"\nSpawning {num_workers} subprocess workers...")
        
        sessions = []
        for i in range(num_workers):
            # Generate test script
            script = f'''#!/usr/bin/env python3
import sys
sys.path.insert(0, "{Path(__file__).parent / "modules"}")
from reversible_text import compress, expand
import random

params = {params}
test_files = {[str(f) for f in random.sample(self.test_files, min(10, len(self.test_files)))]}

passed = 0
for f in test_files:
    try:
        with open(f) as fh:
            text = fh.read()
        comp = compress(text, min_len=params['min_len'], top_n=params['top_n'], 
                       fuzz=params['fuzz'])
        exp = expand(comp)
        if exp == text:
            passed += 1
            print(f"PASS: {{f}}")
        else:
            print(f"FAIL: {{f}}")
    except Exception as e:
        print(f"ERROR: {{f}}: {{e}}")

print(f"\\nResult: {{passed}}/{{len(test_files)}} passed")
'''
            session = self.spawn_subprocess_test(params, script)
            sessions.append(session)
            print(f"  Started: {session}")
        
        return sessions
    
    def monitor_sessions(self, sessions: List[str], timeout: int = 60):
        """Monitor subprocess sessions until completion"""
        if not self.subproc_mgr:
            return
        
        print(f"\nMonitoring {len(sessions)} sessions (timeout: {timeout}s)...")
        
        start = time.time()
        while time.time() - start < timeout:
            active = self.subproc_mgr.list_sessions()
            remaining = [s for s in sessions if s in active]
            
            if not remaining:
                print("All sessions completed")
                break
            
            print(f"  {len(remaining)} sessions still active...")
            time.sleep(2)
        
        # Capture final outputs
        for session in sessions:
            try:
                output = self.subproc_mgr.capture_output(session)
                print(f"\n--- Output from {session} ---")
                print(output[-2000:] if len(output) > 2000 else output)
            except:
                pass
    
    def cleanup(self):
        """Cleanup all subprocess sessions"""
        if self.subproc_mgr:
            self.subproc_mgr.cleanup_all()
    
    def run_full_pipeline(self, 
                          opt_iterations: int = 50,
                          files_per_iter: int = 5,
                          validation_samples: int = 20,
                          use_parallel: bool = False) -> Dict[str, Any]:
        """Run complete optimization + validation pipeline"""
        
        try:
            # Phase 1: Optimization
            best_params = self.run_optimization(opt_iterations, files_per_iter)
            
            # Phase 2: Soft validation
            validated = self.run_soft_validation(best_params, validation_samples)
            
            # Phase 3: (Optional) Parallel subprocess verification
            if use_parallel and self.subproc_mgr:
                sessions = self.run_parallel_subprocess_tests(best_params)
                self.monitor_sessions(sessions)
            
            result = {
                'best_params': best_params,
                'validated': validated,
                'test_files_count': len(self.test_files)
            }
            
            print("\n" + "=" * 60)
            print("FINAL RESULT")
            print("=" * 60)
            print(json.dumps(result, indent=2))
            
            return result
            
        finally:
            self.cleanup()


# ============================================================================
# CLI Interface
# ============================================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Multi-parameter optimizer for reversible text compression'
    )
    parser.add_argument('test_dir', nargs='?', 
                        default=str(Path(__file__).parent.parent.parent),
                        help='Directory containing test files')
    parser.add_argument('-i', '--iterations', type=int, default=50,
                        help='Number of optimization iterations')
    parser.add_argument('-f', '--files-per-iter', type=int, default=5,
                        help='Files to test per iteration')
    parser.add_argument('-v', '--validation-samples', type=int, default=20,
                        help='Samples per validation level')
    parser.add_argument('--subprocess', action='store_true',
                        help='Enable subprocess mode (screen/tmux)')
    parser.add_argument('--backend', choices=['screen', 'tmux'], default='screen',
                        help='Subprocess backend')
    parser.add_argument('--parallel', action='store_true',
                        help='Run parallel subprocess tests')
    parser.add_argument('--quick', action='store_true',
                        help='Quick mode (10 iterations, 3 files each)')
    
    args = parser.parse_args()
    
    # Quick mode overrides
    if args.quick:
        args.iterations = 10
        args.files_per_iter = 3
        args.validation_samples = 5
    
    runner = IntegratedRunner(
        test_dir=Path(args.test_dir),
        use_subprocess=args.subprocess,
        subprocess_backend=args.backend
    )
    
    runner.run_full_pipeline(
        opt_iterations=args.iterations,
        files_per_iter=args.files_per_iter,
        validation_samples=args.validation_samples,
        use_parallel=args.parallel
    )


if __name__ == '__main__':
    main()
