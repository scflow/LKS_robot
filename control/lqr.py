"""
简单离散 LQR 控制器：u = -K x

状态 x 默认包含 [横向误差, 航向误差]，输出 u 可用于舵机偏转。
默认提供基于二阶近似模型的构建函数 `build_default_lqr`。
"""
from __future__ import annotations

from typing import Iterable, Tuple

import numpy as np


def _as_array(mat) -> np.ndarray:
    return np.array(mat, dtype=float)


def _dlqr(A: np.ndarray, B: np.ndarray, Q: np.ndarray, R: np.ndarray, max_iter: int = 200, tol: float = 1e-6) -> np.ndarray:
    """
    简单离散代数 Riccati 迭代求解，避免依赖 SciPy。
    返回增益矩阵 K。
    """
    P = Q
    AT = A.T
    BT = B.T
    for _ in range(max_iter):
        S = BT @ P @ B + R
        K = np.linalg.solve(S, BT @ P @ A)
        P_next = AT @ P @ A - AT @ P @ B @ K + Q
        if np.max(np.abs(P_next - P)) < tol:
            P = P_next
            break
        P = P_next
    S = BT @ P @ B + R
    K = np.linalg.solve(S, BT @ P @ A)
    return K


class LQRController:
    def __init__(
        self,
        A: Iterable[Iterable[float]],
        B: Iterable[Iterable[float]],
        Q: Iterable[Iterable[float]],
        R: Iterable[Iterable[float]],
        output_limits: Tuple[float, float] | None = None,
    ):
        self.A = _as_array(A)
        self.B = _as_array(B)
        self.Q = _as_array(Q)
        self.R = _as_array(R)
        self.K = _dlqr(self.A, self.B, self.Q, self.R)
        self.output_limits = output_limits

    def control(self, state: Iterable[float]) -> float:
        x = _as_array(state).reshape(-1, 1)
        u = float(-self.K @ x)
        if self.output_limits:
            lo, hi = self.output_limits
            u = lo if u < lo else hi if u > hi else u
        return u


def build_default_lqr(dt: float = 0.05, velocity: float = 0.6) -> LQRController:
    """
    基于简单二阶模型的默认 LQR：
    x = [横向误差, 航向误差]，输入为方向控制量。
    """
    A = np.array([
        [1.0, dt],
        [0.0, 1.0],
    ])
    B = np.array([
        [0.0],
        [velocity * dt],
    ])
    Q = np.diag([5.0, 1.0])
    R = np.array([[0.8]])
    return LQRController(A, B, Q, R, output_limits=None)
