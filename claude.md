# CLAUDE.MD - RTO4LLM Context File

## PROJECT
RTO4LLM - Reversible Text Optimizer for Large Language Models
License: GPL-3.0-or-later
Repository: https://github.com/StevenGITHUBwork/RTO4LLM

## QUICK START
```bash
# Compile (if needed)
cd src && g++ -O3 -std=c++17 -o rto reversible_text.cpp

# Compress
cat file.py | rto --compress --ext py > file.rto

# Expand  
cat file.rto | rto --expand > file.py

# Verify roundtrip
diff file.py <(cat file.rto | rto --expand)
```

## BENCHMARK (v1.5.0 - 19,985 files tested)
```
291.5 MB → 256.9 MB = 34.6 MB saved (11.9% avg, up to >20%)

BY SIZE:        SAVINGS:
<1KB            -2.4% (skip - header overhead)
1-10KB          +7.1%
10-50KB        +10.6%
50-100KB       +13.3%
100-500KB      +12.5%
500KB-1MB      +16.2% ← SWEET SPOT
1MB+           +15.0%

THROUGHPUT (12th Gen Intel i5):
  C++:    ~3.3 MB/s (228 files/s)
  Python: ~0.8 MB/s
```

## FORMAT
Header: `{"v":"1.2","m":{"~0":"word","~1":"word2"},"ext":"py"}`

Tokens:
- `~^N` = global dict (~110 keywords, built-in)
- `~*N` = type dict (py/js/c/cpp/ts/rs/sh keywords, built-in)  
- `~N` = local dict (from header "m" field)
- `~~` = literal tilde

## SUPPORTED LANGUAGES
py, js, ts, c, cpp, h, rs, sh, bash, md

## PROJECT STRUCTURE
```
src/
├── reversible_text.cpp  # C++ implementation (MAIN)
├── reversible_text.py   # Python reference
├── learner.py           # Dictionary definitions
├── safety_rails.py      # File safety utilities
└── code_checker.py      # Syntax validation

docs/
├── ALGORITHM.md         # Pseudocode
├── SAMPLES.md           # Before/after examples
├── HELP.txt             # CLI help
└── RESEARCH_PAPER.md    # Technical docs

testing/
└── test_harness.py      # Automated tests
```

## DO NOT COMPRESS (contains dictionaries)
- src/learner.py
- src/reversible_text.cpp
- src/reversible_text.py

## CONTRIBUTIONS
Developed with significant AI assistance (GitHub Copilot - Claude Opus 4.5)
Dictionary optimized from 500MB real-world corpus scan
