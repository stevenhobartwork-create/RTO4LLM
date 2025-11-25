#!/bin/bash
# Setup a Tmux session for testing RTO4LLM
# SPDX-License-Identifier: GPL-3.0-or-later

SESSION="rto_test"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"

tmux has-session -t $SESSION 2>/dev/null

if [ $? != 0 ]; then
  tmux new-session -d -s $SESSION -n "Main_Control"
  tmux split-window -h

  # Pane 1: Test Harness
  tmux send-keys -t $SESSION:0.0 "cd '$BASE_DIR'" C-m
  tmux send-keys -t $SESSION:0.0 "echo 'Ready to run tests...'" C-m
  tmux send-keys -t $SESSION:0.0 "python3 testing/test_harness.py"

  # Pane 2: Manual testing
  tmux send-keys -t $SESSION:0.1 "cd '$BASE_DIR'" C-m
  tmux send-keys -t $SESSION:0.1 "echo 'Manual testing pane'" C-m

  tmux select-pane -t $SESSION:0.0
fi

tmux attach-session -t $SESSION
