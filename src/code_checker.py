#!/usr/bin/env python3
"""
RTO4LLM - Code Quality Checker
=============================
Code Quality Checker Module
===========================
Checks for syntax errors and permission issues before/after compression.
Outputs compact alerts for AI consumption.

Features:
- Python syntax checking (ast.parse)
- Bash syntax checking (bash -n)
- JavaScript syntax checking (node --check)
- File permission verification
- Compact alert format for token efficiency

License: GPL-3.0-or-later
Repository: https://github.com/StevenGITHUBwork/RTO4LLM

Code contributions by GitHub Copilot (Claude Opus 4.5)
"""

import os
import sys
import ast
import subprocess
import stat
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

# ============================================================================
# Alert Formatting
# ============================================================================

MAX_ALERT_LENGTH = 200  # Max chars for compact alert

@dataclass
class Alert:
    """Compact alert for AI"""
    level: str      # ERROR, WARN, INFO
    checker: str    # Which checker found it
    message: str    # What was found
    location: str   # Where (file:line or just file)
    
    def compact(self) -> str:
        """Format as compact single line"""
        loc = self.location[:30] if len(self.location) > 30 else self.location
        msg = self.message[:100] if len(self.message) > 100 else self.message
        return f"[{self.level}:{self.checker}] {loc}: {msg}"
    
    def __str__(self):
        return self.compact()


def format_alerts(alerts: List[Alert], max_total: int = 500) -> str:
    """Format multiple alerts, truncating if too long"""
    if not alerts:
        return ""
    
    lines = [a.compact() for a in alerts]
    result = "\n".join(lines)
    
    if len(result) > max_total:
        # Truncate and add summary
        count = len(alerts)
        result = result[:max_total-50] + f"\n... [{count} total alerts, truncated]"
    
    return result


# ============================================================================
# Syntax Checkers
# ============================================================================

def check_python_syntax(code: str, filename: str = "<string>") -> List[Alert]:
    """Check Python syntax using ast.parse"""
    alerts = []
    
    try:
        ast.parse(code, filename=filename)
    except SyntaxError as e:
        alerts.append(Alert(
            level="ERROR",
            checker="py_ast",
            message=f"{e.msg}",
            location=f"{filename}:{e.lineno}" if e.lineno else filename
        ))
    except Exception as e:
        alerts.append(Alert(
            level="ERROR",
            checker="py_ast",
            message=str(e)[:80],
            location=filename
        ))
    
    return alerts


def check_bash_syntax(code: str, filename: str = "<string>") -> List[Alert]:
    """Check Bash syntax using bash -n"""
    alerts = []
    
    try:
        result = subprocess.run(
            ['bash', '-n'],
            input=code.encode('utf-8'),
            capture_output=True,
            timeout=5
        )
        
        if result.returncode != 0:
            stderr = result.stderr.decode('utf-8', errors='replace')
            # Extract first error line
            for line in stderr.split('\n'):
                if 'syntax error' in line.lower() or 'error' in line.lower():
                    alerts.append(Alert(
                        level="ERROR",
                        checker="bash_n",
                        message=line[:80],
                        location=filename
                    ))
                    break
            else:
                # Generic error
                alerts.append(Alert(
                    level="ERROR",
                    checker="bash_n",
                    message=stderr[:80],
                    location=filename
                ))
    except subprocess.TimeoutExpired:
        alerts.append(Alert(
            level="WARN",
            checker="bash_n",
            message="Syntax check timed out",
            location=filename
        ))
    except FileNotFoundError:
        pass  # bash not available, skip
    except Exception as e:
        alerts.append(Alert(
            level="WARN",
            checker="bash_n",
            message=str(e)[:50],
            location=filename
        ))
    
    return alerts


def check_js_syntax(code: str, filename: str = "<string>") -> List[Alert]:
    """Check JavaScript syntax using node --check"""
    alerts = []
    
    try:
        # Write to temp file for node check
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
            f.write(code)
            tmp_path = f.name
        
        try:
            result = subprocess.run(
                ['node', '--check', tmp_path],
                capture_output=True,
                timeout=5
            )
            
            if result.returncode != 0:
                stderr = result.stderr.decode('utf-8', errors='replace')
                # Extract first error
                for line in stderr.split('\n'):
                    if 'SyntaxError' in line or 'error' in line.lower():
                        alerts.append(Alert(
                            level="ERROR",
                            checker="node_chk",
                            message=line[:80],
                            location=filename
                        ))
                        break
        finally:
            os.unlink(tmp_path)
            
    except FileNotFoundError:
        pass  # node not available, skip
    except Exception as e:
        pass  # Silently skip if node unavailable
    
    return alerts


def check_json_syntax(code: str, filename: str = "<string>") -> List[Alert]:
    """Check JSON syntax"""
    alerts = []
    import json
    
    try:
        json.loads(code)
    except json.JSONDecodeError as e:
        alerts.append(Alert(
            level="ERROR",
            checker="json",
            message=f"line {e.lineno}: {e.msg}",
            location=filename
        ))
    
    return alerts


# ============================================================================
# Permission Checker
# ============================================================================

def check_permissions(path: str) -> List[Alert]:
    """Check file permissions for common issues"""
    alerts = []
    
    try:
        st = os.stat(path)
        mode = st.st_mode
        
        # Check if readable
        if not os.access(path, os.R_OK):
            alerts.append(Alert(
                level="WARN",
                checker="perms",
                message="File not readable",
                location=path
            ))
        
        # Check if executable script has execute bit
        path_obj = Path(path)
        if path_obj.suffix in ('.sh', '.bash', '.py'):
            if not (mode & stat.S_IXUSR):
                alerts.append(Alert(
                    level="INFO",
                    checker="perms",
                    message="Script missing execute bit",
                    location=path
                ))
        
        # Check for world-writable
        if mode & stat.S_IWOTH:
            alerts.append(Alert(
                level="WARN",
                checker="perms",
                message="File is world-writable",
                location=path
            ))
        
        # Check for setuid/setgid
        if mode & (stat.S_ISUID | stat.S_ISGID):
            alerts.append(Alert(
                level="WARN",
                checker="perms",
                message="File has setuid/setgid bit",
                location=path
            ))
            
    except FileNotFoundError:
        pass  # File doesn't exist yet
    except PermissionError:
        alerts.append(Alert(
            level="ERROR",
            checker="perms",
            message="Permission denied reading file",
            location=path
        ))
    except Exception as e:
        alerts.append(Alert(
            level="WARN",
            checker="perms",
            message=str(e)[:50],
            location=path
        ))
    
    return alerts


# ============================================================================
# Main Checker Interface
# ============================================================================

def detect_language(code: str, filename: str = None) -> str:
    """Detect code language from content or filename"""
    if filename:
        ext = Path(filename).suffix.lower()
        ext_map = {
            '.py': 'python',
            '.sh': 'bash',
            '.bash': 'bash',
            '.js': 'javascript',
            '.ts': 'typescript',
            '.json': 'json',
            '.c': 'c',
            '.h': 'c',
            '.cpp': 'cpp',
            '.hpp': 'cpp',
        }
        if ext in ext_map:
            return ext_map[ext]
    
    # Content-based detection
    first_line = code.split('\n')[0] if code else ''
    
    if first_line.startswith('#!/usr/bin/env python') or first_line.startswith('#!/usr/bin/python'):
        return 'python'
    if first_line.startswith('#!/bin/bash') or first_line.startswith('#!/bin/sh'):
        return 'bash'
    if 'import ' in code[:500] and ('def ' in code[:1000] or 'class ' in code[:1000]):
        return 'python'
    if code.strip().startswith('{') and code.strip().endswith('}'):
        return 'json'
    
    return 'unknown'


def check_code(code: str, filename: str = None, check_perms: bool = True) -> Tuple[List[Alert], str]:
    """
    Main entry point: check code for syntax errors and permission issues.
    
    Returns:
        (alerts, compact_summary)
    """
    alerts = []
    
    # Permission check (if filename provided and exists)
    if check_perms and filename and os.path.exists(filename):
        alerts.extend(check_permissions(filename))
    
    # Language detection
    lang = detect_language(code, filename)
    
    # Syntax check based on language
    if lang == 'python':
        alerts.extend(check_python_syntax(code, filename or '<string>'))
    elif lang == 'bash':
        alerts.extend(check_bash_syntax(code, filename or '<string>'))
    elif lang == 'javascript' or lang == 'typescript':
        alerts.extend(check_js_syntax(code, filename or '<string>'))
    elif lang == 'json':
        alerts.extend(check_json_syntax(code, filename or '<string>'))
    
    # Generate compact summary
    if not alerts:
        summary = ""
    else:
        errors = [a for a in alerts if a.level == 'ERROR']
        warns = [a for a in alerts if a.level == 'WARN']
        
        if errors:
            summary = format_alerts(errors[:3], max_total=MAX_ALERT_LENGTH)
        elif warns:
            summary = format_alerts(warns[:2], max_total=MAX_ALERT_LENGTH)
        else:
            summary = format_alerts(alerts[:2], max_total=MAX_ALERT_LENGTH)
    
    return alerts, summary


def check_before_after(original: str, compressed: str, expanded: str, 
                       filename: str = None) -> Tuple[bool, str]:
    """
    Check that compression didn't introduce syntax errors.
    
    Returns:
        (is_ok, alert_summary)
    """
    # Check original for baseline
    orig_alerts, _ = check_code(original, filename, check_perms=False)
    orig_errors = [a for a in orig_alerts if a.level == 'ERROR']
    
    # Check expanded (after round-trip)
    exp_alerts, _ = check_code(expanded, filename, check_perms=False)
    exp_errors = [a for a in exp_alerts if a.level == 'ERROR']
    
    # If original had errors, that's not compression's fault
    if orig_errors:
        return True, ""  # Pass through existing errors
    
    # If expanded has NEW errors, that's a problem
    if exp_errors and not orig_errors:
        return False, f"[COMPRESSION_BROKE_SYNTAX] {format_alerts(exp_errors[:2], 150)}"
    
    return True, ""


# ============================================================================
# CLI
# ============================================================================

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Code Quality Checker')
    parser.add_argument('file', nargs='?', help='File to check (or stdin)')
    parser.add_argument('--lang', help='Force language detection')
    parser.add_argument('--no-perms', action='store_true', help='Skip permission checks')
    parser.add_argument('--compact', action='store_true', help='Output compact format only')
    
    args = parser.parse_args()
    
    # Read input
    if args.file:
        with open(args.file) as f:
            code = f.read()
        filename = args.file
    else:
        code = sys.stdin.read()
        filename = None
    
    # Run checks
    alerts, summary = check_code(code, filename, check_perms=not args.no_perms)
    
    # Output
    if args.compact:
        if summary:
            print(summary)
        else:
            print("[OK] No issues detected")
    else:
        if alerts:
            print(f"Found {len(alerts)} issue(s):\n")
            for a in alerts:
                print(f"  {a}")
        else:
            print("✓ No issues detected")
    
    # Exit code
    errors = [a for a in alerts if a.level == 'ERROR']
    sys.exit(1 if errors else 0)
