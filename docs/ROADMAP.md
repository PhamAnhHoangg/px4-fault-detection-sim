# Roadmap

Status as of 2026-11-20. Done means checked by running it. Draft means written but not run.

## Done
- PX4 v1.17.0 SIH fixed-wing flown hands-off, with engine fault by `SIH_T_MAX` 0 (12 flights).
- Feature table, leave-one-flight-out evaluation and figure from the ULogs. Result: 6 of 6 detected, median delay 1.9 s, no false alarms.
- PX4 + Gazebo Harmonic installed in a separate WSL2 distro and the rc_cessna flown by hand.
- Engine cut found for Gazebo: the throttle limit parameters work, `failure motor off` does not.
- 12 scripted Gazebo flights recorded (`record_set.sh`), table built, detector run: 6 of 6 detected, median delay 2.65 s, no false alarms.

## 1. Gazebo flights (done)
- Recorder and batch script work. Settle time 30 s was enough. The fault time is read from the `FW_THR_MAX` change.

## 2. Detector on Gazebo flights (first result done)
- Done: leave-one-flight-out on 12 flights, compared with SIH.
- Next: make the task harder, with other fault types, noisier flights, wind, and more flights.
- Elevator fault: injection by setting `CA_SV_CS2_TRQ_P` to 0 (the allocator stops moving the elevator). Scripts exist (`record_set_elevator.sh`, `cross_fault.py`). First check by hand with the live script that the plane stays flyable and the fault does something visible.
- Question to answer: does a detector trained on engine cuts find an elevator fault it never saw? Then: train on both.

## 3. Live visual (first version done in SIH)
- Done: `scripts/live/live_detector.py` reads the state over MAVLink, builds the same features and shows probability and alarm in a plot window. Checked in SIH against the flight log.
- Next: run it in Gazebo next to the 3D window, check the plot window on WSLg, and try an overlay in the Gazebo window itself if the separate window is not enough.

## 4. ROS 2 version (later)
- uXRCE-DDS link with matching px4_msgs, and a ROS 2 detector node.

## 5. Use the trained ALFA model (later)
- Load the saved model from the ALFA project instead of retraining. Its feature list has to match what the simulator provides. This is not checked yet.

## Later ideas (not committed)
- Unsupervised anomaly detection trained on normal simulated flights.
- A vision node (OpenCV) using a simulated camera. PX4 ships models with a mono camera (`x500_mono_cam`).
- Comparison with public PX4 datasets (UAV-SEAD, PX4 Flight Review logs, CC-BY).

## Open questions
- Why is the delay in Gazebo a bit longer than in SIH?
- Is a throttle limit close enough to a real engine failure to be useful?
- How many flights are needed before the scores mean something?
