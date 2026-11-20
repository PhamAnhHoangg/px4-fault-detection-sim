"""Small MAVLink layer for the PX4 MCP server. Raises BackendError instead of exiting."""
import struct, time
from pymavlink import mavutil

INT_TYPES = {1, 2, 3, 4, 5, 6, 7, 8}   # MAV_PARAM_TYPE integer types (PX4 sends them as raw bytes in the float field)


class BackendError(Exception):
    pass


class Px4Backend:
    def __init__(self, connection="udpin:0.0.0.0:14540"):
        self.connection = connection
        self.master = None

    @property
    def is_real(self):
        c = self.connection.lower()
        return not (c.startswith(("udp", "tcp")) and ("127.0.0.1" in c or "0.0.0.0" in c or "localhost" in c))

    def _m(self):
        if self.master is None:
            m = mavutil.mavlink_connection(self.connection)
            if m.wait_heartbeat(timeout=8) is None:
                raise BackendError(f"no heartbeat on {self.connection}: is PX4 running and is another program holding the port?")
            self.master = m
        return self.master

    def status(self):
        m = self._m()
        hb = m.recv_match(type="HEARTBEAT", blocking=True, timeout=3)
        pos = m.recv_match(type="GLOBAL_POSITION_INT", blocking=True, timeout=3)
        out = {"connection": self.connection, "real_hardware": self.is_real, "system": m.target_system}
        if hb is not None:
            out["armed"] = bool(hb.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
        if pos is not None:
            out["altitude_m"] = round(pos.alt / 1000.0, 1)
        return out

    def get_param(self, name):
        m = self._m()
        for _ in range(5):
            m.mav.param_request_read_send(m.target_system, m.target_component, name.encode(), -1)
            end = time.time() + 1.5
            while time.time() < end:
                r = m.recv_match(type="PARAM_VALUE", blocking=True, timeout=0.3)
                if r is not None and r.param_id.rstrip("\x00") == name:
                    v = r.param_value
                    if r.param_type in INT_TYPES:
                        v = struct.unpack("<i", struct.pack("<f", v))[0]
                    return v, r.param_type
        raise BackendError(f"could not read {name}")

    def set_param(self, name, value):
        _, ptype = self.get_param(name)
        m = self._m()
        raw = struct.unpack("<f", struct.pack("<i", int(value)))[0] if ptype in INT_TYPES else float(value)
        m.mav.param_set_send(m.target_system, m.target_component, name.encode(), raw, ptype)
        end = time.time() + 3.0          # PX4 can take a moment to apply and report the new value
        new = None
        while time.time() < end:
            time.sleep(0.3)
            try:
                new, _ = self.get_param(name)
            except BackendError:
                continue
            if abs(new - float(value)) <= 1e-4:
                return new
        raise BackendError(f"{name} is {new} after setting {value}")
