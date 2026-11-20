#!/bin/bash
# UNTESTED DRAFT. Written from a manual Gazebo session, never run as a script.
# Records one rc_cessna flight in PX4 SITL + Gazebo Harmonic.
# usage: run_flight_gz.sh <name> <takeoff_alt> <loiter_rad> <fault: none|engine> <fault_after_s>
# env:   PX4_DIR (default $HOME/PX4-Autopilot), OUT (default ./out), HEADLESS (default 1)
# Fault = throttle limit set to 0 (FW_THR_MIN, FW_THR_MAX). `failure motor off` is accepted but has no effect
# on the rc_cessna in Gazebo.
# Things to check on the first run: px4 client commands reaching the running instance, the HEADLESS option,
# and how long the plane needs to settle into its loiter before the fault.
set -u
NAME=$1; ALT=$2; RAD=$3; FAULT=$4; AFTER=$5
PX4_DIR=${PX4_DIR:-$HOME/PX4-Autopilot}; OUT=${OUT:-$PWD/out}; mkdir -p "$OUT"; OUT=$(cd "$OUT" && pwd)
B=$PX4_DIR/build/px4_sitl_default
pkill -f "bin/px4" 2>/dev/null; pkill -f "gz sim" 2>/dev/null; sleep 3
(cd "$PX4_DIR" && HEADLESS=${HEADLESS:-1} nohup make px4_sitl gz_rc_cessna > "$OUT/$NAME.px4.log" 2>&1 &)
sleep 45   # startup and sensor settling (the first run also compiles, which takes much longer)
cd "$B/rootfs" || exit 1
P=$B/bin/px4-param; C=$B/bin/px4-commander
$P set NAV_DLL_ACT 0 >/dev/null                      # otherwise "No connection to the GCS" blocks arming
$P set MIS_TAKEOFF_ALT "$ALT" >/dev/null; $P set NAV_LOITER_RAD "$RAD" >/dev/null
for i in 1 2 3 4 5 6; do $C check 2>&1 | grep -q "OK" && break; sleep 10; done
$C takeoff
sleep "$AFTER"
if [ "$FAULT" = "engine" ]; then
  $P set FW_THR_MIN 0 >/dev/null; $P set FW_THR_MAX 0 > "$OUT/$NAME.inject.txt" 2>&1; sleep 25
else sleep 25; fi
$C disarm -f; sleep 3
pkill -f "bin/px4"; pkill -f "gz sim"; sleep 3
cp "$(ls -t "$B"/rootfs/log/*/*.ulg | head -1)" "$OUT/$NAME.ulg"
ls -la "$OUT/$NAME.ulg"
