import threading
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

# 共享参数（网页可调）
params: Dict[str, Any] = {
    # 视觉参数
    "binary_value": 90,
    "canny_low_threshold": 68,
    "hof_threshold": 40,
    "hof_min_line_len": 20,
    "hof_max_line_gap": 10,

    # 模式：1=自动巡线，0=手动
    "auto_drive": 1,

    # 自动控制参数
    "steer_center": CENTER_POSITION,
    "steer_k": 8.0,        # 舵机对 err 的比例系数（越大越灵敏）
    "steer_invert": 1,     # 方向不对改为 -1
    "motor_base": 0.10,    # 基础速度 duty
    "motor_k": 0.002,      # 转弯减速系数（随 |err| 降速）
    "motor_min": 0.00,
    "motor_max": 0.18,

    # 手动控制值（持续生效：只要 auto_drive=0 就一直按这个发）
    "manual_motor": 0.0,              # duty（可为负，负数表示倒车）
    "manual_servo": CENTER_POSITION,  # 舵机 position

    # 底盘模式/灯
    "scs_mode": SCS_MODE_ACKERMAN,
    "headlight": HEADLIGHT_OFF,

    # ROI 顶点（规范化坐标 0-1），示例四边形
    "roi_points": [],
}

# 参数类型（避免 POST 后类型错乱）
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

    "manual_motor": "float",
    "manual_servo": "int",

    "scs_mode": "int",
    "headlight": "int",

    "roi_points": "list",
}

# 共享状态
lock = threading.Lock()
latest_frames: Dict[str, np.ndarray] = {}
latest_status: Dict[str, Any] = {
    "fps": 0.0,
    "err": 0.0,
    "servo_position": CENTER_POSITION,
    "motor_duty": 0.0,
    "running": False,
    "chassis_connected": False,
    "chassis_error": "",
    "mode": "auto",  # auto/manual
}

# 前端绘制所需的覆盖信息（由 vision 填充）
latest_overlay: Dict[str, Any] = {
    "roi": [],
    "lines": [],
    "frame": {"w": 0, "h": 0},
    "err": 0.0,
}


def compute_control(err: float):
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

    servo = int(center + inv * steer_k * err)
    servo = int(clamp(servo, MIN_POSITION, MAX_POSITION))

    motor = base - mk * abs(err)
    motor = float(clamp(motor, mmin, mmax))
    motor = float(clamp(motor, MIN_DUTY, MAX_DUTY))

    return motor, servo, scs_mode, headlight, "auto"
