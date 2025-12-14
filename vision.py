import time
from typing import Any, Dict, Tuple

import cv2 as cv
import numpy as np

# ROI 顶点缓存，随输入尺寸更新
vertices = np.array([[(0, 0), (0, 0), (0, 0), (0, 0)]], dtype=np.int32)
_last_err = 0.0
_last_segments = []
_last_ts = None


class OneEuroFilter:
    """一欧元滤波器，用于对误差做强平滑。"""
    def __init__(self, min_cutoff=0.5, beta=0.003, d_cutoff=1.0):
        self.min_cutoff = float(min_cutoff)
        self.beta = float(beta)
        self.d_cutoff = float(d_cutoff)
        self.x_prev = None
        self.dx_prev = None
        self.t_prev = None

    @staticmethod
    def _alpha(cutoff, dt):
        tau = 1.0 / (2 * np.pi * cutoff)
        return 1.0 / (1.0 + tau / dt) if dt > 0 else 1.0

    def __call__(self, x, t):
        if self.t_prev is None:
            self.t_prev = t
            self.x_prev = x
            self.dx_prev = 0.0
            return x

        dt = max(t - self.t_prev, 1e-6)
        dx = (x - self.x_prev) / dt
        alpha_d = self._alpha(self.d_cutoff, dt)
        dx_hat = alpha_d * dx + (1 - alpha_d) * self.dx_prev

        cutoff = self.min_cutoff + self.beta * abs(dx_hat)
        alpha = self._alpha(cutoff, dt)
        x_hat = alpha * x + (1 - alpha) * self.x_prev

        self.x_prev = x_hat
        self.dx_prev = dx_hat
        self.t_prev = t
        return float(x_hat)


_err_filter = OneEuroFilter(min_cutoff=0.6, beta=0.003, d_cutoff=1.0)


def grayscale(image_bgr: np.ndarray) -> np.ndarray:
    return cv.cvtColor(image_bgr, cv.COLOR_BGR2GRAY)


def gaussian_blur(gray: np.ndarray) -> np.ndarray:
    return cv.GaussianBlur(gray, (3, 3), 0)


def canny(gray_blur: np.ndarray, low_threshold: int) -> np.ndarray:
    return cv.Canny(gray_blur, low_threshold, low_threshold * 3)


def region_of_interest(image: np.ndarray, params: Dict[str, Any]):
    global vertices
    imshape = image.shape

    roi_points = params.get("roi_points") or []
    valid_roi = []
    used_custom = False
    try:
        for p in roi_points:
            if not isinstance(p, (list, tuple)) or len(p) != 2:
                continue
            x, y = float(p[0]), float(p[1])
            # 支持 0~1 规范化坐标；如果传入像素值也允许使用
            if 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0:
                px = int(x * imshape[1])
                py = int(y * imshape[0])
            else:
                px = int(x)
                py = int(y)
            if 0 <= px < imshape[1] and 0 <= py < imshape[0]:
                valid_roi.append((px, py))
    except Exception:
        valid_roi = []

    if len(valid_roi) >= 3:
        vertices = np.array([valid_roi], dtype=np.int32)
        used_custom = True
    else:
        vertices = np.array([[
            (10, imshape[0]),
            (imshape[1] * 5 / 34, imshape[0] * 2 / 3),
            (imshape[1] * 29 / 34, imshape[0] * 2 / 3),
            (imshape[1] - 20, imshape[0])
        ]], dtype=np.int32)
        used_custom = False

    mask = np.zeros_like(image)
    ignore_mask_color = 255 if len(image.shape) == 2 else (255,) * image.shape[2]
    cv.fillPoly(mask, vertices, ignore_mask_color)
    return cv.bitwise_and(image, mask), mask, vertices, used_custom


def hough_lines(edge_roi: np.ndarray, threshold: int, min_line_len: int, max_line_gap: int):
    rho = 2
    theta = np.pi / 180
    return cv.HoughLinesP(edge_roi, rho, theta, threshold, np.array([]), min_line_len, max_line_gap)


def bypass_angle_filter(lines):
    low_thres = 20
    high_thres = 80
    filtered = []
    if lines is None:
        return filtered
    for line in lines:
        for x1, y1, x2, y2 in line:
            if x1 == x2 or y1 == y2:
                continue
            angle = abs(np.arctan((y2 - y1) / (x2 - x1)) * 180 / np.pi)
            if low_thres < angle < high_thres:
                filtered.append([[x1, y1, x2, y2]])
    return filtered


def weighted_img(img: np.ndarray, initial_img: np.ndarray) -> np.ndarray:
    return cv.addWeighted(initial_img, 0.8, img, 1.0, 0.0)


def draw_lines(line_image: np.ndarray, lines, ref_shape):
    global _last_err, _last_segments
    right_y_set, right_x_set, right_slope_set, right_intercept_set = [], [], [], []
    left_y_set, left_x_set, left_slope_set, left_intercept_set = [], [], [], []

    h, w = ref_shape[:2]
    middle_x = w // 2
    max_y = h
    top_y = int(h * 0.6)  # 60% 高度取中点

    draw_segments = []

    if not lines:
        # 丢线时返回上次结果，否则给出默认直立车道
        if _last_segments:
            return _last_err, _last_segments
        return 0.0, _default_segments(ref_shape)

    for line in lines:
        for x1, y1, x2, y2 in line:
            fit = np.polyfit((x1, x2), (y1, y2), 1)
            slope, intercept = fit[0], fit[1]
            if slope > 0:
                right_y_set += [y1, y2]
                right_x_set += [x1, x2]
                right_slope_set.append(slope)
                right_intercept_set.append(intercept)
            elif slope < 0:
                left_y_set += [y1, y2]
                left_x_set += [x1, x2]
                left_slope_set.append(slope)
                left_intercept_set.append(intercept)

    right_x_err = 0.0
    left_x_err = 0.0

    if left_y_set:
        lslope = float(np.median(left_slope_set))
        lintercept = float(np.median(left_intercept_set))
        left_x_bottom = int((max_y - lintercept) / lslope)
        left_x_top = int((top_y - lintercept) / lslope)
        left_x_err = (top_y - lintercept) / lslope
        draw_segments.append({"x1": left_x_bottom, "y1": max_y, "x2": left_x_top, "y2": top_y})

    if right_y_set:
        rslope = float(np.median(right_slope_set))
        rintercept = float(np.median(right_intercept_set))
        right_x_bottom = int((max_y - rintercept) / rslope)
        right_x_top = int((top_y - rintercept) / rslope)
        right_x_err = (top_y - rintercept) / rslope
        draw_segments.append({"x1": right_x_top, "y1": top_y, "x2": right_x_bottom, "y2": max_y})

    if right_y_set and left_y_set:
        miderr_x = (right_x_err + left_x_err) / 2.0
        error = (middle_x) - miderr_x
        error = max(min(error, 40), -40)
    else:
        if _last_segments:
            return _last_err, _last_segments
        error = 0.0
        if not draw_segments:
            draw_segments = _default_segments(ref_shape)

    _last_err = float(error)
    _last_segments = draw_segments
    return float(error), draw_segments

def _default_segments(shape):
    h, w = shape[:2]
    top_y = int(h * 0.6)
    left_x_bottom = int(w * 0.35)
    right_x_bottom = int(w * 0.65)
    left_x_top = left_x_bottom
    right_x_top = right_x_bottom
    return [
        {"x1": left_x_bottom, "y1": h, "x2": left_x_top, "y2": top_y},
        {"x1": right_x_bottom, "y1": h, "x2": right_x_top, "y2": top_y},
    ]


def process_image(frame_bgr: np.ndarray, params: Dict[str, Any]) -> Tuple[Dict[str, np.ndarray], float, Dict[str, Any]]:
    low = int(params.get("canny_low_threshold", 68))
    threshold = int(params.get("hof_threshold", 40))
    min_line_len = int(params.get("hof_min_line_len", 20))
    max_line_gap = int(params.get("hof_max_line_gap", 10))

    gray = grayscale(frame_bgr)
    blur = gaussian_blur(gray)
    edges = canny(blur, low)
    roi, mask, roi_vertices, roi_custom = region_of_interest(edges, params)
    lines = hough_lines(roi, threshold, min_line_len, max_line_gap)
    filtered = bypass_angle_filter(lines)

    line_image = np.zeros_like(frame_bgr)
    err_raw, draw_segments = draw_lines(line_image, filtered, frame_bgr.shape)
    now = time.time()
    err = _err_filter(err_raw, now)
    mask_bgr = cv.cvtColor(mask, cv.COLOR_GRAY2BGR)
    processed = cv.bitwise_and(frame_bgr, mask_bgr)  # 只展示 ROI 内部区域

    gray_bgr = cv.cvtColor(gray, cv.COLOR_GRAY2BGR)
    blur_bgr = cv.cvtColor(blur, cv.COLOR_GRAY2BGR)
    edges_bgr = cv.cvtColor(edges, cv.COLOR_GRAY2BGR)
    roi_bgr = cv.cvtColor(roi, cv.COLOR_GRAY2BGR)

    return {
        "raw": frame_bgr,
        "gray": gray_bgr,
        "blur": blur_bgr,
        "canny": edges_bgr,
        "roi": roi_bgr,
        "processed": processed,
    }, err, {
        "roi": [[int(p[0]), int(p[1])] for p in (roi_vertices.tolist()[0] if len(roi_vertices) > 0 else [])],
        "lines": [
            {
                "x1": int(seg["x1"]),
                "y1": int(seg["y1"]),
                "x2": int(seg["x2"]),
                "y2": int(seg["y2"]),
            } for seg in draw_segments
        ],
        "frame": {"w": int(frame_bgr.shape[1]), "h": int(frame_bgr.shape[0])},
        "err": float(err),
        "roi_source": "custom" if roi_custom else "default",
    }
