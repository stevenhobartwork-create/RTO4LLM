#!/usr/bin/env python3
"""
RTO4LLM - Reversible Text Optimizer for Large Language Models
==============================================================
Lossless dictionary-based compression for AI context windows.

License: GPL-3.0-or-later
Repository: https://github.com/StevenGITHUBwork/RTO4LLM

Code contributions and optimizations by:
  - GitHub Copilot (Claude Opus 4.5)
  - Dictionary optimization from 500MB corpus scan  
  - Three-tier compression: global (~^N), type-specific (~*N), local (~N)

SAFETY: This module NEVER deletes files. See safety_rails.py.

Module Contribution Tracking (DEV MODE):
    export OPTIMIZER_DEV_MODE=1
    # Then run compression - report shows each module's savings
"""
import sys
import re
import json
import argparse
import random
import string
import math
import collections

import learner
import time

# Import code checker (optional - graceful fallback if not available)
try:
    from code_checker import check_code, check_before_after
    HAS_CHECKER = True
except ImportError:
    HAS_CHECKER = False

# Import module tracker (optional - for DEV mode contribution analysis)
try:
    from module_tracker import ModuleTracker, DEV_MODE
    HAS_TRACKER = True
except ImportError:
    HAS_TRACKER = False
    DEV_MODE = False

# Global tracker instance (only active in DEV_MODE)
_tracker = ModuleTracker() if HAS_TRACKER else None

def calculate_entropy(data):
    """Calculate Shannon entropy of byte data."""
    if not data:
        return 0
    counts = collections.Counter(data)
    length = len(data)
    entropy = 0
    for count in counts.values():
        p = count / length
        entropy -= p * math.log2(p)
    return entropy

def analyze_content(data):
    """
    Analyze content to determine if it's binary, text, or already compressed.
    Returns a dict with metrics and a recommendation.
    """
    length = len(data)
    if length == 0:
        return {'type': 'empty', 'action': 'pass', 'entropy': 0, 'ws_ratio': 0}

    # 1. Null Byte Check (Fastest Binary Check)
    if b'\x00' in data[:1024]: # Check first 1KB
        return {'type': 'binary', 'reason': 'null_bytes', 'action': 'pass', 'entropy': 0, 'ws_ratio': 0}

    # 2. Entropy Check
    # Text is usually 3.5-5.0. Compressed/Encrypted is > 7.5.
    # We check the first 4KB to be fast.
    sample = data[:4096]
    entropy = calculate_entropy(sample)
    
    # 3. Whitespace Ratio
    # Text usually has spaces, tabs, newlines.
    whitespace_count = sum(1 for b in sample if b in b' \t\n\r')
    whitespace_ratio = whitespace_count / len(sample)

    # Decision Logic
    if entropy > 7.5:
        return {'type': 'high_entropy', 'entropy': entropy, 'ws_ratio': whitespace_ratio, 'action': 'pass'}
    
    if whitespace_ratio < 0.05 and entropy > 6.0:
        # Low whitespace + moderately high entropy = likely binary or minified code
        return {'type': 'binary_likely', 'entropy': entropy, 'ws_ratio': whitespace_ratio, 'action': 'pass'}

    return {'type': 'text', 'entropy': entropy, 'ws_ratio': whitespace_ratio, 'action': 'compress'}

def get_frequent_phrases(text, min_len=4, top_n=200):
    """
    Find frequent phrases (n-grams) and words.
    """
    # 1. Find frequent words first
    words = re.findall(r'\b[a-zA-Z_]{' + str(min_len) + r',}\b', text)
    
    counts = {}
    for w in words:
        counts[w] = counts.get(w, 0) + 1
    # Filter for words that appear at least 3 times to ensure savings cover overhead
    counts = {k: v for k, v in counts.items() if v > 2}
    sorted_words = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    return [w[0] for w in sorted_words[:top_n]]

def compress(text, fuzz=False, seed=42, metadata=None, file_ext=None, min_len=4, top_n=200, shuffle_stages=False):
    """
    Compress text using dictionary-based substitution.
    
    Args:
        text: Input text to compress
        fuzz: Enable fuzzing for testing
        seed: Random seed for fuzzing
        metadata: File metadata to preserve
        file_ext: File extension for type-specific dictionary
        min_len: Minimum word length for local dictionary
        top_n: Max words in local dictionary
        shuffle_stages: Randomize stage order (for contribution testing)
    """
    # Track initial size for DEV mode
    initial_size = len(text.encode('utf-8'))
    
    # Define compression stages (can be shuffled for contribution testing)
    stages = ['escape_tildes', 'global_dict', 'type_dict', 'local_dict']
    if shuffle_stages and HAS_TRACKER and DEV_MODE:
        random.shuffle(stages)
    
    # 1. Dictionary Compression
    words = get_frequent_phrases(text, min_len=min_len, top_n=top_n)
    mapping = {}
    reverse_mapping = {}
    
    # Global/Type Dictionary Logic
    global_dict = learner.get_static_global()
    type_dict = learner.get_type_specific(file_ext) if file_ext else []
    
    # Escape existing tildes to ensure reversibility
    if HAS_TRACKER and DEV_MODE:
        _tracker.start_module('escape_tildes')
    compressed_text = text.replace('~', '~~')
    if HAS_TRACKER and DEV_MODE:
        _tracker.end_module('escape_tildes', initial_size, len(compressed_text.encode('utf-8')))
    
    # Create mapping table (e.g., ~0, ~1, ~A, ~B...)
    chars = string.digits + string.ascii_letters
    
    # Helper to generate token
    def get_token(idx, prefix="~"):
        if idx < len(chars):
            return f"{prefix}{chars[idx]}"
        return f"{prefix}{idx}"

    # Process words
    # We prioritize Global/Type words to save header space
    # But we only replace them if they are actually in the text (which get_frequent_phrases ensures)
    
    # We need to know which global/type words are used to mark them in header
    used_global = []
    used_type = []
    
    # Sort words by length descending to avoid partial replacements
    words.sort(key=len, reverse=True)
    
    # Track dictionary stages
    pre_dict_size = len(compressed_text.encode('utf-8'))
    global_count = 0
    type_count = 0
    local_count = 0
    
    for word in words:
        token = None
        
        # Check Global
        if word in global_dict:
            idx = global_dict.index(word)
            token = get_token(idx, prefix="~^") # ~^0, ~^A
            used_global.append(idx)
            global_count += 1
            
        # Check Type
        elif word in type_dict:
            idx = type_dict.index(word)
            token = get_token(idx, prefix="~*") # ~*0, ~*A
            used_type.append(idx)
            type_count += 1
            
        # Local
        else:
            # Assign next local token
            local_idx = len(mapping)
            token = get_token(local_idx, prefix="~")
            mapping[word] = token
            reverse_mapping[token] = word
            local_count += 1
            
        # Apply replacement
        if token:
            compressed_text = re.sub(r'\b' + re.escape(word) + r'\b', token, compressed_text)
    
    # Track dictionary contributions (aggregate since individual replacements are too granular)
    post_dict_size = len(compressed_text.encode('utf-8'))
    if HAS_TRACKER and DEV_MODE:
        _tracker.start_module('dict_compress')
        _tracker.end_module('dict_compress', pre_dict_size, post_dict_size)
        # Also track individual dict type contributions (approximate)
        if global_count > 0:
            _tracker.modules.setdefault('global_dict', type(_tracker.modules.get('global_dict', object())))
            _tracker.register_module('global_dict')
        if type_count > 0:
            _tracker.register_module('type_dict')
        if local_count > 0:
            _tracker.register_module('local_dict')
        
    # 2. Fuzzing (if enabled)
    is_fuzzed = False
    if fuzz and random.random() < 0.1:
        is_fuzzed = True
        random.seed(seed)
        fuzz_block = ''.join(random.choices(string.ascii_letters, k=20))
        compressed_text += f"\n\n[FUZZ:{fuzz_block}]"

    # Output format: JSON header + newline + body
    header = {
        "v": "1.2", # Version
        "m": reverse_mapping, # Local map
    }
    
    if is_fuzzed:
        header["f"] = 1
        header["s"] = seed
        
    if metadata:
        header["meta"] = metadata
        
    # Indicate if we used global/type dicts (implicit by version 1.2, but good to be explicit if we change dicts)
    # For now, version 1.2 implies support for ~^ and ~* tokens using the static lists in learner.py
    if file_ext:
        header["ext"] = file_ext

    # Use compact separators to save space
    header_str = json.dumps(header, separators=(',', ':'))
    result = header_str + "\n" + compressed_text
    
    # Final tracking
    if HAS_TRACKER and DEV_MODE:
        final_size = len(result.encode('utf-8'))
        _tracker.start_module('header_overhead')
        _tracker.end_module('header_overhead', post_dict_size, final_size)
    
    return result

def expand(text):
    # Split header and body
    try:
        header_line, body = text.split('\n', 1)
        header = json.loads(header_line)
    except ValueError:
        # Fallback if not formatted correctly
        return text

    # 1. Defuzz
    if header.get("f") or header.get("fuzzed"):
        # Remove the fuzz block, handling potential trailing newlines
        body = re.sub(r'\n\n\[FUZZ:.*?\]\s*$', '', body)
        # Report fuzzing to stderr (so test harness can see it)
        sys.stderr.write("[INFO] File was fuzzed\n")
        
    # 2. Decompress
    reverse_mapping = header.get("m", header.get("map", {}))
    
    # Add Global/Type mappings
    global_dict = learner.get_static_global()
    chars = string.digits + string.ascii_letters
    
    def get_token(idx, prefix="~"):
        if idx < len(chars):
            return f"{prefix}{chars[idx]}"
        return f"{prefix}{idx}"

    # We need to reconstruct the full mapping to do a single pass replacement
    # Or we can do regex replacement for all known patterns.
    # The issue is we don't know WHICH global words were used just by looking at the header.
    # But we can scan the body for tokens? No, that's slow.
    # Actually, we can just build a regex that matches ~^..., ~*..., ~...
    
    # Better: Add global/type words to reverse_mapping
    # We iterate through the global dict and add entries for ~^0, ~^1 etc.
    # This might be large if global dict is large.
    # Optimization: Only add tokens that appear in the text?
    # Or just rely on the regex callback to look them up dynamically.
    
    file_ext = header.get("ext")
    type_dict = learner.get_type_specific(file_ext) if file_ext else []
    
    # Create a single regex for all replacements
    # Pattern: ~~ | ~^[0-9a-zA-Z]+ | ~*[0-9a-zA-Z]+ | ~[0-9a-zA-Z]+
    # We need to be careful about greedy matching. ~^10 vs ~^1.
    # Our tokens are ~ + char OR ~ + number.
    # If we use ~^A, it's 3 chars. ~^10 is 4 chars.
    
    # Let's use a callback function with a regex that matches our token structure.
    # Tokens start with ~, then optional ^ or *, then a char or digits.
    token_pattern = re.compile(r'~~|~[\^\*]?[0-9a-zA-Z]+')
    
    def replace_func(match):
        token = match.group(0)
        if token == '~~':
            return '~'
            
        # Check Local
        if token in reverse_mapping:
            return reverse_mapping[token]
            
        # Check Global (~^...)
        if token.startswith('~^'):
            idx_str = token[2:]
            try:
                if idx_str.isdigit() and int(idx_str) >= len(chars):
                     idx = int(idx_str)
                else:
                     # Reverse lookup char
                     idx = chars.index(idx_str)
                
                if 0 <= idx < len(global_dict):
                    return global_dict[idx]
            except ValueError:
                pass
                
        # Check Type (~*...)
        if token.startswith('~*'):
            idx_str = token[2:]
            try:
                if idx_str.isdigit() and int(idx_str) >= len(chars):
                     idx = int(idx_str)
                else:
                     # Reverse lookup char
                     idx = chars.index(idx_str)
                
                if 0 <= idx < len(type_dict):
                    return type_dict[idx]
            except ValueError:
                pass
                
        return token # Return as is if not found (shouldn't happen if valid)
        
    expanded_text = token_pattern.sub(replace_func, body)
        
    return expanded_text


# ============================================================================
# Help & Documentation System
# ============================================================================

VERSION = "1.3.0"
BUILD_DATE = "2025-11-25"

HELP_TEXT = f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                     REVERSIBLE TEXT OPTIMIZER v{VERSION}                       ║
║                         Build: {BUILD_DATE}                                    ║
╚══════════════════════════════════════════════════════════════════════════════╝

DESCRIPTION
    Compresses text for AI context windows while preserving 100% reversibility.
    Uses dictionary-based substitution with three dictionary tiers:
    
    1. GLOBAL DICT (~^) - Common programming keywords (function, return, import)
    2. TYPE DICT (~*)   - Language-specific keywords (self, def, None for Python)  
    3. LOCAL DICT (~)   - Frequent words found in the specific file
    
    Compression is LOSSLESS - expand(compress(text)) == text always.

USAGE
    # Compress stdin
    cat file.py | python3 reversible_text.py --compress > file.py.rto
    
    # Expand back
    cat file.py.rto | python3 reversible_text.py --expand > file_restored.py
    
    # With metadata preservation
    python3 reversible_text.py --compress --filename file.py --mtime 1732500000
    
    # With syntax checking
    python3 reversible_text.py --compress --check --filename file.py

OPTIONS
    --compress          Compress input text
    --expand            Expand compressed text back to original
    --check             Run syntax/permission checks before and after
    --no-check          Skip all checks (faster)
    --fuzz              Enable fuzzing for testing (adds random blocks)
    --seed N            Random seed for fuzzing (default: 42)
    
    --filename FILE     Original filename (for type detection & metadata)
    --mtime FLOAT       Original modification time (preserved in header)
    --mode INT          Original file permissions (preserved in header)
    
    --min-len N         Minimum word length for local dict (default: 4)
    --top-n N           Max words in local dictionary (default: 200)
    --shuffle-stages    Randomize compression stages (for contribution testing)
    
    --show-global-dict  Print the global dictionary and exit
    --show-type-dict E  Print type-specific dict for extension E and exit
    --show-claude-md    Print the claude.md guidelines and exit
    --show-config       Print current configuration and exit
    --dev-report        Print module contribution report (requires DEV_MODE)
    
    --version           Print version and exit
    --help              Print this help and exit

COMPRESSION FORMAT
    Output is: JSON_HEADER + newline + COMPRESSED_BODY
    
    Header contains:
    - "v": Version (currently "1.2")
    - "m": Local dictionary mapping (token -> word)
    - "meta": File metadata (name, mtime, mode)
    - "ext": File extension for type-specific dict
    - "f": Fuzzing flag (if fuzzing enabled)
    
    Tokens:
    - ~~      -> literal ~
    - ~^N     -> global_dict[N]
    - ~*N     -> type_dict[N]  
    - ~N      -> local_dict[N]

DEV MODE
    Set OPTIMIZER_DEV_MODE=1 to enable module contribution tracking:
    
    export OPTIMIZER_DEV_MODE=1
    cat *.py | python3 reversible_text.py --compress --shuffle-stages > /dev/null
    python3 reversible_text.py --dev-report
    
    This shows which compression stages contribute most to savings.

SAFETY
    This module NEVER deletes files. See safety_rails.py.
    All operations are non-destructive - original input is preserved.

EXAMPLES
    # Basic compression
    echo "def function(): return None" | python3 reversible_text.py --compress
    
    # Check for redundant modules
    export OPTIMIZER_DEV_MODE=1
    for f in *.py; do cat "$f" | python3 reversible_text.py --compress > /dev/null; done
    python3 reversible_text.py --dev-report

SEE ALSO
    - module_tracker.py  - Module contribution tracking
    - learner.py         - Dictionary definitions
    - code_checker.py    - Syntax checking
    - safety_rails.py    - File deletion protection

"""

def print_global_dict():
    """Print the global dictionary"""
    global_dict = learner.get_static_global()
    chars = string.digits + string.ascii_letters
    print(f"GLOBAL DICTIONARY ({len(global_dict)} entries)")
    print("=" * 60)
    for i, word in enumerate(global_dict):
        token = f"~^{chars[i]}" if i < len(chars) else f"~^{i}"
        print(f"  {token:8} -> {word}")
    print()

def print_type_dict(ext):
    """Print type-specific dictionary for given extension"""
    type_dict = learner.get_type_specific(ext)
    chars = string.digits + string.ascii_letters
    if not type_dict:
        print(f"No type-specific dictionary for extension: {ext}")
        print(f"Available extensions: py, js, c, h, cpp, ts, md")
        return
    print(f"TYPE DICTIONARY for .{ext} ({len(type_dict)} entries)")
    print("=" * 60)
    for i, word in enumerate(type_dict):
        token = f"~*{chars[i]}" if i < len(chars) else f"~*{i}"
        print(f"  {token:8} -> {word}")
    print()

def print_claude_md():
    """Print the claude.md file if it exists"""
    import os
    claude_paths = [
        os.path.join(os.path.dirname(__file__), '..', '..', '..', 'claude.md'),
        os.path.join(os.path.dirname(__file__), '..', '..', 'claude.md'),
        os.path.join(os.path.dirname(__file__), '..', 'claude.md'),
    ]
    for path in claude_paths:
        if os.path.exists(path):
            with open(path, 'r') as f:
                print(f.read())
            return
    print("claude.md not found in parent directories")

def print_config():
    """Print current configuration"""
    print(f"REVERSIBLE TEXT OPTIMIZER CONFIGURATION")
    print("=" * 60)
    print(f"  Version:        {VERSION}")
    print(f"  Build Date:     {BUILD_DATE}")
    print(f"  DEV_MODE:       {DEV_MODE}")
    print(f"  HAS_CHECKER:    {HAS_CHECKER}")
    print(f"  HAS_TRACKER:    {HAS_TRACKER}")
    print()
    print("  Global Dict:    {} entries".format(len(learner.get_static_global())))
    print("  Type Dicts:     py, js, c, h, cpp, ts, md")
    print()
    print("  Default min_len: 4")
    print("  Default top_n:   200")
    print()

def print_dev_report():
    """Print module contribution report"""
    if not HAS_TRACKER:
        print("Module tracker not available")
        return
    tracker = ModuleTracker(enabled=True)
    if not tracker.modules:
        print("No module statistics yet.")
        print("Run compressions with OPTIMIZER_DEV_MODE=1 first:")
        print("  export OPTIMIZER_DEV_MODE=1")
        print("  cat *.py | python3 reversible_text.py --compress > /dev/null")
        return
    tracker.report(file=sys.stdout)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Reversible Text Optimizer - Compress text for AI context windows',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='Run with --help for full documentation, or with no args for quick help.'
    )
    parser.add_argument('--compress', action='store_true', help='Compress input text')
    parser.add_argument('--expand', action='store_true', help='Expand compressed text')
    parser.add_argument('--fuzz', action='store_true', help='Enable fuzzing for testing')
    parser.add_argument('--seed', type=int, default=42, help='Random seed for fuzzing')
    parser.add_argument('--filename', type=str, help='Original filename for metadata')
    parser.add_argument('--mtime', type=float, help='Original modification time')
    parser.add_argument('--mode', type=int, help='Original file permissions')
    parser.add_argument('--min-len', type=int, default=4, help='Min word length for local dict')
    parser.add_argument('--top-n', type=int, default=200, help='Max words in local dict')
    parser.add_argument('--check', action='store_true', help='Run syntax/permission checks')
    parser.add_argument('--no-check', action='store_true', help='Skip all checks')
    parser.add_argument('--shuffle-stages', action='store_true', help='Randomize stage order (DEV)')
    
    # Documentation options
    parser.add_argument('--show-global-dict', action='store_true', help='Print global dictionary')
    parser.add_argument('--show-type-dict', type=str, metavar='EXT', help='Print type dict for extension')
    parser.add_argument('--show-claude-md', action='store_true', help='Print claude.md guidelines')
    parser.add_argument('--show-config', action='store_true', help='Print configuration')
    parser.add_argument('--dev-report', action='store_true', help='Print module contribution report')
    parser.add_argument('--version', action='store_true', help='Print version')
    
    args = parser.parse_args()
    
    # Handle documentation/info commands first
    if args.version:
        print(f"reversible_text.py v{VERSION} ({BUILD_DATE})")
        sys.exit(0)
    
    if args.show_global_dict:
        print_global_dict()
        sys.exit(0)
    
    if args.show_type_dict:
        print_type_dict(args.show_type_dict)
        sys.exit(0)
    
    if args.show_claude_md:
        print_claude_md()
        sys.exit(0)
    
    if args.show_config:
        print_config()
        sys.exit(0)
    
    if args.dev_report:
        print_dev_report()
        sys.exit(0)
    
    # If no action specified and stdin is a TTY, show help
    if not args.compress and not args.expand and sys.stdin.isatty():
        print(HELP_TEXT)
        sys.exit(0)
    
    # Read binary input
    input_bytes = sys.stdin.buffer.read()
    
    # Handle empty input
    if not input_bytes:
        if sys.stdin.isatty():
            print(HELP_TEXT)
        sys.exit(0)
    
    # Smart Analysis
    analysis = analyze_content(input_bytes)
    
    # Output metrics to stderr for test harness
    sys.stderr.write(f"[METRICS] entropy={analysis.get('entropy', 0):.2f} ws_ratio={analysis.get('ws_ratio', 0):.2f} type={analysis['type']}\n")
    
    # Permission check (if checker available and filename provided)
    if HAS_CHECKER and args.filename and not args.no_check:
        alerts, summary = check_code("", args.filename, check_perms=True)
        perm_alerts = [a for a in alerts if a.checker == 'perms']
        if perm_alerts:
            sys.stderr.write(f"[PERMS] {' | '.join(a.compact() for a in perm_alerts[:2])}\n")
    
    # If analysis says pass, just output and exit (unless force expand is on)
    if args.compress and analysis['action'] == 'pass':
        sys.stdout.buffer.write(input_bytes)
        sys.exit(0)
        
    try:
        input_text = input_bytes.decode('utf-8')
    except UnicodeDecodeError:
        sys.stdout.buffer.write(input_bytes)
        sys.exit(0)
    
    # Syntax check on original (if enabled)
    if HAS_CHECKER and args.check and not args.no_check:
        alerts, summary = check_code(input_text, args.filename, check_perms=False)
        syntax_errors = [a for a in alerts if a.level == 'ERROR']
        if syntax_errors:
            sys.stderr.write(f"[SYNTAX] {syntax_errors[0].compact()}\n")
    
    if args.compress:
        # Prepare metadata
        meta = {}
        if args.filename: meta['name'] = args.filename
        if args.mtime: meta['mtime'] = args.mtime
        if args.mode: meta['mode'] = args.mode
        
        # Determine extension for type-specific dict
        ext = None
        if args.filename:
            parts = args.filename.rsplit('.', 1)
            if len(parts) > 1:
                ext = parts[1]
        
        result = compress(input_text, fuzz=args.fuzz, seed=args.seed, metadata=meta, 
                         file_ext=ext, min_len=args.min_len, top_n=args.top_n,
                         shuffle_stages=args.shuffle_stages)
        
        # Verify round-trip and check for introduced syntax errors
        if HAS_CHECKER and args.check and not args.no_check:
            expanded = expand(result)
            is_ok, alert_msg = check_before_after(input_text, result, expanded, args.filename)
            if not is_ok:
                sys.stderr.write(f"{alert_msg}\n")
        
        # Check if compression actually saved space
        if len(result.encode('utf-8')) >= len(input_bytes):
            sys.stdout.write(input_text)
        else:
            sys.stdout.write(result)
            
        # Save tracker state if in DEV mode
        if HAS_TRACKER and DEV_MODE and _tracker:
            _tracker.save()
            
    elif args.expand:
        sys.stdout.write(expand(input_text))
    else:
        sys.stdout.write(input_text)
