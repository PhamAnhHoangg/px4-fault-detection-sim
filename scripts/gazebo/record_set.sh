#!/bin/bash
# UNTESTED as a batch. Records 6 normal (n1..n6) and 6 engine-cut (f1..f6) Gazebo flights, each pair with the
# same takeoff altitude, loiter radius and steady time, so the only difference inside a pair is the fault.
# usage: PX4_DIR=~/PX4-Autopilot OUT=./out scripts/gazebo/record_set.sh
# Takes about 2 minutes per flight (about 25 minutes). Keep the terminal open and the computer awake.
HERE=$(cd "$(dirname "$0")" && pwd)
ALTS=(30 35 25 40 28 32)
RADS=(100 80 120 90 110 70)
STEADY=(60 50 70 55 65 60)     # simulated seconds at altitude before the fault (the same pause is used for normal flights)
for i in 0 1 2 3 4 5; do
  k=$((i+1))
  "$HERE/run_flight_gz.sh" "n$k" "${ALTS[$i]}" "${RADS[$i]}" none   "${STEADY[$i]}"
  "$HERE/run_flight_gz.sh" "f$k" "${ALTS[$i]}" "${RADS[$i]}" engine "${STEADY[$i]}"
done
echo "done. Check each flight: python scripts/inspect_log.py out/<name>.ulg"
