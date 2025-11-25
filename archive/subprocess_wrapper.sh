#!/bin/bash
#
# Copilot Subprocess Wrapper
# ==========================
# Spawn and manage AI/Copilot sessions via screen or tmux
# Supports parameter passing, output capture, and batch operations
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_DIR="$SCRIPT_DIR/.state"
LOG_DIR="$SCRIPT_DIR/logs"
SESSION_PREFIX="copilot_opt"

# Backend selection (screen or tmux)
BACKEND="${BACKEND:-screen}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_ok() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_err() { echo -e "${RED}[ERROR]${NC} $1"; }

# Initialize directories
init_dirs() {
    mkdir -p "$STATE_DIR" "$LOG_DIR"
}

# Generate unique session name
gen_session_name() {
    echo "${SESSION_PREFIX}_$(date +%s)_$$"
}

# Spawn a new session
spawn_session() {
    local cmd="$1"
    local name="${2:-$(gen_session_name)}"
    
    if [[ "$BACKEND" == "screen" ]]; then
        screen -dmS "$name" bash -c "$cmd; echo '[SESSION COMPLETE]'; read -p 'Press enter to close...'"
        log_ok "Spawned screen session: $name"
    else
        tmux new-session -d -s "$name" "$cmd; echo '[SESSION COMPLETE]'; read"
        log_ok "Spawned tmux session: $name"
    fi
    
    echo "$name" >> "$STATE_DIR/active_sessions.txt"
    echo "$name"
}

# List active sessions
list_sessions() {
    if [[ "$BACKEND" == "screen" ]]; then
        screen -ls 2>/dev/null | grep "$SESSION_PREFIX" || echo "No active sessions"
    else
        tmux list-sessions 2>/dev/null | grep "$SESSION_PREFIX" || echo "No active sessions"
    fi
}

# Attach to a session
attach_session() {
    local name="$1"
    
    if [[ -z "$name" ]]; then
        log_err "Session name required"
        return 1
    fi
    
    if [[ "$BACKEND" == "screen" ]]; then
        screen -r "$name"
    else
        tmux attach-session -t "$name"
    fi
}

# Send command to session
send_to_session() {
    local name="$1"
    local keys="$2"
    
    if [[ "$BACKEND" == "screen" ]]; then
        screen -S "$name" -X stuff "$keys
"
    else
        tmux send-keys -t "$name" "$keys" Enter
    fi
    log_ok "Sent to $name: $keys"
}

# Capture session output
capture_session() {
    local name="$1"
    local output_file="${2:-$LOG_DIR/${name}_$(date +%Y%m%d_%H%M%S).log}"
    
    if [[ "$BACKEND" == "screen" ]]; then
        screen -S "$name" -X hardcopy "$output_file"
    else
        tmux capture-pane -t "$name" -p > "$output_file"
    fi
    
    log_ok "Captured output to: $output_file"
    echo "$output_file"
}

# Kill a session
kill_session() {
    local name="$1"
    
    if [[ "$BACKEND" == "screen" ]]; then
        screen -S "$name" -X quit 2>/dev/null || true
    else
        tmux kill-session -t "$name" 2>/dev/null || true
    fi
    
    # Remove from active list
    if [[ -f "$STATE_DIR/active_sessions.txt" ]]; then
        sed -i "/$name/d" "$STATE_DIR/active_sessions.txt"
    fi
    
    log_ok "Killed session: $name"
}

# Kill all managed sessions
kill_all_sessions() {
    log_warn "Killing all managed sessions..."
    
    if [[ -f "$STATE_DIR/active_sessions.txt" ]]; then
        while read -r name; do
            kill_session "$name"
        done < "$STATE_DIR/active_sessions.txt"
        rm -f "$STATE_DIR/active_sessions.txt"
    fi
    
    log_ok "All sessions terminated"
}

# Run parameter optimization test in a session
run_param_test() {
    local min_len="${1:-4}"
    local top_n="${2:-100}"
    local fuzz="${3:-0.1}"
    local test_dir="${4:-$SCRIPT_DIR/../..}"
    
    local name=$(gen_session_name)
    local cmd="cd '$SCRIPT_DIR' && python3 param_optimizer.py '$test_dir' -i 20 -f 5 --quick 2>&1 | tee '$LOG_DIR/${name}.log'"
    
    spawn_session "$cmd" "$name"
}

# Run multiple parallel tests with different parameters
run_parallel_tests() {
    local num_workers="${1:-4}"
    local test_dir="${2:-$SCRIPT_DIR/../..}"
    
    log_info "Spawning $num_workers parallel test workers..."
    
    local sessions=()
    for i in $(seq 1 "$num_workers"); do
        # Randomize parameters for each worker
        local min_len=$((3 + RANDOM % 5))
        local top_n=$((50 + RANDOM % 150))
        local fuzz="0.$(printf '%02d' $((RANDOM % 20)))"
        
        local name="${SESSION_PREFIX}_worker_${i}"
        local cmd="cd '$SCRIPT_DIR' && python3 -c \"
import sys
sys.path.insert(0, 'modules')
from reversible_text import compress, expand
import random
import glob

params = {'min_len': $min_len, 'top_n': $top_n, 'fuzz': $fuzz}
print(f'Worker $i: Testing with {params}')

files = glob.glob('$test_dir/**/*.py', recursive=True)[:20]
passed = 0
for f in files:
    try:
        with open(f) as fh:
            text = fh.read()
        comp = compress(text, **params)
        exp = expand(comp)
        if exp == text:
            passed += 1
            print(f'  PASS: {f}')
        else:
            print(f'  FAIL: {f}')
    except Exception as e:
        print(f'  ERROR: {f}: {e}')

print(f'\\nWorker $i Result: {passed}/{len(files)} passed')
print(f'Parameters: {params}')
\" 2>&1 | tee '$LOG_DIR/${name}.log'"
        
        spawn_session "$cmd" "$name"
        sessions+=("$name")
    done
    
    log_info "Spawned ${#sessions[@]} workers"
    echo "Sessions: ${sessions[*]}"
    
    # Save session list
    printf '%s\n' "${sessions[@]}" > "$STATE_DIR/parallel_sessions.txt"
}

# Monitor parallel sessions until complete
monitor_parallel() {
    local timeout="${1:-120}"
    local start=$(date +%s)
    
    log_info "Monitoring parallel sessions (timeout: ${timeout}s)..."
    
    while true; do
        local now=$(date +%s)
        local elapsed=$((now - start))
        
        if [[ $elapsed -gt $timeout ]]; then
            log_warn "Timeout reached"
            break
        fi
        
        local active=0
        if [[ "$BACKEND" == "screen" ]]; then
            active=$(screen -ls 2>/dev/null | grep -c "$SESSION_PREFIX" || echo 0)
        else
            active=$(tmux list-sessions 2>/dev/null | grep -c "$SESSION_PREFIX" || echo 0)
        fi
        
        if [[ $active -eq 0 ]]; then
            log_ok "All sessions completed"
            break
        fi
        
        echo -ne "\r${BLUE}[INFO]${NC} Active sessions: $active (elapsed: ${elapsed}s)    "
        sleep 2
    done
    echo
    
    # Aggregate results
    aggregate_results
}

# Aggregate results from parallel runs
aggregate_results() {
    log_info "Aggregating results from $LOG_DIR..."
    
    local total_passed=0
    local total_tests=0
    local best_score=0
    local best_params=""
    
    for log in "$LOG_DIR"/${SESSION_PREFIX}*.log; do
        if [[ -f "$log" ]]; then
            local result=$(grep -o '[0-9]\+/[0-9]\+ passed' "$log" | tail -1)
            if [[ -n "$result" ]]; then
                local passed=$(echo "$result" | cut -d'/' -f1)
                local total=$(echo "$result" | cut -d'/' -f2 | cut -d' ' -f1)
                total_passed=$((total_passed + passed))
                total_tests=$((total_tests + total))
                
                if [[ $passed -gt $best_score ]]; then
                    best_score=$passed
                    best_params=$(grep 'Parameters:' "$log" | tail -1)
                fi
            fi
        fi
    done
    
    echo
    log_info "=== AGGREGATE RESULTS ==="
    echo "Total passed: $total_passed / $total_tests"
    echo "Best worker: $best_score passed"
    echo "$best_params"
}

# Interactive menu
interactive_menu() {
    while true; do
        echo
        echo "====================================="
        echo "  Copilot Subprocess Manager"
        echo "  Backend: $BACKEND"
        echo "====================================="
        echo "1) List sessions"
        echo "2) Spawn single test session"
        echo "3) Run parallel tests"
        echo "4) Monitor parallel sessions"
        echo "5) Attach to session"
        echo "6) Capture session output"
        echo "7) Kill session"
        echo "8) Kill all sessions"
        echo "9) View logs"
        echo "q) Quit"
        echo
        read -p "Choice: " choice
        
        case "$choice" in
            1) list_sessions ;;
            2) 
                read -p "Test directory [$SCRIPT_DIR/../..]: " tdir
                run_param_test 4 100 0.1 "${tdir:-$SCRIPT_DIR/../..}"
                ;;
            3)
                read -p "Number of workers [4]: " nw
                read -p "Test directory [$SCRIPT_DIR/../..]: " tdir
                run_parallel_tests "${nw:-4}" "${tdir:-$SCRIPT_DIR/../..}"
                ;;
            4)
                read -p "Timeout seconds [120]: " to
                monitor_parallel "${to:-120}"
                ;;
            5)
                list_sessions
                read -p "Session name: " sname
                attach_session "$sname"
                ;;
            6)
                list_sessions
                read -p "Session name: " sname
                capture_session "$sname"
                ;;
            7)
                list_sessions
                read -p "Session name: " sname
                kill_session "$sname"
                ;;
            8) kill_all_sessions ;;
            9) 
                ls -la "$LOG_DIR"/*.log 2>/dev/null || echo "No logs found"
                read -p "View log (filename): " lf
                [[ -n "$lf" ]] && less "$LOG_DIR/$lf"
                ;;
            q|Q) exit 0 ;;
            *) log_err "Invalid choice" ;;
        esac
    done
}

# Show usage
usage() {
    cat <<EOF
Usage: $0 <command> [args...]

Commands:
  spawn <cmd> [name]     Spawn a new session with command
  list                   List active sessions
  attach <name>          Attach to a session
  send <name> <keys>     Send keys to a session
  capture <name> [file]  Capture session output
  kill <name>            Kill a session
  killall                Kill all managed sessions
  test [dir]             Run single optimization test
  parallel [n] [dir]     Run n parallel tests
  monitor [timeout]      Monitor and aggregate parallel runs
  menu                   Interactive menu

Environment:
  BACKEND=screen|tmux    Set multiplexer backend (default: screen)

Examples:
  $0 spawn "python3 test.py" mytest
  $0 parallel 4 /path/to/test/files
  $0 monitor 60
  BACKEND=tmux $0 list
EOF
}

# Main entry point
main() {
    init_dirs
    
    local cmd="${1:-menu}"
    shift || true
    
    case "$cmd" in
        spawn)    spawn_session "$1" "$2" ;;
        list)     list_sessions ;;
        attach)   attach_session "$1" ;;
        send)     send_to_session "$1" "$2" ;;
        capture)  capture_session "$1" "$2" ;;
        kill)     kill_session "$1" ;;
        killall)  kill_all_sessions ;;
        test)     run_param_test 4 100 0.1 "$1" ;;
        parallel) run_parallel_tests "$1" "$2" ;;
        monitor)  monitor_parallel "$1" ;;
        menu)     interactive_menu ;;
        help|-h|--help) usage ;;
        *)        usage; exit 1 ;;
    esac
}

main "$@"
