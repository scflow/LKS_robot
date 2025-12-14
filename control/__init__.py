import json
import threading
from pathlib import Path
from typing import Any, Dict

import numpy as np

from chassis import (
    CENTER_POSITION,
    HEADLIGHT_OFF,
    MAX_POSITION,
    MAX_DUTY,
    MIN_POSITION,
    MIN_DUTY,
    SCS_MODE_ACKERMAN,
    clamp,
)
from .lqr import LQRController, build_default_lqr
from .speed_pid import SpeedPIDController


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = ROOT / "config" / "defaults.json"

DEFAULT_PARAMS: Dict[str, Any] = {
    # 视觉参数
    "binary_value": 90,
    "canny_low_threshold": 68,
    "hof_threshold": 40,
    "hof_min_line_len": 20,
    "hof_max_line_gap": 10,

    # 模式：1=自动巡线，0=手动
    "auto_drive": 0,

    # 转向控制（比例）
    "steer_center": CENTER_POSITION,
    "steer_k": 8.0,
    "steer_invert": 1,

    # 线性降速模式（speed_mode=0）
    "motor_base": 0.10,
    "motor_k": 0.002,
    "motor_min": 0.00,
    "motor_max": 0.18,

    # 速度控制模式：0=线性降速，1=PID
    "speed_mode": 0,
    "speed_target": 0.10,
    "speed_kp": 0.6,
    "speed_ki": 0.1,
    "speed_kd": 0.02,
    "speed_dt": 0.02,
    "speed_slowdown_gain": 0.002,  # 按横向误差降速

    # 手动控制值
    "manual_motor": 0.0,
    "manual_servo": CENTER_POSITION,

    # 底盘模式/灯
    "scs_mode": SCS_MODE_ACKERMAN,
    "headlight": HEADLIGHT_OFF,

    # ROI 顶点（规范化坐标 0-1）
    "roi_points": [],
}

# 参数类型
PARAM_TYPES: Dict[str, str] = {
    "binary_value": "int",
    "canny_low_threshold": "int",
    "hof_threshold": "int",
    "hof_min_line_len": "int",
    "hof_max_line_gap": "int",

    "auto_drive": "int",

    "steer_center": "int",
    "steer_k": "float",
    "steer_invert": "int",

    "motor_base": "float",
    "motor_k": "float",
    "motor_min": "float",
    "motor_max": "float",

    "speed_mode": "int",
    "speed_target": "float",
    "speed_kp": "float",
    "speed_ki": "float",
    "speed_kd": "float",
    "speed_dt": "float",
    "speed_slowdown_gain": "float",

    "manual_motor": "float",
    "manual_servo": "int",

    "scs_mode": "int",
    "headlight": "int",

    "roi_points": "list",
}


def _load_params_from_file(base: Dict[str, Any]) -> Dict[str, Any]:
    if DEFAULT_CONFIG_PATH.exists():
        try:
            with open(DEFAULT_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                for k, v in data.items():
                    base[k] = v
        except Exception:
            pass
    return base


# 共享参数（网页可调）
params: Dict[str, Any] = _load_params_from_file(dict(DEFAULT_PARAMS))

# 共享状态
lock = threading.Lock()
latest_frames: Dict[str, np.ndarray] = {}
latest_status: Dict[str, Any] = {
    "fps": 0.0,
    "err": 0.0,
    "servo_position": CENTER_POSITION,
    "motor_duty": 0.0,
    "running": False,
    "camera_connected": False,
    "camera_error": "",
    "chassis_connected": False,
    "chassis_error": "",
    "mode": "manual",  # auto/manual
}

# 前端绘制所需的覆盖信息（由 vision 填充）
latest_overlay: Dict[str, Any] = {
    "roi": [],
    "lines": [],
    "frame": {"w": 0, "h": 0},
    "err": 0.0,
    "roi_source": "default",
}

# 速度 PID 控制器
_speed_pid = SpeedPIDController()
_last_motor = 0.0


def compute_control(err: float):
    global _last_motor
    with lock:
        auto = int(params["auto_drive"]) == 1
        scs_mode = int(params["scs_mode"])
        headlight = int(params["headlight"])

        if not auto:
            motor = float(params["manual_motor"])
            servo = int(params["manual_servo"])
            return motor, servo, scs_mode, headlight, "manual"

        center = int(params["steer_center"])
        steer_k = float(params["steer_k"])
        inv = int(params["steer_invert"])

        base = float(params["motor_base"])
        mk = float(params["motor_k"])
        mmin = float(params["motor_min"])
        mmax = float(params["motor_max"])

        speed_mode = int(params.get("speed_mode", 0))
        speed_target = float(params.get("speed_target", base))
        pid_kp = float(params.get("speed_kp", _speed_pid.kp))
        pid_ki = float(params.get("speed_ki", _speed_pid.ki))
        pid_kd = float(params.get("speed_kd", _speed_pid.kd))
        pid_dt = float(params.get("speed_dt", _speed_pid.dt))
        slowdown_gain = float(params.get("speed_slowdown_gain", _speed_pid.slowdown_gain))

    servo = int(center + inv * steer_k * err)
    servo = int(clamp(servo, MIN_POSITION, MAX_POSITION))

    if speed_mode == 1:
        _speed_pid.kp = pid_kp
        _speed_pid.ki = pid_ki
        _speed_pid.kd = pid_kd
        _speed_pid.dt = pid_dt
        _speed_pid.output_limits = (mmin, mmax)
        _speed_pid.slowdown_gain = slowdown_gain
        motor, _dbg = _speed_pid.compute(err, target_speed=speed_target, measured_speed=_last_motor)
    else:
        motor = base - mk * abs(err)
        motor = float(clamp(motor, mmin, mmax))

    motor = float(clamp(motor, MIN_DUTY, MAX_DUTY))
    _last_motor = motor

    return motor, servo, scs_mode, headlight, "auto"
