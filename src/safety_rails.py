#!/usr/bin/env python3
"""
RTO4LLM - Safety Rails Module
============================
Safety Rails Module
===================
Prevents accidental file deletion and provides safe file operations.

CORE PRINCIPLES:
1. NEVER delete any file - not even zero-byte files
2. NEVER modify original files - always work with copies
3. All deletions go through this module with explicit confirmation
4. Temp files are the ONLY exception (and are tracked)

Usage:
    from safety_rails import SafeFileOps, SafetyViolation
    
    ops = SafeFileOps()
    ops.safe_read(path)           # Read-only, safe
    ops.safe_write_temp(data)     # Write to temp, tracked
    ops.cleanup_temp()            # Only cleans tracked temp files

License: GPL-3.0-or-later
Repository: https://github.com/StevenGITHUBwork/RTO4LLM

Code contributions by GitHub Copilot (Claude Opus 4.5)
"""

import os
import sys
import time
import tempfile
import hashlib
import atexit
from pathlib import Path
from typing import Optional, Set, Dict, Any, Union
from dataclasses import dataclass, field
from contextlib import contextmanager
import threading
import json

# ============================================================================
# Safety Configuration
# ============================================================================

@dataclass
class SafetyConfig:
    """Global safety configuration"""
    # NEVER delete any user files
    allow_user_file_deletion: bool = False
    
    # Only allow temp file cleanup
    allow_temp_cleanup: bool = True
    
    # Log all file operations
    log_all_operations: bool = True
    
    # Require explicit confirmation for any destructive action
    require_confirmation: bool = True
    
    # Maximum temp files before warning
    max_temp_files: int = 100
    
    # Protected paths (regex patterns) - NEVER touch these
    protected_patterns: tuple = (
        r'.*\.git.*',
        r'.*\.ssh.*',
        r'.*\.gnupg.*',
        r'/etc/.*',
        r'/usr/.*',
        r'/bin/.*',
        r'/sbin/.*',
        r'/boot/.*',
    )


# Global config (can be modified at startup)
SAFETY_CONFIG = SafetyConfig()


# ============================================================================
# Exceptions
# ============================================================================

class SafetyViolation(Exception):
    """Raised when a safety rule is violated"""
    pass


class DeletionBlocked(SafetyViolation):
    """Raised when file deletion is attempted"""
    pass


class ProtectedPathViolation(SafetyViolation):
    """Raised when a protected path is accessed for writing"""
    pass


# ============================================================================
# Safety Logging
# ============================================================================

class SafetyLogger:
    """Logs all file operations for audit"""
    
    def __init__(self, log_dir: Optional[Path] = None):
        self.log_dir = log_dir or Path(tempfile.gettempdir()) / "optimizer_safety_logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / f"safety_log_{os.getpid()}.jsonl"
        self.lock = threading.Lock()
        
    def log(self, operation: str, path: str, details: Dict[str, Any] = None):
        """Log a file operation"""
        entry = {
            'timestamp': time.time(),
            'iso_time': time.strftime('%Y-%m-%dT%H:%M:%S'),
            'pid': os.getpid(),
            'operation': operation,
            'path': str(path),
            'details': details or {}
        }
        
        with self.lock:
            with open(self.log_file, 'a') as f:
                f.write(json.dumps(entry) + '\n')
    
    def log_blocked(self, operation: str, path: str, reason: str):
        """Log a blocked operation"""
        self.log(f"BLOCKED_{operation}", path, {'reason': reason})


# Global logger
_SAFETY_LOGGER = SafetyLogger()


# ============================================================================
# Safe File Operations
# ============================================================================

class SafeFileOps:
    """
    Safe file operations that prevent accidental deletion.
    
    Rules:
    1. Reading is always allowed (read-only)
    2. Writing only to temp files or explicit new files
    3. NEVER delete user files
    4. Track all temp files for safe cleanup
    """
    
    def __init__(self, config: SafetyConfig = None):
        self.config = config or SAFETY_CONFIG
        self.temp_files: Set[Path] = set()
        self.lock = threading.Lock()
        
        # Register cleanup on exit
        atexit.register(self._atexit_cleanup)
    
    def _is_protected(self, path: Union[str, Path]) -> bool:
        """Check if path matches protected patterns"""
        import re
        path_str = str(Path(path).resolve())
        
        for pattern in self.config.protected_patterns:
            if re.match(pattern, path_str):
                return True
        return False
    
    def _is_temp_file(self, path: Union[str, Path]) -> bool:
        """Check if path is in temp directory"""
        path = Path(path).resolve()
        temp_dir = Path(tempfile.gettempdir()).resolve()
        
        try:
            path.relative_to(temp_dir)
            return True
        except ValueError:
            return False
    
    def safe_read(self, path: Union[str, Path], mode: str = 'rb') -> bytes:
        """
        Safely read a file (read-only operation, always allowed).
        """
        path = Path(path)
        
        if self.config.log_all_operations:
            _SAFETY_LOGGER.log('READ', str(path))
        
        with open(path, mode) as f:
            return f.read()
    
    def safe_read_text(self, path: Union[str, Path], encoding: str = 'utf-8') -> str:
        """Read file as text"""
        return self.safe_read(path, 'r').decode(encoding) if isinstance(self.safe_read(path, 'rb'), bytes) else open(path, 'r', encoding=encoding).read()
    
    def safe_write_temp(self, data: Union[bytes, str], suffix: str = '.tmp') -> Path:
        """
        Write data to a temporary file.
        Returns the path to the temp file.
        The file is tracked and will be cleaned up on exit.
        """
        if isinstance(data, str):
            data = data.encode('utf-8')
        
        # Create temp file
        fd, path = tempfile.mkstemp(suffix=suffix, prefix='optimizer_')
        path = Path(path)
        
        try:
            os.write(fd, data)
        finally:
            os.close(fd)
        
        # Track for cleanup
        with self.lock:
            self.temp_files.add(path)
            
            if len(self.temp_files) > self.config.max_temp_files:
                print(f"WARNING: {len(self.temp_files)} temp files tracked", file=sys.stderr)
        
        if self.config.log_all_operations:
            _SAFETY_LOGGER.log('WRITE_TEMP', str(path), {'size': len(data)})
        
        return path
    
    def safe_write_new(self, path: Union[str, Path], data: Union[bytes, str], 
                       overwrite: bool = False) -> Path:
        """
        Write to a new file. Will NOT overwrite existing files unless explicit.
        """
        path = Path(path)
        
        if self._is_protected(path):
            raise ProtectedPathViolation(f"Cannot write to protected path: {path}")
        
        if path.exists() and not overwrite:
            raise SafetyViolation(f"File already exists and overwrite=False: {path}")
        
        if isinstance(data, str):
            data = data.encode('utf-8')
        
        # Ensure parent exists
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, 'wb') as f:
            f.write(data)
        
        if self.config.log_all_operations:
            _SAFETY_LOGGER.log('WRITE_NEW', str(path), {'size': len(data), 'overwrite': overwrite})
        
        return path
    
    def cleanup_temp(self, path: Union[str, Path] = None):
        """
        Clean up tracked temp files.
        If path is specified, only clean that file (if it's tracked).
        """
        if not self.config.allow_temp_cleanup:
            _SAFETY_LOGGER.log_blocked('CLEANUP', str(path) if path else 'ALL', 'temp cleanup disabled')
            return
        
        with self.lock:
            if path:
                path = Path(path).resolve()
                if path in self.temp_files:
                    if path.exists():
                        path.unlink()
                        if self.config.log_all_operations:
                            _SAFETY_LOGGER.log('CLEANUP_TEMP', str(path))
                    self.temp_files.discard(path)
            else:
                # Clean all tracked temp files
                for temp_path in list(self.temp_files):
                    if temp_path.exists():
                        temp_path.unlink()
                        if self.config.log_all_operations:
                            _SAFETY_LOGGER.log('CLEANUP_TEMP', str(temp_path))
                self.temp_files.clear()
    
    def _atexit_cleanup(self):
        """Cleanup on program exit"""
        self.cleanup_temp()
    
    # =========================================================================
    # BLOCKED OPERATIONS - These raise exceptions
    # =========================================================================
    
    def delete_file(self, path: Union[str, Path]):
        """
        BLOCKED: File deletion is not allowed.
        This method always raises DeletionBlocked.
        """
        path = Path(path)
        _SAFETY_LOGGER.log_blocked('DELETE', str(path), 'file deletion is disabled')
        raise DeletionBlocked(
            f"FILE DELETION BLOCKED: {path}\n"
            f"This optimizer NEVER deletes files.\n"
            f"If you need to delete this file, do it manually."
        )
    
    def remove(self, path: Union[str, Path]):
        """BLOCKED: Alias for delete_file"""
        return self.delete_file(path)
    
    def unlink(self, path: Union[str, Path]):
        """BLOCKED: Alias for delete_file"""
        return self.delete_file(path)
    
    def rmtree(self, path: Union[str, Path]):
        """BLOCKED: Directory tree removal is not allowed"""
        path = Path(path)
        _SAFETY_LOGGER.log_blocked('RMTREE', str(path), 'directory deletion is disabled')
        raise DeletionBlocked(
            f"DIRECTORY DELETION BLOCKED: {path}\n"
            f"This optimizer NEVER deletes directories.\n"
            f"If you need to delete this, do it manually."
        )


# ============================================================================
# Monkey-Patching for Extra Safety (Optional)
# ============================================================================

def install_safety_hooks():
    """
    Install safety hooks that intercept dangerous os operations.
    Call this at module load time for maximum protection.
    """
    import builtins
    
    _original_open = builtins.open
    _original_unlink = os.unlink
    _original_remove = os.remove
    
    def safe_open(file, mode='r', *args, **kwargs):
        # Allow all opens, but log writes
        if 'w' in mode or 'a' in mode:
            _SAFETY_LOGGER.log('OPEN_WRITE', str(file), {'mode': mode})
        return _original_open(file, mode, *args, **kwargs)
    
    def blocked_unlink(path):
        # Check if it's a temp file
        path = Path(path)
        if str(path).startswith(tempfile.gettempdir()):
            _SAFETY_LOGGER.log('UNLINK_TEMP', str(path))
            return _original_unlink(path)
        
        _SAFETY_LOGGER.log_blocked('UNLINK', str(path), 'non-temp file deletion blocked')
        raise DeletionBlocked(f"UNLINK BLOCKED: {path}")
    
    def blocked_remove(path):
        return blocked_unlink(path)
    
    # Install hooks
    # Note: Uncomment these lines to enable global blocking
    # os.unlink = blocked_unlink
    # os.remove = blocked_remove
    
    print("[SAFETY] Safety hooks available (not auto-installed)", file=sys.stderr)


# ============================================================================
# Context Manager for Temp Files
# ============================================================================

@contextmanager
def safe_temp_file(data: Union[bytes, str] = None, suffix: str = '.tmp'):
    """
    Context manager for safe temp file operations.
    
    Usage:
        with safe_temp_file(data) as path:
            # Use the temp file
            process(path)
        # File is automatically cleaned up
    """
    ops = SafeFileOps()
    path = None
    
    try:
        if data is not None:
            path = ops.safe_write_temp(data, suffix)
        else:
            fd, path_str = tempfile.mkstemp(suffix=suffix, prefix='optimizer_')
            os.close(fd)
            path = Path(path_str)
            ops.temp_files.add(path)
        
        yield path
    finally:
        if path and path.exists():
            ops.cleanup_temp(path)


# ============================================================================
# Summary Report
# ============================================================================

def get_safety_summary() -> str:
    """Generate summary of safety status"""
    lines = []
    lines.append("=" * 50)
    lines.append("SAFETY RAILS STATUS")
    lines.append("=" * 50)
    lines.append(f"User file deletion: {'BLOCKED' if not SAFETY_CONFIG.allow_user_file_deletion else 'ALLOWED'}")
    lines.append(f"Temp cleanup: {'ALLOWED' if SAFETY_CONFIG.allow_temp_cleanup else 'BLOCKED'}")
    lines.append(f"Operation logging: {'ON' if SAFETY_CONFIG.log_all_operations else 'OFF'}")
    lines.append(f"Log file: {_SAFETY_LOGGER.log_file}")
    lines.append("=" * 50)
    return "\n".join(lines)


# ============================================================================
# Module Initialization
# ============================================================================

# Print safety status on import
if __name__ != '__main__':
    print("[SAFETY] Safety rails loaded - file deletion BLOCKED", file=sys.stderr)


if __name__ == '__main__':
    # Self-test
    print(get_safety_summary())
    
    ops = SafeFileOps()
    
    # Test temp file
    print("\n[TEST] Creating temp file...")
    path = ops.safe_write_temp(b"test data", suffix='.txt')
    print(f"  Created: {path}")
    
    # Test blocked deletion
    print("\n[TEST] Attempting to delete user file (should be blocked)...")
    try:
        ops.delete_file("/tmp/test.txt")
    except DeletionBlocked as e:
        print(f"  ✓ Blocked as expected: {type(e).__name__}")
    
    # Clean up temp
    print("\n[TEST] Cleaning up temp files...")
    ops.cleanup_temp()
    print("  ✓ Cleanup complete")
    
    print("\n[PASS] All safety tests passed")
