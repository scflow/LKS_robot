from flask import Flask, Response, jsonify, request, send_from_directory

from camera import mjpeg_stream, start_camera_thread
from chassis import CENTER_POSITION
from control import PARAM_TYPES, latest_overlay, latest_status, lock, params

app = Flask(__name__)


@app.route("/")
def index():
    return send_from_directory("templates", "index.html")


@app.route("/app.css")
def app_css():
    return send_from_directory("templates", "app.css")


@app.route("/app.js")
def app_js():
    return send_from_directory("templates", "app.js")


@app.route("/stream/<name>")
def stream(name: str):
    if name not in {"raw", "gray", "blur", "canny", "roi", "processed"}:
        return "unknown stream", 404
    return Response(mjpeg_stream(name),
                    mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/api/params", methods=["GET"])
def get_params():
    with lock:
        return jsonify(dict(params))


@app.route("/api/params", methods=["POST"])
def set_params():
    data = request.get_json(force=True, silent=True) or {}
    changed = {}

    with lock:
        for k, t in PARAM_TYPES.items():
            if k not in data:
                continue
            try:
                if t == "int":
                    params[k] = int(float(data[k]))
                elif t == "list":
                    # 只接受二维点列表，并归一化为 float
                    pts = []
                    if isinstance(data[k], list):
                        for p in data[k]:
                            if not isinstance(p, (list, tuple)) or len(p) != 2:
                                continue
                            x = float(p[0])
                            y = float(p[1])
                            pts.append([x, y])
                    params[k] = pts
                else:
                    params[k] = float(data[k])
                changed[k] = params[k]
            except Exception:
                pass

    return jsonify({"ok": True, "changed": changed, "params": params})


@app.route("/api/status", methods=["GET"])
def get_status():
    with lock:
        data = dict(latest_status)
        data["overlay"] = latest_overlay
        return jsonify(data)


@app.route("/api/estop", methods=["POST"])
def estop():
    """急停：把手动值置 0，并强制切到 manual"""
    with lock:
        params["auto_drive"] = 0
        params["manual_motor"] = 0.0
        params["manual_servo"] = CENTER_POSITION
    return jsonify({"ok": True, "auto_drive": 0, "manual_motor": 0.0, "manual_servo": CENTER_POSITION})


if __name__ == "__main__":
    start_camera_thread()
    app.run(host="0.0.0.0", port=5001, debug=False, threaded=True)
