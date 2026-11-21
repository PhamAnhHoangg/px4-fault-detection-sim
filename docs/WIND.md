# Flights in wind (Gazebo)

Status 2026-11-21: set-up written and tested on PX4's published Gazebo files, not yet run in Gazebo.

## Why a generator

- PX4's `windy.sdf` sets `<wind>` but loads no wind system, so it has no effect.
- `rc_cessna` does not have `enable_wind`, so Gazebo's WindEffects would ignore it.
- A world that lists any plugin no longer gets PX4's default plugins from `server.config`. The generated world
  therefore copies all of them (IMU, GPS, airspeed, sensors, ...) and adds WindEffects with gusts, following Gazebo's
  example `gz-sim8/worlds/wind.sdf`.

`python sim/make_wind_setup.py` builds `sim/generated/worlds/windy_gusts.sdf` (default world + 4 m/s wind from the
west, speed swing +-25 percent every 15 s, direction swing +-15 degrees every 20 s, random noise) and
`sim/generated/models/rc_cessna_wind/` (the Cessna with `enable_wind`), and links both into PX4's folders.

## Calibration first

Gazebo's wind force depends on the difference between wind and link velocity, and a plane always moves fast through
the air, so the force scaling (`--scale`, default 0.1) must be checked on a normal flight before recording: the plane
should still hold its height and circle, with throttle below 100 percent, but visibly drift and bump. If it cannot
hold height, regenerate with a smaller `--scale`; if nothing changes compared with a calm flight, use a larger one.

## The test

1. `scripts/gazebo/record_set_wind.sh`: 18 flights in wind (wn, wf, we), twins of the 18 calm flights.
2. The calm-trained model on the wind flights: does it raise false alarms on the normal wind flights?
3. Leave-one-flight-out with wind flights in training, and the simple rules again.
