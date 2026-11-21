#!/bin/bash
# Version 3 (tested on 12 flights on 2026-11-20; the elevator fault is NOT tested yet). Versions 1 and 2 produced flights without a valid fault (see docs/RUN_GAZEBO.md):
# PX4 SITL keeps changed parameters between restarts, so a throttle limit left over from an earlier run stayed active.
# Records one rc_cessna flight in PX4 SITL + Gazebo Harmonic, headless by default.
# usage: run_flight_gz.sh <name> <takeoff_alt> <loiter_rad> <fault: none|engine|elevator> <steady_sim_seconds>
# env:   PX4_DIR (default $HOME/PX4-Autopilot), OUT (default ./out), HEADLESS (default 1)
# Waits use simulator time (read from PX4), not wall time, so a slow simulator does not shift the fault.
# Everything is logged to $OUT/<name>.script.log. After the run, check the flight with:
#   python scripts/inspect_log.py $OUT/<name>.ulg
# engine   = FW_THR_MIN and FW_THR_MAX set to 0. `failure motor off` has no effect on this plane.
# elevator = CA_SV_CS2_TRQ_P set to 0: the control allocator stops moving the elevator (servo 3), so pitch control is lost.
set -u
NAME=$1; ALT=$2; RAD=$3; FAULT=$4; STEADY=$5
PX4_DIR=${PX4_DIR:-$HOME/PX4-Autopilot}; OUT=${OUT:-$PWD/out}; mkdir -p "$OUT"; OUT=$(cd "$OUT" && pwd)
B=$PX4_DIR/build/px4_sitl_default
LOG=$OUT/$NAME.script.log; : > "$LOG"
say() { echo "$(date +%T) $*" | tee -a "$LOG"; }
pkill -f "bin/px4" 2>/dev/null; pkill -f "gz sim" 2>/dev/null; sleep 3
# SIM_TARGET (default gz_rc_cessna) and SIM_WORLD (default: PX4's default world) choose plane and world, e.g.
# SIM_TARGET=gz_rc_cessna_wind SIM_WORLD=windy_gusts after python sim/make_wind_setup.py
SIM_TARGET=${SIM_TARGET:-gz_rc_cessna}
WENV=""; [ -n "${SIM_WORLD:-}" ] && WENV="PX4_GZ_WORLD=$SIM_WORLD"
if [ "$SIM_TARGET" = "gz_rc_cessna" ]; then
  (cd "$PX4_DIR" && env $WENV HEADLESS=${HEADLESS:-1} nohup make px4_sitl gz_rc_cessna > "$OUT/$NAME.px4.log" 2>&1 &)
else   # models outside PX4 have no make target: start PX4 directly with the normal Cessna airframe (4003)
  (cd "$B/rootfs" && env $WENV HEADLESS=${HEADLESS:-1} PX4_SYS_AUTOSTART=4003 PX4_SIM_MODEL=$SIM_TARGET \
     nohup "$B/bin/px4" -d "$B/etc" -s etc/init.d-posix/rcS -w "$B/rootfs" < /dev/null > "$OUT/$NAME.px4.log" 2>&1 &)
fi
say "plane $SIM_TARGET, world ${SIM_WORLD:-default}"
cd "$B/rootfs" 2>/dev/null || { say "no rootfs yet, waiting"; sleep 20; cd "$B/rootfs" || exit 1; }
P=$B/bin/px4-param; C=$B/bin/px4-commander; L=$B/bin/px4-listener
simtime() { "$L" vehicle_local_position 1 2>/dev/null | awk '/timestamp:/{print int($2/1000000); exit}'; }
height()  { "$L" vehicle_local_position 1 2>/dev/null | awk '/^ *z:/{print int(-$2); exit}'; }
wait_sim() { local target=$1 n=0; while [ "$(simtime)" -lt "$target" ] 2>/dev/null; do sleep 2; n=$((n+1)); [ $n -gt 600 ] && { say "timeout waiting for sim time $target"; return 1; }; done; }

say "waiting for PX4 to answer (the first run also compiles, which can take a long time)"
for i in $(seq 1 120); do
  out=$("$P" show NAV_DLL_ACT 2>&1); echo "$out" | grep -q "NAV_DLL_ACT" && break; sleep 5
done
echo "$out" | grep -q "NAV_DLL_ACT" || { say "PX4 never answered, giving up"; exit 1; }
say "PX4 answers, sim time $(simtime)"
sleep 15   # sensors settle
show1() { "$P" show "$1" 2>&1 | grep -E "^x " | sed "s/ *[0-9]*\/[0-9]* parameters used.*//"; }
setp() { say "before: $(show1 "$1")"; "$P" set "$1" "$2" >> "$LOG" 2>&1; say "after:  $(show1 "$1")"; }
# Parameters survive simulator restarts, so set every one this script depends on, including the ones the fault changes.
setp FW_THR_MAX 1; setp FW_THR_MIN 0; setp CA_SV_CS2_TRQ_P 1
setp NAV_DLL_ACT 0; setp MIS_TAKEOFF_ALT "$ALT"; setp NAV_LOITER_RAD "$RAD"
for i in $(seq 1 12); do "$C" check 2>&1 | tee -a "$LOG" | grep -qE "OK|Ready" && break; sleep 10; done
say "takeoff at sim time $(simtime)"
"$C" takeoff 2>&1 | tee -a "$LOG"
for i in $(seq 1 90); do h=$(height); [ "${h:-0}" -ge $((ALT - 3)) ] 2>/dev/null && break; sleep 2; done
T1=$(simtime); say "reached about ${h:-?} m at sim time $T1"
wait_sim $((T1 + STEADY))
if [ "$FAULT" = "engine" ]; then
  setp FW_THR_MIN 0; setp FW_THR_MAX 0
  Tf=$(simtime); say "fault set at sim time $Tf"
  wait_sim $((Tf + 25))
elif [ "$FAULT" = "elevator" ]; then
  setp CA_SV_CS2_TRQ_P 0
  Tf=$(simtime); say "fault set at sim time $Tf"
  wait_sim $((Tf + 25))
else
  say "no fault"; wait_sim $((T1 + STEADY + 25))
  "$C" disarm -f 2>&1 | tee -a "$LOG"; sleep 3
fi
setp CA_SV_CS2_TRQ_P 1; setp FW_THR_MAX 1   # leave the simulator as it was found, so hand flights are not affected
sleep 2
pkill -f "bin/px4"; pkill -f "gz sim"; sleep 3
cp "$(ls -t "$B"/rootfs/log/*/*.ulg | head -1)" "$OUT/$NAME.ulg"
say "saved $(ls -la "$OUT/$NAME.ulg")"
