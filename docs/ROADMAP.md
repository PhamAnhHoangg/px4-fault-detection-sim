# Roadmap

Status key: planned, in progress, done. Everything below is planned as of 2026-11-20.

## 1. Environment (planned)
- Create a separate WSL2 Ubuntu 24.04 distro for PX4 (or use the prebuilt container), on the E: drive.
- Install PX4 and Gazebo Harmonic; pin the PX4 version in the README.
- Confirm ROS 2 Jazzy can talk to PX4 (uXRCE-DDS agent, px4_msgs matching the PX4 version).
- Start with the lightweight SIH simulator to test the ROS 2 link, then Gazebo headless.

## 2. One logged flight (planned)
- Run a fixed-wing model (check that the packaged models include one).
- Fly a mission and save the PX4 log.
- Open the log with pyulog and list the available topics.

## 3. Feature node (planned)
- ROS 2 node that builds per-second features from the vehicle topics.
- Map the ALFA features to what PX4 provides; record which ones cannot be reproduced.

## 4. Fault injection (planned)
- Check what PX4 failure injection supports for a fixed-wing.
- Write a scenario file format (fault type, onset time, parameters).
- Scenario runner: fly, inject, log the ground-truth onset time.

## 5. Evaluation (planned)
- Detection delay, false alarms and misses, with the ALFA alarm rule.
- Split by flight, never by row.
- Report the gap between real-data scores and simulated-data scores.

## 6. Retrain on simulated data (planned)
- Generate many flights with varied faults and seeds.
- Retrain or fine-tune and compare with the ALFA-trained model.

## Later ideas (not committed)
- Unsupervised anomaly detection trained on normal simulated flights.
- A data-driven dynamics model trained on PX4 logs as a fast data generator.
- A vision node (OpenCV) using a simulated camera.
- Comparison with public PX4 datasets.

## Open questions
- Which fault types can PX4 inject for a fixed-wing?
- Do the packaged simulation models include a fixed-wing, and how realistic is it?
- Which PX4 version to pin?
