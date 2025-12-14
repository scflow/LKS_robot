from typing import Any, Dict, Tuple

import cv2 as cv
import numpy as np

# ROI 顶点缓存，随输入尺寸更新
vertices = np.array([[(0, 0), (0, 0), (0, 0), (0, 0)]], dtype=np.int32)


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
    try:
        for p in roi_points:
            if not isinstance(p, (list, tuple)) or len(p) != 2:
                continue
            x, y = float(p[0]), float(p[1])
            if 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0:
                valid_roi.append((int(x * imshape[1]), int(y * imshape[0])))
    except Exception:
        valid_roi = []

    if len(valid_roi) >= 3:
        vertices = np.array([valid_roi], dtype=np.int32)
    else:
        vertices = np.array([[
            (10, imshape[0]),
            (imshape[1] * 5 / 34, imshape[0] * 2 / 3),
            (imshape[1] * 29 / 34, imshape[0] * 2 / 3),
            (imshape[1] - 20, imshape[0])
        ]], dtype=np.int32)

    mask = np.zeros_like(image)
    ignore_mask_color = 255 if len(image.shape) == 2 else (255,) * image.shape[2]
    cv.fillPoly(mask, vertices, ignore_mask_color)
    return cv.bitwise_and(image, mask), mask


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
    right_y_set, right_x_set, right_slope_set, right_intercept_set = [], [], [], []
    left_y_set, left_x_set, left_slope_set, left_intercept_set = [], [], [], []

    h, w = ref_shape[:2]
    middle_x = w // 2
    max_y = h

    draw_segments = []

    if not lines:
        return 0.0, draw_segments

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
        lindex = left_y_set.index(min(left_y_set))
        left_x_top = left_x_set[lindex]
        left_y_top = left_y_set[lindex]
        lslope = float(np.median(left_slope_set))
        lintercept = float(np.median(left_intercept_set))
        left_x_bottom = int(left_x_top + (max_y - left_y_top) / lslope)
        left_x_err = (max_y - 50 - lintercept) / lslope
        draw_segments.append({"x1": left_x_bottom, "y1": max_y, "x2": left_x_top, "y2": left_y_top})

    if right_y_set:
        rindex = right_y_set.index(min(right_y_set))
        right_x_top = right_x_set[rindex]
        right_y_top = right_y_set[rindex]
        rslope = float(np.median(right_slope_set))
        rintercept = float(np.median(right_intercept_set))
        right_x_bottom = int(right_x_top + (max_y - right_y_top) / rslope)
        right_x_err = (max_y - 50 - rintercept) / rslope
        draw_segments.append({"x1": right_x_top, "y1": right_y_top, "x2": right_x_bottom, "y2": max_y})

    if right_y_set and left_y_set:
        miderr_x = (right_x_err + left_x_err) / 2.0
        error = (middle_x - 10) - miderr_x
        error = max(min(error, 40), -40)
    else:
        error = 0.0

    return float(error), draw_segments


def process_image(frame_bgr: np.ndarray, params: Dict[str, Any]) -> Tuple[Dict[str, np.ndarray], float, Dict[str, Any]]:
    low = int(params.get("canny_low_threshold", 68))
    threshold = int(params.get("hof_threshold", 40))
    min_line_len = int(params.get("hof_min_line_len", 20))
    max_line_gap = int(params.get("hof_max_line_gap", 10))

    gray = grayscale(frame_bgr)
    blur = gaussian_blur(gray)
    edges = canny(blur, low)
    roi, mask = region_of_interest(edges, params)
    lines = hough_lines(roi, threshold, min_line_len, max_line_gap)
    filtered = bypass_angle_filter(lines)

    line_image = np.zeros_like(frame_bgr)
    err, draw_segments = draw_lines(line_image, filtered, frame_bgr.shape)
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
        "roi": [[int(p[0]), int(p[1])] for p in (vertices.tolist()[0] if len(vertices) > 0 else [])],
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
    }
