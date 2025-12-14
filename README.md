### 智能汽车综合实践课程设计代码

一个基于 Flask + OpenCV 的小车巡线/遥控控制台。后端负责采集摄像头、视觉处理、控制信号下发，前端提供参数调节、状态展示和 ROI 编辑。

#### 运行方式
- 安装依赖：`pip install flask opencv-python numpy pyserial`（需要 USB 摄像头和串口驱动）。
- 启动服务：`python3 app.py`（或 `bash start.sh`）。默认监听 `0.0.0.0:5001`。
- 浏览器访问 `http://<设备IP>:5001`，即可看到控制台。

#### 运行逻辑概览
- **入口 (app.py)**：启动 Flask，暴露视频流 `/stream/<name>`（raw/gray/blur/canny/roi/processed），参数接口 `/api/params`，状态接口 `/api/status`，急停 `/api/estop`，以及静态前端页面。
- **摄像头与循环 (camera.py)**：`start_camera_thread()` 开启后台线程 `camera_loop`，用 V4L2 拉取 320x240 帧。每帧读取当前参数，调用视觉模块处理后得到错误值 `err` 和覆盖信息，再调用 `compute_control` 生成电机占空比、舵机位置、底盘模式与车灯开关。
- **底盘控制 (chassis.py)**：通过 `/dev/ttyTHS1` 串口与底盘通信，按固定协议打包占空比、舵机、模式和灯光数据，周期性发送；失败时记录 `latest_status["chassis_error"]` 并清空输出。
- **自动/手动策略 (control.py)**：`compute_control(err)` 根据 `params` 判断模式。`auto_drive=1` 时：舵机 = `steer_center + steer_k * err * steer_invert`（限幅 800-2200），速度 = `motor_base - motor_k*|err|`（限幅 0~0.2）；`auto_drive=0` 时持续发送 `manual_motor`、`manual_servo`。所有值通过锁保护的共享状态下发给底盘线程。
- **视觉处理 (vision.py)**：灰度 -> 高斯滤波 -> Canny -> ROI 裁剪（默认梯形或前端下发的 ROI 顶点） -> HoughLinesP 找线，过滤角度后计算左右车道线与车身中心的横向误差 `err`。输出多路可视化帧（raw/gray/blur/canny/roi/processed）和 ROI/线段覆盖数据。
- **前端 (templates)**：`index.html` + `app.js` 轮询 `/api/status` 更新 FPS、误差、串口状态与覆盖图层；实时提交滑块参数到 `/api/params`；支持手动模式输入、急停按钮、视频流切换、全屏。ROI 编辑支持点击添加点、双击/按钮收尾发送，清除按钮重置 ROI。
- **安全与急停**：`/api/estop` 将 `auto_drive` 置 0，速度清零、舵机回中，确保进入手动停机状态。

#### 目录
- `app.py`：Flask 入口与路由。
- `camera.py`：摄像头采集、调用视觉/控制、更新状态。
- `vision.py`：图像处理与误差计算。
- `control.py`：共享参数、状态、控制计算。
- `chassis.py`：底盘串口协议与发送线程。
- `templates/`：前端页面、样式与交互脚本。
- `start.sh`：简单启动脚本；`test.py`：串口发送 Demo。
