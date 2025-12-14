import time
import threading
from typing import Dict

import cv2 as cv
import numpy as np

from chassis import CHASSIS_PORT, chassis
from control import compute_control, latest_frames, latest_status, latest_overlay, lock, params
from vision import process_image


def camera_loop(camera_index=0, width=320, height=240):
    cap = cv.VideoCapture(camera_index, cv.CAP_V4L2)
    cap.set(cv.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv.CAP_PROP_FOURCC, cv.VideoWriter_fourcc(*"MJPG"))

    with lock:
        latest_status["running"] = True

    ok = chassis.open()
    with lock:
        latest_status["chassis_connected"] = bool(ok)
        latest_status["chassis_error"] = "" if ok else f"open {CHASSIS_PORT} failed: {chassis.last_error}"

    last_t = time.time()
    frames_in_window = 0
    fps = 0.0

    while True:
        ok, frame = cap.read()
        if not ok or frame is None:
            frame = np.zeros((height, width, 3), dtype=np.uint8)
            cv.putText(frame, "Camera not ready", (10, height // 2),
                       cv.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

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
