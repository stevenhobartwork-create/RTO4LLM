#!/usr/bin/env python3
"""
Generate AI Bundle - Creates cross-validation prompts for AI analysis
Archive utility for RTO4LLM development
SPDX-License-Identifier: GPL-3.0-or-later
"""
import os
from pathlib import Path

# Configuration - use relative paths from script location
BASE_DIR = Path(__file__).parent.parent
SRC_DIR = BASE_DIR / "src"
OUTPUT_FILE = BASE_DIR / "AI_CROSS_VALIDATION_PROMPT.md"

FILES_TO_BUNDLE = [
    SRC_DIR / "learner.py",
    SRC_DIR / "reversible_text.py",
    BASE_DIR / "testing" / "test_harness.py"
]

PROMPT_HEADER = """
# AI Cross-Validation Task

**Role**: You are a Senior Software Engineer and Algorithm Specialist.
**Task**: Review, Analyze, and Simulate the execution of the following Python Reversible Text Optimizer.

## Context
I have developed a "Reversible Text Optimizer" that compresses text files by replacing 
frequent words with short tokens.
It uses a "Hybrid Dictionary" approach:
1. **Global Dictionary**: Common programming keywords (static list).
2. **Type-Specific Dictionary**: Keywords based on file extension (static list).
3. **Local Dictionary**: Words unique to the file (stored in header).

It also preserves file metadata (mtime, permissions) in the JSON header.

## The Code

Here are the three core files of the system:

"""

PROMPT_FOOTER = """
## Your Instructions

1. **Code Review**: Analyze `reversible_text.py` and `learner.py`. Are there any edge cases where the "Hybrid Dictionary" logic (Global/Type/Local) might fail to reverse correctly?
2. **Simulation**: Mentally simulate compressing a simple Python file:
   ```python
   def hello():
       print("Hello World")
   ```
   Trace how `reversible_text.py` would tokenize `def`, `print` (Type/Global dicts) vs `"Hello"` (Local dict).
3. **Test Harness Analysis**: Look at `test_harness.py`. Does the metric parsing logic (reading stderr for `[METRICS]`) look robust?
4. **Final Verdict**: If you were to run this, would it pass? If not, what specific bug would cause it to fail?

Please provide a detailed report.
"""

def generate_bundle():
    print(f"Generating AI Bundle from {BASE_DIR}...")
    
    with open(OUTPUT_FILE, 'w') as out:
        out.write(PROMPT_HEADER)
        
        for file_path in FILES_TO_BUNDLE:
            if not file_path.exists():
                print(f"Warning: {file_path} not found!")
                continue
                
            out.write(f"### File: `{file_path.name}`\n\n")
            out.write("```python\n")
            with open(file_path, 'r') as f:
                out.write(f.read())
            out.write("\n```\n\n")
            
        out.write(PROMPT_FOOTER)
    
    print(f"Bundle generated at: {OUTPUT_FILE}")
    print("You can now copy the contents of this file to other AI models.")

if __name__ == "__main__":
    generate_bundle()
