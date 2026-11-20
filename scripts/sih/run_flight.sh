#!/bin/bash
# Tested draft of the SIH flight recorder (headless PX4 SIH fixed-wing, airframe 10041_sihsim_airplane).
# usage: run_flight.sh <name> <takeoff_alt> <loiter_rad> <fault: none|engine> <fault_after_s_wall>
# env:   PX4_DIR (default $HOME/PX4-Autopilot), OUT (default ./out)
# Fault = SIH_T_MAX set to 0. The PX4 command `failure motor off` has no effect in SIH.
set -u
NAME=$1; ALT=$2; RAD=$3; FAULT=$4; AFTER=$5
PX4_DIR=${PX4_DIR:-$HOME/PX4-Autopilot}; OUT=${OUT:-$PWD/out}; mkdir -p "$OUT"; OUT=$(cd "$OUT" && pwd)
B=$PX4_DIR/build/px4_sitl_default
RF=$OUT/rootfs_$NAME
pkill -f "bin/px4" 2>/dev/null; sleep 2
rm -rf "$RF"; mkdir -p "$RF"; cd "$RF"
(PX4_SIM_SPEED_FACTOR=2 PX4_SYS_AUTOSTART=10041 PX4_SIM_MODEL=sihsim_airplane nohup "$B/bin/px4" -d "$B/etc" -s etc/init.d-posix/rcS -w . > "$OUT/$NAME.px4.log" 2>&1 &)
sleep 18
P=$B/bin/px4-param
$P set RWTO_TKOFF 0 >/dev/null; $P set FW_LAUN_DETCN_ON 0 >/dev/null   # hands-off takeoff in SIH
$P set MIS_TAKEOFF_ALT "$ALT" >/dev/null; $P set NAV_LOITER_RAD "$RAD" >/dev/null
sleep 2
"$B/bin/px4-commander" takeoff >/dev/null 2>&1
sleep "$AFTER"
if [ "$FAULT" = "engine" ]; then $P set SIH_T_MAX 0 > "$OUT/$NAME.inject.txt" 2>&1; sleep 25; else sleep 25; fi
"$B/bin/px4-commander" disarm -f >/dev/null 2>&1; sleep 3
pkill -f "bin/px4"; sleep 3
cp "$(ls -t "$RF"/log/*/*.ulg | head -1)" "$OUT/$NAME.ulg"
ls -la "$OUT/$NAME.ulg"
