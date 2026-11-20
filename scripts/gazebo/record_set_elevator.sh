#!/bin/bash
# UNTESTED. Records 6 elevator-fault flights (e1..e6) with the same takeoff altitude, loiter radius and steady
# time as the pairs of record_set.sh, so they can be compared with the normal flights n1..n6 recorded there.
# Fault: CA_SV_CS2_TRQ_P set to 0, which stops the control allocator from moving the elevator.
# Try one flight by hand first (see docs/RUN_GAZEBO.md): the plane may not stay flyable.
# usage: PX4_DIR=~/PX4-Autopilot OUT=./out scripts/gazebo/record_set_elevator.sh
HERE=$(cd "$(dirname "$0")" && pwd)
ALTS=(30 35 25 40 28 32)
RADS=(100 80 120 90 110 70)
STEADY=(60 50 70 55 65 60)
for i in 0 1 2 3 4 5; do
  k=$((i+1))
  "$HERE/run_flight_gz.sh" "e$k" "${ALTS[$i]}" "${RADS[$i]}" elevator "${STEADY[$i]}"
done
echo "done. Check each flight: python scripts/inspect_log.py out/<name>.ulg"
