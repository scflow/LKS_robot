export interface RobotParams {
  binary_value: number;
  canny_low_threshold: number;
  hof_threshold: number;
  hof_min_line_len: number;
  hof_max_line_gap: number;

  auto_drive: number; // 0/1
  steer_k: number;
  steer_invert: number;

  // 速度控制
  speed_mode: number; // 0: linear, 1: PID
  motor_base: number;
  motor_k: number;
  speed_target: number;
  speed_kp: number;
  speed_ki: number;
  speed_kd: number;
  speed_dt: number;
  speed_slowdown_gain: number;

  // 手动 & 底盘
  manual_motor: number;
  manual_servo: number;
  scs_mode: number;
  headlight: number;

  roi_points: number[][];
}

export interface RobotStatus {
  fps: number;
  err: number;
  servo_position: number;
  motor_duty: number;
  running: boolean;
  camera_connected: boolean;
  chassis_connected: boolean;
  chassis_error: string;
  camera_error?: string;
  mode: 'auto' | 'manual';
  overlay?: any;
}
