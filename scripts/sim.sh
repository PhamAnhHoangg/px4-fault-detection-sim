#!/bin/bash
# Run the PX4 simulator in the background, so you need only one terminal.
#   scripts/sim.sh start [target]   start PX4 (default target gz_rc_cessna; gz_rc_cessna_cam = with forward camera;
#                                   gz_rc_cessna_chase = with a chase camera for demo videos; sihsim_airplane for SIH)
#                                   and reset the fault parameters
#   scripts/sim.sh status           running or not, and FW_THR_MAX / FW_THR_MIN
#   scripts/sim.sh takeoff          arm and take off (same as commander takeoff in pxh)
#   scripts/sim.sh attach           open the pxh> console (leave it again with Ctrl+b then d; Ctrl+c would stop PX4)
#   scripts/sim.sh log              last lines of the simulator output
#   scripts/sim.sh stop             shut PX4 and Gazebo down
# env: PX4_DIR (default $HOME/PX4-Autopilot), HEADLESS=1 for no Gazebo window, SIM_LOG (default /tmp/px4sim.log)
# Needs tmux (sudo apt install tmux). The simulator runs inside a tmux session named px4sim.
set -u
PX4_DIR=${PX4_DIR:-$HOME/PX4-Autopilot}
B=$PX4_DIR/build/px4_sitl_default
LOG=${SIM_LOG:-/tmp/px4sim.log}
S=px4sim
REPO=$(cd "$(dirname "$0")/.." && pwd)

need_tmux() { command -v tmux >/dev/null || { echo "tmux is missing: run  sudo apt install tmux"; exit 1; }; }
running() { tmux has-session -t $S 2>/dev/null; }
pparam() { (cd "$B/rootfs" 2>/dev/null && "$B/bin/px4-param" "$@" 2>&1); }

case "${1:-}" in
  start)
    need_tmux
    TARGET=${2:-gz_rc_cessna}
    if running; then echo "already running (scripts/sim.sh stop first)"; exit 1; fi
    [ -d "$PX4_DIR" ] || { echo "no PX4 at $PX4_DIR (set PX4_DIR)"; exit 1; }
    pkill -f "bin/px4" 2>/dev/null; pkill -f "gz sim" 2>/dev/null; sleep 1
    : > "$LOG"
    # Models kept in this repo (sim/models) are started directly with an existing airframe, so PX4 itself is not edited
    # PX4 hides the Gazebo window when HEADLESS is set to anything, even 0, so set it only for HEADLESS=1
    if [ "${HEADLESS:-0}" = "1" ]; then H="HEADLESS=1"; else H="env -u HEADLESS"; fi
    case "$TARGET" in gz_rc_cessna_cam|gz_rc_cessna_chase) AUTOSTART=4003 ;; *) AUTOSTART="" ;; esac
    AUTOSTART=${SIM_AUTOSTART:-$AUTOSTART}
    if [ -n "$AUTOSTART" ]; then
      [ -x "$B/bin/px4" ] || { echo "PX4 is not built yet: run  make px4_sitl  in $PX4_DIR once"; exit 1; }
      # PX4 loads the model from its own models folder, so put a link to ours there (only a symlink, nothing is overwritten)
      MODEL=${TARGET#gz_}; MDIR="$PX4_DIR/Tools/simulation/gz/models"
      if [ -d "$REPO/sim/models/$MODEL" ] && [ -d "$MDIR" ] && [ ! -e "$MDIR/$MODEL" ]; then
        ln -s "$REPO/sim/models/$MODEL" "$MDIR/$MODEL" && echo "linked $MDIR/$MODEL -> $REPO/sim/models/$MODEL"
      fi
      RUN="cd '$B/rootfs' && GZ_SIM_RESOURCE_PATH='$REPO/sim/models'\${GZ_SIM_RESOURCE_PATH:+:\$GZ_SIM_RESOURCE_PATH} PX4_SYS_AUTOSTART=$AUTOSTART PX4_SIM_MODEL=$TARGET $H '$B/bin/px4' '$B/etc' -s etc/init.d-posix/rcS -w '$B/rootfs'"
    else
      RUN="cd '$PX4_DIR' && $H make px4_sitl $TARGET"
    fi
    tmux new-session -d -s $S -x 200 -y 50 "$RUN; echo '[simulator ended]'; sleep 5"
    tmux pipe-pane -o -t $S "cat >> '$LOG'"
    echo "starting $TARGET (the first start compiles and can take minutes); log: $LOG"
    for i in $(seq 1 120); do
      out=$(pparam show FW_THR_MAX); echo "$out" | grep -q "FW_THR_MAX" && break
      running || { echo "simulator stopped while starting, see: scripts/sim.sh log"; exit 1; }
      sleep 3
    done
    echo "$out" | grep -q "FW_THR_MAX" || { echo "PX4 did not answer after 6 minutes, see: scripts/sim.sh log"; exit 1; }
    # PX4 keeps parameters between runs: put the fault parameters back to normal on every start
    for kv in FW_THR_MAX=1 FW_THR_MIN=0 CA_SV_CS2_TRQ_P=1 NAV_DLL_ACT=0; do pparam set "${kv%=*}" "${kv#*=}" >/dev/null; done
    case "$TARGET" in sih*) pparam set SIH_T_MAX 6 >/dev/null ;; esac
    echo "ready. FW_THR_MAX = $(pparam show FW_THR_MAX | awk '/FW_THR_MAX/{print $NF}')"
    ;;
  status)
    if running; then
      echo "running"; pparam show FW_THR_MAX | grep FW_THR_MAX; pparam show FW_THR_MIN | grep FW_THR_MIN
    else echo "not running"; fi
    ;;
  takeoff)
    running || { echo "not running"; exit 1; }
    (cd "$B/rootfs" && "$B/bin/px4-commander" takeoff) && echo "takeoff sent"
    ;;
  attach) need_tmux; running && tmux attach -t $S || echo "not running" ;;
  log) tail -n "${2:-40}" "$LOG" 2>/dev/null | sed 's/\x1b\[[0-9;]*m//g' | tr -d '\r' ;;
  stop)
    if running; then
      tmux send-keys -t $S "shutdown" Enter
      for i in $(seq 1 15); do running || break; sleep 1; done
      running && tmux kill-session -t $S
    fi
    pkill -f "bin/px4" 2>/dev/null; pkill -f "gz sim" 2>/dev/null
    echo "stopped"
    ;;
  *) sed -n '2,9p' "$0"; exit 1 ;;
esac
