# Roadmap

Status as of 2026-11-20. Done means checked by running it. Draft means written but not run.

## Done
- PX4 v1.17.0 SIH fixed-wing flown hands-off, with engine fault by `SIH_T_MAX` 0 (12 flights).
- Feature table, leave-one-flight-out evaluation and figure from the ULogs. Result: 6 of 6 detected, median delay 1.9 s, no false alarms.
- PX4 + Gazebo Harmonic installed in a separate WSL2 distro and the rc_cessna flown by hand.
- Engine cut found for Gazebo: the throttle limit parameters work, `failure motor off` does not.

## 1. Gazebo flights (draft, next)
- Run `scripts/gazebo/run_flight_gz.sh` once and fix what breaks (client commands, headless option, settle time).
- Record normal and engine-cut flights with varied takeoff altitude and loiter radius.
- Run `build_table.py` on them. The settle time (`SETTLE_S`) may need to be longer than 30 s.
- Check that the fault time is read correctly from the `FW_THR_MAX` parameter change.

## 2. Detector on Gazebo flights
- Evaluate with the same leave-one-flight-out method. Compare with the SIH numbers.
- Make the task harder: other fault types (control surfaces), noisier flights, wind.

## 3. Live visual
- A script that reads the vehicle state over MAVLink while the plane flies, builds the same features and shows the fault probability and alarm next to the Gazebo window.
- Check which of the features are available live (some come from PX4 internal topics and may need a MAVLink equivalent).

## 4. ROS 2 version (later)
- uXRCE-DDS link with matching px4_msgs, and a ROS 2 detector node.

## 5. Use the trained ALFA model (later)
- Load the saved model from the ALFA project instead of retraining. Its feature list has to match what the simulator provides. This is not checked yet.

## Later ideas (not committed)
- Unsupervised anomaly detection trained on normal simulated flights.
- A vision node (OpenCV) using a simulated camera. PX4 ships models with a mono camera (`x500_mono_cam`).
- Comparison with public PX4 datasets (UAV-SEAD, PX4 Flight Review logs, CC-BY).

## Open questions
- Does the scripted Gazebo run work as written?
- Is a throttle limit close enough to a real engine failure to be useful?
- How many flights are needed before the scores mean something?
