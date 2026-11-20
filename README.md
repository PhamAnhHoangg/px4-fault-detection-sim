# px4-fault-detection-sim

Status: planned. Nothing here has been built or run yet.

A test harness that runs a UAV fault detector inside the PX4 simulator, injects faults at known times, and measures how well the detector finds them. The first detector to test is the one from the separate project [alfa-fault-detection](https://github.com/PhamAnhHoangg/alfa-fault-detection).

## Goal

1. Fly a simulated aircraft in PX4 SITL with Gazebo.
2. A ROS 2 node reads the vehicle state each second, builds per-second features, and runs a trained model.
3. A scenario script injects a fault at a known time and logs it as ground truth.
4. An evaluation script reports detection delay, false alarms and misses, using the same method as the ALFA project (split by flight, alarm after 3 alarms in a row).

The simulator is a test environment. It is not a replacement for real flight data.

## Limits, stated up front

- The simulated aircraft is not the aircraft behind the ALFA data. Scores in simulation will differ from real-flight scores, and a detector trained on real data may need retraining on simulated data.
- Some ALFA features (for example altitude error and cross-track error) came from the fixed-wing controller through mavros. PX4's simulated topics differ, so some features may need recomputing or dropping.
- Which fault types PX4 failure injection supports for a fixed-wing (engine, control surfaces) is not yet checked. If it falls short, faults can be injected by changing actuator commands in a ROS 2 node.

## Planned layout

```
px4-fault-detection-sim/
  README.md
  docs/ROADMAP.md
  scenarios/            fault scenarios (type, onset time, parameters)
  ros2_ws/src/
    fault_detector/     ROS 2 node: features in, model, alarm out
    scenario_runner/    starts a flight, injects the fault, logs ground truth
  evaluation/           delay, false alarms, misses
  models/               trained models, or a pointer to the ALFA ones
  scripts/              run helpers
```

All paths are set through environment variables so nothing is tied to one machine.

## Environment

- Ubuntu 24.04 (PX4's current CI and release target) with ROS 2 Jazzy and Gazebo Harmonic.
- Use a separate WSL2 distro or the prebuilt container for PX4. PX4's setup script is meant for a clean Ubuntu and may not work on top of an existing system.
- Pin the PX4 version in this file once chosen. ROS 2 code needs message definitions (px4_msgs) that match the PX4 version.
- Run Gazebo headless first; add the GUI later if it is smooth on WSL2.

PX4 version: to be pinned.

## Data

- Simulated flights generated here (planned).
- Optional comparison with public PX4 data such as UAV-SEAD and the PX4 Flight Review logs (CC-BY, credit PX4).

## License and credits

License: to be chosen.
PX4 Autopilot, Gazebo and ROS 2 have their own licenses. Credit the ALFA dataset (Keipour, Mousaei and Scherer, 2021) when ALFA-trained models are used.
