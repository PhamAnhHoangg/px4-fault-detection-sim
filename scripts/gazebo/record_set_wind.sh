#!/bin/bash
# Records the same 18 flights as record_set.sh + record_set_elevator.sh, but in gusty wind: wn1..wn6 normal,
# wf1..wf6 engine cut, we1..we6 elevator cut. Same heights, circles and steady times, so each wind flight has a
# calm twin. Run python sim/make_wind_setup.py first (and a calibration flight, see docs/WIND.md).
# usage: PX4_DIR=~/PX4-Autopilot OUT=./out scripts/gazebo/record_set_wind.sh      (about 40 minutes, headless)
HERE=$(cd "$(dirname "$0")" && pwd)
export SIM_TARGET=${SIM_TARGET:-gz_rc_cessna_wind} SIM_WORLD=${SIM_WORLD:-windy_gusts}
ALTS=(30 35 25 40 28 32)
RADS=(100 80 120 90 110 70)
STEADY=(60 50 70 55 65 60)
for i in 0 1 2 3 4 5; do
  k=$((i+1))
  "$HERE/run_flight_gz.sh" "wn$k" "${ALTS[$i]}" "${RADS[$i]}" none     "${STEADY[$i]}"
  "$HERE/run_flight_gz.sh" "wf$k" "${ALTS[$i]}" "${RADS[$i]}" engine   "${STEADY[$i]}"
  "$HERE/run_flight_gz.sh" "we$k" "${ALTS[$i]}" "${RADS[$i]}" elevator "${STEADY[$i]}"
done
echo "done. Check each flight: python scripts/inspect_log.py out/<name>.ulg"
