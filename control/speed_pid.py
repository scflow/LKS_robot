"""
速度 PID 控制器：在目标速度基础上按横向误差降速，输出 duty。
兼容较老 Python 版本，不依赖 dataclasses。
"""
from typing import Tuple


def _clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


class SpeedPIDController:
    def __init__(
        self,
        kp: float = 0.6,
        ki: float = 0.1,
        kd: float = 0.02,
        dt: float = 0.02,
        output_limits: Tuple[float, float] = (0.0, 0.2),
        slowdown_gain: float = 0.002,
    ):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.dt = dt
        self.output_limits = output_limits
        self.slowdown_gain = slowdown_gain  # 横向误差增大时的降速比例（|err|*gain）
        self._integral = 0.0
        self._prev_err = 0.0

    def reset(self):
        self._integral = 0.0
        self._prev_err = 0.0

    def compute(self, lateral_error: float, target_speed: float, measured_speed: float = 0.0) -> Tuple[float, dict]:
        """
        lateral_error: 横向误差（越大则减速）
        target_speed: 期望速度 (duty)
        measured_speed: 实际速度，可为空置 0
        """
        # 按横向误差动态降速，并限制到输出范围内
        slow = abs(lateral_error) * self.slowdown_gain
        eff_target = target_speed - slow
        lo, hi = self.output_limits
        eff_target = _clamp(eff_target, lo, hi)

        err = eff_target - measured_speed
        self._integral += err * self.dt
        # 简单防积分饱和
        self._integral = _clamp(self._integral, lo, hi)

        deriv = (err - self._prev_err) / self.dt if self.dt > 0 else 0.0
        u = self.kp * err + self.ki * self._integral + self.kd * deriv
        u_out = _clamp(u, lo, hi)
        self._prev_err = err

        return u_out, {
            "effective_target": eff_target,
            "error": err,
            "integral": self._integral,
            "derivative": deriv,
            "raw_output": u,
        }
