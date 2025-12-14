import time
import threading
from typing import Dict
import platform

import cv2 as cv
import numpy as np

from chassis import CHASSIS_PORT, chassis
from control import compute_control, latest_frames, latest_status, latest_overlay, lock, params
from vision import process_image


def _open_capture(preferred_index, width, height):
    """Try a couple of camera indices/backends and return the first opened capture."""
    tried = []
    for idx in ([preferred_index] + ([0] if preferred_index != 0 else [])):
        # Try with V4L2 first on Linux, otherwise skip to default backend.
        if platform.system().lower() == "linux":
            cap = cv.VideoCapture(idx, cv.CAP_V4L2)
            tried.append(f"{idx}(v4l2)")
            if cap.isOpened():
                cap.set(cv.CAP_PROP_FRAME_WIDTH, width)
                cap.set(cv.CAP_PROP_FRAME_HEIGHT, height)
                cap.set(cv.CAP_PROP_FOURCC, cv.VideoWriter_fourcc(*"MJPG"))
                return cap, idx, tried
            cap.release()
        # macOS: AVFoundation backend
        if platform.system().lower() == "darwin":
            cap = cv.VideoCapture(idx, cv.CAP_AVFOUNDATION)
            tried.append(f"{idx}(avfoundation)")
            if cap.isOpened():
                cap.set(cv.CAP_PROP_FRAME_WIDTH, width)
                cap.set(cv.CAP_PROP_FRAME_HEIGHT, height)
                cap.set(cv.CAP_PROP_FOURCC, cv.VideoWriter_fourcc(*"MJPG"))
                return cap, idx, tried
            cap.release()
        cap = cv.VideoCapture(idx)
        tried.append(f"{idx}(default)")
        if cap.isOpened():
            cap.set(cv.CAP_PROP_FRAME_WIDTH, width)
            cap.set(cv.CAP_PROP_FRAME_HEIGHT, height)
            cap.set(cv.CAP_PROP_FOURCC, cv.VideoWriter_fourcc(*"MJPG"))
            return cap, idx, tried
        cap.release()
    return None, None, tried


def camera_loop(camera_index=0, width=320, height=240):
    cap, used_idx, tried = _open_capture(camera_index, width, height)

    with lock:
        latest_status["running"] = True
        ok_open = cap is not None and cap.isOpened()
        latest_status["camera_connected"] = ok_open
        if ok_open:
            latest_status["camera_error"] = ""
        else:
            latest_status["camera_error"] = f"open camera failed, tried: {', '.join(tried)}"

    ok = chassis.open()
    with lock:
        latest_status["chassis_connected"] = bool(ok)
        latest_status["chassis_error"] = "" if ok else f"open {CHASSIS_PORT} failed: {chassis.last_error}"

    last_t = time.time()
    frames_in_window = 0
    fps = 0.0

    while True:
        try:
            ok, frame = cap.read()
            if not ok or frame is None:
                frame = np.zeros((height, width, 3), dtype=np.uint8)
                with lock:
                    latest_status["camera_connected"] = False
                    latest_status["camera_error"] = "no frame"
            else:
                with lock:
                    latest_status["camera_connected"] = True
                    latest_status["camera_error"] = ""

            with lock:
                local_params: Dict = dict(params)

            imgs, err, overlay = process_image(frame, local_params)
            motor_duty, servo_pos, scs_mode, headlight, mode = compute_control(err)

            if not chassis.is_open():
                if chassis.open():
                    with lock:
                        latest_status["chassis_connected"] = True
                        latest_status["chassis_error"] = ""
                else:
                    motor_duty = 0.0
                    with lock:
                        latest_status["chassis_connected"] = False
                        latest_status["chassis_error"] = f"open {CHASSIS_PORT} failed: {chassis.last_error}"

            if chassis.is_open():
                try:
                    chassis.send(motor_duty, servo_pos, scs_mode, headlight)
                    with lock:
                        latest_status["chassis_connected"] = True
                        latest_status["chassis_error"] = ""
                except Exception as e:
                    with lock:
                        latest_status["chassis_connected"] = False
                        latest_status["chassis_error"] = str(e)

            frames_in_window += 1
            now = time.time()
            dt = now - last_t
            if dt >= 0.5:
                fps = frames_in_window / dt
                frames_in_window = 0
                last_t = now

            with lock:
                latest_frames.update(imgs)
                latest_status["fps"] = float(fps)
                latest_status["err"] = float(err)
                latest_status["servo_position"] = int(servo_pos)
                latest_status["motor_duty"] = float(motor_duty)
                latest_status["mode"] = mode
                latest_overlay.update(overlay)

        except Exception as e:
            with lock:
                latest_status["camera_error"] = str(e)
                latest_status["camera_connected"] = False
            time.sleep(0.05)
        time.sleep(0.01)


def mjpeg_stream(name: str):
    while True:
        with lock:
            img = latest_frames.get(name, None)

        if img is None:
            placeholder = np.zeros((240, 320, 3), dtype=np.uint8)
            cv.putText(placeholder, f"Waiting: {name}", (10, 120),
                       cv.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            ok, jpg = cv.imencode(".jpg", placeholder, [int(cv.IMWRITE_JPEG_QUALITY), 80])
        else:
            ok, jpg = cv.imencode(".jpg", img, [int(cv.IMWRITE_JPEG_QUALITY), 80])

        if not ok:
            continue

        yield (b"--frame\r\n"
               b"Content-Type: image/jpeg\r\n\r\n" + jpg.tobytes() + b"\r\n")
        time.sleep(0.03)


def start_camera_thread():
    th = threading.Thread(
        target=camera_loop,
        kwargs={"camera_index": 0, "width": 320, "height": 240},
        daemon=True
    )
    th.start()
    return th
