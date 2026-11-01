"""Loopback-only PX4 SITL sensor/motor bridge. Never connects to a flight controller."""

import json
import math
import os
import subprocess
from pathlib import Path

import numpy as np

from .controller import rotation_xyzw
from .rotors import RotorAllocator

ENU_NED = np.array([[0.0, 1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, -1.0]])
FLU_FRD = np.diag([1.0, -1.0, -1.0])


def sensor_values(position, velocity, acceleration, quaternion_xyzw, angular_velocity_world):
    rotation = rotation_xyzw(quaternion_xyzw)
    body_frd = FLU_FRD @ rotation.T
    rotation_ned_frd = ENU_NED @ rotation @ FLU_FRD
    specific = body_frd @ (np.asarray(acceleration) - [0.0, 0.0, -9.80665])
    gyro = body_frd @ angular_velocity_world
    magnetic = rotation_ned_frd.T @ np.array([0.21523, 0.007, 0.42741])
    height = 488.0 + position[2]
    return {
        "accel_frd": specific,
        "gyro_frd": gyro,
        "mag_frd": magnetic,
        "latitude": 47.397742 + math.degrees(position[1] / 6371000),
        "longitude": 8.545594 + math.degrees(position[0] / (6371000 * math.cos(math.radians(47.397742)))),
        "altitude_m": height,
        "pressure_hpa": 1013.25 * (1 - height / 44330) ** 5.255,
        "velocity_ned": ENU_NED @ velocity,
    }


def airframe_script(limits=None):
    lines = [
        "#!/bin/sh",
        ". ${R}etc/init.d/rc.mc_defaults",
        "param set-default CA_AIRFRAME 0",
        "param set-default CA_ROTOR_COUNT 4",
    ]
    allocator = RotorAllocator()
    for i, location in enumerate(allocator.locations):
        x, y, _ = FLU_FRD @ location
        # PX4: torque = ct * (r cross axis - km * axis), axis = -Z FRD.
        # A positive FRD yaw torque is a negative FLU yaw torque.
        for name, value in (("PX", x), ("PY", y), ("PZ", 0), ("KM", -allocator.matrix[3, i])):
            lines.append(f"param set-default CA_ROTOR{i}_{name} {value}")
        lines.append(f"param set-default PWM_MAIN_FUNC{i + 1} {101 + i}")
    parameters = {
        "COM_RC_IN_MODE": 4,
        "COM_RCL_EXCEPT": 4,
        "MPC_THR_HOVER": 0.56,
        "MPC_XY_VEL_MAX": 8,
        "MPC_XY_CRUISE": 8,
        "MPC_Z_VEL_MAX_UP": 4,
        "MPC_Z_VEL_MAX_DN": 3,
        "COM_OF_LOSS_T": 0.5,
        "COM_OBL_RC_ACT": 4,
        "SDLOG_MODE": 1,
        **(limits or {}),
    }
    lines.extend(f"param set-default {name} {value}" for name, value in parameters.items())
    return "\n".join(lines) + "\n"


class PX4SITL:
    def __init__(self, index, output, *, px4_root="/opt/PX4-Autopilot", limits=None):
        from pymavlink import mavutil

        if not 0 <= index < 8:
            raise ValueError("Invalid SITL vehicle index")
        self.index, self.system = index, index + 1
        self.limits = limits
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=True)
        self.root = Path(px4_root) / "build/px4_sitl_default"
        self.sim = mavutil.mavlink_connection(f"tcpin:127.0.0.1:{4560 + index}", source_system=201 + index)
        self.offboard = mavutil.mavlink_connection(
            f"udpin:127.0.0.1:{14540 + index}", source_system=201 + index
        )
        self.process = None
        self.console = None
        self.controls = np.zeros(4)
        self.allocator = RotorAllocator()
        self.armed = False
        self.offboard_active = False
        self.last_actuator_time = -1.0
        self.first_actuator = False
        self.offset = None
        self.local_position = None
        self.last_request = -100.0
        self.last_heartbeat = -100.0
        self.last_gps = -100.0
        self.prev_velocity = np.zeros(3)
        self.stats = {
            "sensor_packets": 0,
            "gps_packets": 0,
            "actuator_packets": 0,
            "setpoint_packets": 0,
            "armed_seen": False,
            "offboard_seen": False,
        }
        self.messages = []

    def start(self):
        if self.process is not None:
            raise RuntimeError("SITL already started")
        script = self.root / "etc/init.d-posix/airframes/9001_embernet"
        script.write_text(airframe_script(self.limits))
        self.console = (self.output / "px4-console.log").open("w")
        env = dict(
            os.environ,
            PX4_SIM_MODEL="embernet",
            PX4_SIM_HOST_ADDR="127.0.0.1",
            PX4_HOME_LAT="47.397742",
            PX4_HOME_LON="8.545594",
            PX4_HOME_ALT="488",
            EMBERNET_SITL_NON_RT="1",
        )
        self.process = subprocess.Popen(
            [
                str(self.root / "bin/px4"),
                "-i",
                str(self.index),
                "-d",
                str(self.root / "etc"),
                "-s",
                "etc/init.d-posix/rcS",
            ],
            cwd=self.output,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=self.console,
            stderr=subprocess.STDOUT,
        )

    def _receive(self, now, wait=False):
        from pymavlink import mavutil

        if wait:
            packet = self.sim.recv_match(type="HIL_ACTUATOR_CONTROLS", blocking=True, timeout=0.25)
            if packet:
                self._actuator(packet, now)
        for _ in range(80):
            packet = self.sim.recv_match(blocking=False)
            if packet is None:
                break
            if packet.get_type() == "HIL_ACTUATOR_CONTROLS":
                self._actuator(packet, now)
        for _ in range(100):
            packet = self.offboard.recv_match(blocking=False)
            if packet is None:
                break
            kind = packet.get_type()
            if kind == "HEARTBEAT" and packet.get_srcSystem() == self.system:
                self.armed = bool(packet.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
                self.offboard_active = (packet.custom_mode >> 16) & 0xFF == 6
                self.stats["armed_seen"] |= self.armed
                self.stats["offboard_seen"] |= self.offboard_active
            elif kind == "LOCAL_POSITION_NED":
                self.local_position = np.array([packet.x, packet.y, packet.z])
            elif kind in ("COMMAND_ACK", "STATUSTEXT"):
                self.messages.append({"time": now, "message": packet.to_dict()})
                self.messages = self.messages[-500:]

    def _actuator(self, packet, now):
        values = np.asarray(packet.controls[:4], float)
        if not np.isfinite(values).all():
            raise RuntimeError("Nonfinite PX4 motor output")
        self.armed = bool(packet.mode & 128)
        self.controls = np.clip(values, 0, 1) if self.armed else np.zeros(4)
        self.last_actuator_time, self.first_actuator = now, True
        self.stats["actuator_packets"] += 1

    def step(
        self,
        now,
        position,
        velocity,
        quaternion_xyzw,
        angular_velocity_world,
        target,
        *,
        enable_offboard=True,
    ):
        from pymavlink import mavutil

        if self.process.poll() is not None:
            raise RuntimeError(f"PX4 SITL exited: {self.process.returncode}")
        self._receive(now)
        acceleration = (np.asarray(velocity) - self.prev_velocity) * 250
        self.prev_velocity = np.asarray(velocity).copy()
        values = sensor_values(
            np.asarray(position),
            np.asarray(velocity),
            acceleration,
            quaternion_xyzw,
            np.asarray(angular_velocity_world),
        )
        stamp = int((now + 1) * 1e6)
        self.sim.mav.hil_sensor_send(
            stamp,
            *values["accel_frd"],
            *values["gyro_frd"],
            *values["mag_frd"],
            values["pressure_hpa"],
            0.0,
            values["altitude_m"],
            20.0,
            0x1FFF,
        )
        self.stats["sensor_packets"] += 1
        if now - self.last_gps >= 0.05:
            vn, ve, vd = values["velocity_ned"]
            self.sim.mav.hil_gps_send(
                stamp,
                3,
                int(values["latitude"] * 1e7),
                int(values["longitude"] * 1e7),
                int(values["altitude_m"] * 1000),
                30,
                50,
                int(np.linalg.norm(velocity) * 100),
                int(vn * 100),
                int(ve * 100),
                int(vd * 100),
                int(math.degrees(math.atan2(ve, vn)) % 360 * 100),
                18,
            )
            self.last_gps = now
            self.stats["gps_packets"] += 1
            if self.local_position is not None and self.offset is None and now >= 5:
                self.offset = np.asarray(position) - ENU_NED @ self.local_position
            if self.offset is not None and enable_offboard:
                ned = ENU_NED @ (np.asarray(target) - self.offset)
                self.offboard.mav.set_position_target_local_ned_send(
                    int(now * 1000),
                    self.system,
                    1,
                    mavutil.mavlink.MAV_FRAME_LOCAL_NED,
                    0b100111111000,
                    *ned,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    math.pi / 2,
                    0,
                )
                self.stats["setpoint_packets"] += 1
        if now - self.last_heartbeat >= 1:
            self.sim.mav.heartbeat_send(0, 8, 0, 0, 0)
            self.offboard.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS, 8, 0, 0, 0)
            self.last_heartbeat = now
        if now >= 10 and self.offset is not None and now - self.last_request >= 2 and enable_offboard:
            if not self.offboard_active:
                self.offboard.mav.command_long_send(
                    self.system,
                    1,
                    mavutil.mavlink.MAV_CMD_DO_SET_MODE,
                    0,
                    mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
                    6,
                    0,
                    0,
                    0,
                    0,
                    0,
                )
            if not self.armed:
                self.offboard.mav.command_long_send(
                    self.system, 1, mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 0, 0, 0, 0, 0, 0
                )
            self.last_request = now
        self._receive(now, wait=self.first_actuator)
        if self.first_actuator and now - self.last_actuator_time > .5:
            raise RuntimeError("PX4 motor telemetry is stale; stopping physics session")
        speeds = 100 + 1000 * self.controls if self.armed else np.zeros(4)
        rotor_thrust = 8.54858e-6 * speeds**2
        return self.allocator.matrix @ rotor_thrust

    def close(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
        if self.console:
            self.console.close()
        self.sim.close()
        self.offboard.close()
        (self.output / "mavlink-report.json").write_text(
            json.dumps(
                {
                    "stats": self.stats,
                    "offset_enu": None if self.offset is None else self.offset.tolist(),
                    "messages": self.messages,
                },
                indent=2,
            )
        )
