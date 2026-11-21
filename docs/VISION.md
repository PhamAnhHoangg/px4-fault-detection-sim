# Vision detector (OpenCV) next to the telemetry detector

Goal: a second, independent detector that only looks at an onboard camera image, and a fair comparison of which one
alarms first after a fault. Expectation, said up front: telemetry will probably be faster, because it reads the attitude
directly while the camera only sees its effect. The value of vision is that it does not trust the flight computer.

## Status (2026-11-21)

| Step | State |
| --- | --- |
| Horizon detection in OpenCV (`scripts/vision/horizon.py`) | done, tested on synthetic frames: tilt error under 0.1 degrees, height error under 0.01 image heights; all-sky and all-ground frames handled |
| Vision alarm (`vision_detect.py`) and comparison (`compare_alarms.py`) | done, checked end to end on a synthetic flight (`demo_synthetic.py`): no alarm before the cut, alarm 5 s after it. Thresholds are first guesses |
| Camera on the rc_cessna in Gazebo and a frame recorder | not started, needs the Gazebo machine |
| Real comparison flights | not started |

## How it works

`horizon.py` separates sky from ground (Otsu threshold on a blue-and-bright score), finds the boundary in each column,
fits a line with a small RANSAC and reports the tilt (`roll_deg`), the height of the horizon at the image centre
(`horizon_y`, 0 top, 1 bottom) and a quality value. After an engine cut the plane noses down to keep its speed, so the
horizon rises in the image. `vision_detect.py` takes per-second means, a baseline from steady flight, and raises an
alarm after 3 seconds in a row beyond the limits (same K = 3 as the telemetry detector).

## Open questions for step 3

- Gazebo Harmonic Python bindings for receiving camera images (`gz.transport13`, `gz.msgs10`): check they are installed.
- How to add a camera to the rc_cessna without editing PX4's own model (a separate model that includes it, plus an airframe).
- Time axis: frames must be stamped with the same flight time as the telemetry CSV, otherwise the comparison is wrong.
- The sky colour and lighting in the PX4 world: `SPLIT_MIN` and `SKY_BLUE_MIN` in `horizon.py` may need tuning on real frames.

First checks to run on the Gazebo machine (simulator running):

```
python3 -c "import gz.transport13, gz.msgs10; print('bindings ok')"
gz topic -l | head -40
```
