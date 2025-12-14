import { onMounted, onUnmounted, reactive, ref } from 'vue'
import type { RobotParams, RobotStatus } from '../types'

const DEFAULT_STATUS: RobotStatus = {
  fps: 0,
  err: 0,
  servo_position: 1500,
  motor_duty: 0,
  running: false,
  camera_connected: false,
  chassis_connected: false,
  chassis_error: '',
  mode: 'manual',
  overlay: null,
}

export function useRobot() {
  const status = ref<RobotStatus>({ ...DEFAULT_STATUS })
  const isConnected = ref(true)
  const params = reactive<RobotParams>({
    binary_value: 90,
    canny_low_threshold: 68,
    hof_threshold: 40,
    hof_min_line_len: 20,
    hof_max_line_gap: 10,
    auto_drive: 0,
    steer_mode: 0,
    steer_k: 8,
    steer_invert: 1,
    steer_center: 1500,
    lqr_q1: 5,
    lqr_q2: 1,
    lqr_r: 0.8,
    lqr_dt: 0.05,
    lqr_velocity: 0.6,
    speed_mode: 0,
    motor_base: 0.1,
    motor_k: 0.002,
    speed_target: 0.1,
    speed_kp: 0.6,
    speed_ki: 0.1,
    speed_kd: 0.02,
    speed_dt: 0.02,
    speed_slowdown_gain: 0.002,
    manual_motor: 0,
    manual_servo: 1500,
    scs_mode: 0,
    headlight: 0,
    roi_points: [],
  } as RobotParams)

  const fetchStatus = async () => {
    try {
      const res = await fetch('/api/status')
      const data = await res.json()
      status.value = data
      isConnected.value = true
    } catch (err) {
      console.error('fetchStatus error', err)
      isConnected.value = false
    }
  }

  const loadParams = async () => {
    try {
      const res = await fetch('/api/params')
      const data = await res.json()
      Object.assign(params, data)
    } catch (err) {
      console.error('loadParams error', err)
    }
  }

  const syncParams = async (partial: Partial<RobotParams>) => {
    try {
      await fetch('/api/params', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(partial),
      })
      Object.assign(params, partial)
    } catch (err) {
      console.error('syncParams error', err)
    }
  }

  const estop = async () => {
    try {
      await fetch('/api/estop', { method: 'POST' })
      await loadParams()
    } catch (err) {
      console.error('estop error', err)
    }
  }

  let timer: number | undefined
  onMounted(async () => {
    await loadParams()
    await fetchStatus()
    timer = window.setInterval(fetchStatus, 220)
  })
  onUnmounted(() => {
    if (timer) window.clearInterval(timer)
  })

  return { status, params, syncParams, estop, loadParams, isConnected }
}
