import time
from typing import Any, Dict, Tuple

import cv2 as cv
import numpy as np

# 透视矩阵缓存
_M = None
_M_inv = None
_src_pts = None

# 上一帧拟合系数
_prev_left_fit: Tuple[float, float, float] = ()
_prev_right_fit: Tuple[float, float, float] = ()

# 误差简单滤波
_filter_val = 0.0


def reset_vision_state():
    """清空缓存，避免卡死时需要重启。"""
    global _M, _M_inv, _src_pts, _prev_left_fit, _prev_right_fit, _filter_val
    _M = None
    _M_inv = None
    _src_pts = None
    _prev_left_fit = ()
    _prev_right_fit = ()
    _filter_val = 0.0


def _get_perspective_matrices(w: int, h: int):
    """计算鸟瞰变换矩阵，只算一次后缓存。"""
    global _M, _M_inv, _src_pts
    if _M is None or _M_inv is None or _src_pts is None:
        src = np.float32([
            [w * 0.1, h],
            [w * 0.9, h],
            [w * 0.4, h * 0.6],
            [w * 0.6, h * 0.6],
        ])
        dst = np.float32([
            [w * 0.2, h],
            [w * 0.8, h],
            [w * 0.2, 0],
            [w * 0.8, 0],
        ])
        _M = cv.getPerspectiveTransform(src, dst)
        _M_inv = cv.getPerspectiveTransform(dst, src)
        _src_pts = src
    return _M, _M_inv, _src_pts


def _fast_binary(image_bgr: np.ndarray, thresh: int) -> np.ndarray:
    """使用红通道 + Sobel X 提取垂直边缘并二值化。"""
    if image_bgr.ndim == 3:
        _, _, r = cv.split(image_bgr)
    else:
        r = image_bgr
    sobelx = cv.Sobel(r, cv.CV_16S, 1, 0)
    abs_sobelx = np.absolute(sobelx)
    maxv = np.max(abs_sobelx) or 1
    scaled = np.uint8(255 * abs_sobelx / maxv)
    _, binary = cv.threshold(scaled, thresh, 255, cv.THRESH_BINARY)
    # 形态学去噪：先闭运算连接断点，再开运算去掉孤立噪点
    kernel = np.ones((3, 3), np.uint8)
    binary = cv.morphologyEx(binary, cv.MORPH_CLOSE, kernel, iterations=1)
    binary = cv.morphologyEx(binary, cv.MORPH_OPEN, kernel, iterations=1)
    return binary


def _sliding_window_fit(binary_warped: np.ndarray):
    """滑动窗口寻找左右车道并二次拟合。"""
    global _prev_left_fit, _prev_right_fit
    h, w = binary_warped.shape

    # 只看图像下半区，且聚焦中间 80% 区域，避免旁车道/墙角干扰
    hist_region = binary_warped[h // 2:, :].copy()
    edge_margin = int(w * 0.1)
    hist_region[:, :edge_margin] = 0
    hist_region[:, w - edge_margin:] = 0
    histogram = np.sum(hist_region, axis=0)

    midpoint = int(w // 2)
    leftx_base = int(np.argmax(histogram[:midpoint]))
    rightx_base = int(np.argmax(histogram[midpoint:]) + midpoint)

    nwindows = 6
    window_height = int(h // nwindows)
    margin = 40
    minpix = 20

    nonzero = binary_warped.nonzero()
    nonzeroy = np.array(nonzero[0])
    nonzerox = np.array(nonzero[1])

    # 期望车道宽度限制，防止抓到旁边车道
    lane_width_min = int(w * 0.25)
    lane_width_max = int(w * 0.7)
    if (rightx_base - leftx_base) < lane_width_min or (rightx_base - leftx_base) > lane_width_max:
        # 若宽度异常，使用上一帧中心或默认中心对称
        if len(_prev_left_fit) and len(_prev_right_fit):
            base_y = h - 1
            leftx_base = int(_poly_points(_prev_left_fit, base_y))
            rightx_base = int(_poly_points(_prev_right_fit, base_y))
        else:
            offset = int(w * 0.18)
            leftx_base = midpoint - offset
            rightx_base = midpoint + offset

    leftx_current = leftx_base
    rightx_current = rightx_base

    # 若有上一帧拟合，限制窗口初始位置的漂移
    if len(_prev_left_fit) and len(_prev_right_fit):
        base_y = h - 1
        prev_left = int(_poly_points(_prev_left_fit, base_y))
        prev_right = int(_poly_points(_prev_right_fit, base_y))
        drift = int(w * 0.15)
        leftx_current = int(np.clip(leftx_current, prev_left - drift, prev_left + drift))
        rightx_current = int(np.clip(rightx_current, prev_right - drift, prev_right + drift))

    left_lane_inds = []
    right_lane_inds = []

    for window in range(nwindows):
        win_y_low = h - (window + 1) * window_height
        win_y_high = h - window * window_height
        win_xleft_low = leftx_current - margin
        win_xleft_high = leftx_current + margin
        win_xright_low = rightx_current - margin
        win_xright_high = rightx_current + margin

        good_left_inds = ((nonzeroy >= win_y_low) & (nonzeroy < win_y_high) &
                          (nonzerox >= win_xleft_low) & (nonzerox < win_xleft_high)).nonzero()[0]
        good_right_inds = ((nonzeroy >= win_y_low) & (nonzeroy < win_y_high) &
                           (nonzerox >= win_xright_low) & (nonzerox < win_xright_high)).nonzero()[0]

        left_lane_inds.append(good_left_inds)
        right_lane_inds.append(good_right_inds)

        if len(good_left_inds) > minpix:
            leftx_current = int(np.mean(nonzerox[good_left_inds]))
        if len(good_right_inds) > minpix:
            rightx_current = int(np.mean(nonzerox[good_right_inds]))

    left_lane_inds = np.concatenate(left_lane_inds)
    right_lane_inds = np.concatenate(right_lane_inds)

    leftx = nonzerox[left_lane_inds]
    lefty = nonzeroy[left_lane_inds]
    rightx = nonzerox[right_lane_inds]
    righty = nonzeroy[right_lane_inds]

    left_fit = _prev_left_fit if len(_prev_left_fit) else None
    right_fit = _prev_right_fit if len(_prev_right_fit) else None

    if len(leftx) > 50:
        left_fit = np.polyfit(lefty, leftx, 2)
        _prev_left_fit = left_fit
    if len(rightx) > 50:
        right_fit = np.polyfit(righty, rightx, 2)
        _prev_right_fit = right_fit

    return left_fit, right_fit


def _poly_points(fit, y_vals):
    return fit[0] * y_vals ** 2 + fit[1] * y_vals + fit[2]


def process_image(frame_bgr: np.ndarray, params: Dict[str, Any]) -> Tuple[Dict[str, np.ndarray], float, Dict[str, Any]]:
    """滑窗+鸟瞰+二次拟合的车道检测，输出多路图像和覆盖数据。"""
    global _filter_val
    h, w = frame_bgr.shape[:2]
    thresh = int(params.get("binary_value", 40))

    # 1) 快速二值
    binary = _fast_binary(frame_bgr, thresh)

    # 2) 透视变换成鸟瞰
    M, M_inv, src_pts = _get_perspective_matrices(w, h)
    warped = cv.warpPerspective(binary, M, (w, h), flags=cv.INTER_LINEAR)

    # 3) 滑动窗口 + 拟合
    left_fit, right_fit = _sliding_window_fit(warped)
    if left_fit is None:
        left_fit = _prev_left_fit if len(_prev_left_fit) else [0, 0, w * 0.35]
    if right_fit is None:
        right_fit = _prev_right_fit if len(_prev_right_fit) else [0, 0, w * 0.65]

    ploty = np.linspace(0, h - 1, h)
    left_fitx = _poly_points(left_fit, ploty)
    right_fitx = _poly_points(right_fit, ploty)

    # 4) 误差（底部往上一点）
    eval_y = h - 20
    lane_center = (_poly_points(left_fit, eval_y) + _poly_points(right_fit, eval_y)) / 2.0
    screen_center = w / 2.0
    err_raw = screen_center - lane_center
    alpha = 0.3
    _filter_val = _filter_val * (1 - alpha) + err_raw * alpha
    err = float(np.clip(_filter_val, -120, 120))

    # 5) 鸟瞰可视化
    warp_zero = np.zeros_like(warped).astype(np.uint8)
    color_warp = np.dstack((warp_zero, warp_zero, warp_zero))
    pts_left = np.array([np.transpose(np.vstack([left_fitx, ploty]))])
    pts_right = np.array([np.flipud(np.transpose(np.vstack([right_fitx, ploty])))])
    pts = np.hstack((pts_left, pts_right))
    cv.fillPoly(color_warp, np.int_([pts]), (0, 255, 0))
    cv.polylines(color_warp, np.int_([pts_left]), False, (0, 0, 255), 4)
    cv.polylines(color_warp, np.int_([pts_right]), False, (255, 0, 0), 4)
    processed_bird = cv.addWeighted(np.dstack([warped, warped, warped]), 1, color_warp, 0.3, 0)

    # 6) 反投影到原图坐标用于前端覆盖
    sample_y = np.linspace(h * 0.3, h, num=12)
    left_pts = np.vstack([_poly_points(left_fit, sample_y), sample_y]).T.reshape(-1, 1, 2)
    right_pts = np.vstack([_poly_points(right_fit, sample_y), sample_y]).T.reshape(-1, 1, 2)
    left_unwarp = cv.perspectiveTransform(left_pts.astype(np.float32), M_inv)
    right_unwarp = cv.perspectiveTransform(right_pts.astype(np.float32), M_inv)

    def _segments_from_poly(unwarped_pts):
        segs = []
        pts = unwarped_pts.reshape(-1, 2)
        for i in range(len(pts) - 1):
            x1, y1 = pts[i]
            x2, y2 = pts[i + 1]
            segs.append({"x1": int(x1), "y1": int(y1), "x2": int(x2), "y2": int(y2)})
        return segs

    line_segments = _segments_from_poly(left_unwarp) + _segments_from_poly(right_unwarp)

    # 输出帧
    gray_bgr = cv.cvtColor(binary, cv.COLOR_GRAY2BGR)
    warped_bgr = cv.cvtColor(warped, cv.COLOR_GRAY2BGR)

    imgs = {
        "raw": frame_bgr,
        "gray": gray_bgr,
        "blur": gray_bgr,
        "canny": gray_bgr,
        "roi": warped_bgr,          # ROI 视角：鸟瞰二值
        "processed": processed_bird  # Processed：带拟合的鸟瞰
    }

    overlay = {
        "roi": [[int(p[0]), int(p[1])] for p in _src_pts.tolist()],
        "lines": [],  # 不再传直线段，前端专注曲线
        "curves": {
            "left": [[int(p[0]), int(p[1])] for p in left_unwarp.reshape(-1, 2).tolist()],
            "right": [[int(p[0]), int(p[1])] for p in right_unwarp.reshape(-1, 2).tolist()],
        },
        "frame": {"w": int(w), "h": int(h)},
        "err": float(err),
        "roi_source": "birdview",
    }

    return imgs, err, overlay
