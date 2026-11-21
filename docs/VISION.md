# Vision detector (OpenCV) next to the telemetry detector

**Parked (2026-11-21), experimental.** The project's focus is machine learning on telemetry in simulation. Rendered Gazebo images are much cleaner than real camera video, so a vision result from the simulator would not say much about a real plane. The code stays here; picking it up again only makes sense with real flight video.

Goal: a second, independent detector that only looks at an onboard camera image, and a fair comparison of which one
alarms first after a fault. Expectation, said up front: telemetry will probably be faster, because it reads the attitude
directly while the camera only sees its effect. The value of vision is that it does not trust the flight computer.

## Status (2026-11-21)

| Step | State |
| --- | --- |
| Horizon detection in OpenCV (`scripts/vision/horizon.py`) | done, tested on synthetic frames: tilt error under 0.1 degrees, height error under 0.01 image heights; all-sky and all-ground frames handled |
| Vision alarm (`vision_detect.py`) and comparison (`compare_alarms.py`) | done, checked end to end on a synthetic flight (`demo_synthetic.py`): no alarm before the cut, alarm 5 s after it. Thresholds are first guesses |
| Camera on the rc_cessna (`sim/models/rc_cessna_cam`, start with `scripts/sim.sh start gz_rc_cessna_cam`) | written, not run in Gazebo yet. PX4 is not edited: the model lives in this repo and starts with the normal Cessna airframe (4003) |
| Frame recorder (`record_frames.py`, system Python with the Gazebo bindings) | written; PNG writer tested; not run against Gazebo yet |
| Clock alignment: `live_detector.py` now logs `boot_s`, `compare_alarms.py` uses it | tested on synthetic data with a 41.5 s clock offset |
| Real comparison flights | not started |

## How it works

`horizon.py` separates sky from ground (Otsu threshold on a blue-and-bright score), finds the boundary in each column,
fits a line with a small RANSAC and reports the tilt (`roll_deg`), the height of the horizon at the image centre
(`horizon_y`, 0 top, 1 bottom) and a quality value. After an engine cut the plane noses down to keep its speed, so the
horizon rises in the image. `vision_detect.py` takes per-second means, a baseline from steady flight, and raises an
alarm after 3 seconds in a row beyond the limits (same K = 3 as the telemetry detector).

## Open questions

- Python bindings: confirmed installed on the Gazebo machine (2026-11-21). The rc_cessna has no image camera by default.
- Assumption to check: PX4's clock in SITL follows the Gazebo clock, so frame names match `boot_s`.
- The sky colour and lighting in the PX4 world: `SPLIT_MIN` and `SKY_BLUE_MIN` in `horizon.py` may need tuning on real frames.

## Steps on the Gazebo machine

```
scripts/sim.sh stop
scripts/sim.sh start gz_rc_cessna_cam
gz topic -l | grep cessna_cam                       # should print /cessna_cam
/usr/bin/python3 scripts/vision/record_frames.py --out out/frames_test --seconds 5
python scripts/vision/horizon.py out/frames_test --csv out/horizon_test.csv
```

Then a flight: start `record_frames.py` (second window or in the background) and `live_detector.py --csv out/live_cam1.csv`
with the usual engine cut, take off, and afterwards:

```
python scripts/vision/horizon.py out/frames_cam1 --csv out/horizon_cam1.csv
python scripts/vision/compare_alarms.py out/live_cam1.csv out/horizon_cam1.csv
```
