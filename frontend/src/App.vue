<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import type { Ref } from 'vue'
import { useRobot } from './composables/useRobot'
import type { RobotParams, RobotStatus } from './types'
import DynamicIsland from './components/DynamicIsland.vue'
import StatusGrid from './components/StatusGrid.vue'
import PrecisionControl from './components/PrecisionControl.vue'

const robot = useRobot()
const statusRef = robot.status as Ref<RobotStatus>
const params = robot.params
const syncParams = robot.syncParams
const estop = robot.estop
const isConnected = robot.isConnected

const streamSrc = ref('/stream/raw')
const selectedStream = ref('raw')
const errCanvas = ref<HTMLCanvasElement | null>(null)
const speedCanvas = ref<HTMLCanvasElement | null>(null)
const errHistory = ref<number[]>([])
const speedHistory = ref<number[]>([])
const maxPoints = 120
const streamError = ref(false)
const overlayDismissed = ref(false)
const showCameraLost = computed(() => streamError.value || !statusRef.value.camera_connected)

const dataTheme = ref('dark')
onMounted(() => {
  const t = document.documentElement.getAttribute('data-theme')
  dataTheme.value = t || 'dark'
})

const updateParam = (key: keyof RobotParams, val: number) => {
  syncParams({ [key]: val } as Partial<RobotParams>)
}

const statusTiles = computed(() => [
  { label: 'MODE', value: (statusRef.value.mode || 'auto').toString().toUpperCase() },
  { label: 'FPS', value: statusRef.value.fps.toFixed(1) },
  { label: 'OFFSET', value: statusRef.value.err.toFixed(2) },
  { label: 'STEERING', value: statusRef.value.servo_position.toString() },
  { label: 'THROTTLE', value: statusRef.value.motor_duty.toFixed(2) },
])

const changeStream = () => {
  streamSrc.value = `/stream/${selectedStream.value}?t=${Date.now()}`
  streamError.value = false
}

const pushHistory = (arr: number[], val: number) => {
  arr.push(val)
  if (arr.length > maxPoints) arr.shift()
}

const drawSparkline = (canvas: HTMLCanvasElement | null, data: number[], opts: { min?: number; max?: number; color?: string } = {}) => {
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  const w = canvas.width
  const h = canvas.height
  ctx.clearRect(0, 0, w, h)
  if (!data.length) return
  const values = data
  const min = opts.min ?? Math.min(...values)
  const max = opts.max ?? Math.max(...values)
  const range = max - min || 1
  const step = values.length > 1 ? w / (values.length - 1) : w
  const baseColor = opts.color || '#007aff'
  const grad = ctx.createLinearGradient(0, 0, 0, h)
  grad.addColorStop(0, `${baseColor}33`)
  grad.addColorStop(1, `${baseColor}00`)

  ctx.beginPath()
  values.forEach((v, i) => {
    const x = i * step
    const y = h - ((v - min) / range) * h
    if (i === 0) ctx.moveTo(x, y)
    else ctx.lineTo(x, y)
  })
  ctx.lineTo(w, h)
  ctx.lineTo(0, h)
  ctx.closePath()
  ctx.fillStyle = grad
  ctx.fill()

  ctx.strokeStyle = baseColor
  ctx.lineWidth = 2
  ctx.beginPath()
  values.forEach((v, i) => {
    const x = i * step
    const y = h - ((v - min) / range) * h
    if (i === 0) ctx.moveTo(x, y)
    else ctx.lineTo(x, y)
  })
  ctx.stroke()

  ctx.strokeStyle = 'rgba(128,128,128,0.15)'
  ctx.lineWidth = 1
  ctx.setLineDash([4, 4])
  ;[0.25, 0.5, 0.75].forEach(r => {
    const y = h * r
    ctx.beginPath()
    ctx.moveTo(0, y)
    ctx.lineTo(w, y)
    ctx.stroke()
  })
  ctx.setLineDash([])
}

const handleStreamError = () => {
  streamError.value = true
}

const handleStreamLoad = () => {
  streamError.value = false
}

const restartStream = () => {
  streamError.value = false
  streamSrc.value = `/stream/${selectedStream.value}?t=${Date.now()}`
}

const showOverlay = computed(() => !isConnected.value && !overlayDismissed.value)
const dismissOverlay = () => {
  overlayDismissed.value = true
}

watch(
  () => ({ err: statusRef.value.err, motor: statusRef.value.motor_duty }),
  ({ err, motor }) => {
    pushHistory(errHistory.value, err)
    pushHistory(speedHistory.value, motor)
    drawSparkline(errCanvas.value, errHistory.value, { min: -40, max: 40, color: '#00c7be' })
    drawSparkline(speedCanvas.value, speedHistory.value, { min: 0, max: 0.2, color: '#ff9f0a' })
  }
)

onUnmounted(() => {
  errHistory.value = []
  speedHistory.value = []
})
</script>

<template>
  <div class="ipad-layout" :data-theme="dataTheme">
    <div class="stage-area">
      <div class="stage-card">
        <div class="video-header">
          <h3>视频流</h3>
          <select id="streamSelect" class="select" v-model="selectedStream" @change="changeStream">
            <option value="raw" selected>Raw</option>
            <option value="processed">Processed</option>
            <option value="gray">Gray</option>
            <option value="blur">Blur</option>
            <option value="canny">Canny</option>
            <option value="roi">ROI</option>
          </select>
        </div>
        <div class="video-wrap">
          <DynamicIsland :err="statusRef.err" />
          <img id="streamImage" :src="streamSrc" alt="stream" @error="handleStreamError" @load="handleStreamLoad" />
          <canvas id="overlay" class="overlay-canvas"></canvas>
          <div class="video-fallback" v-if="showCameraLost">
            <div class="fallback-icon">⚠</div>
            <div class="fallback-text">{{ statusRef.camera_error || 'VIDEO SIGNAL LOST' }}</div>
            <button class="secondary" @click="restartStream">重试/重启摄像头</button>
          </div>
          <div class="ribbon-overlay">
            <div class="metric">
              <div class="metric-title">横向误差</div>
              <canvas id="errChart" ref="errCanvas" height="80"></canvas>
            </div>
            <div class="metric">
              <div class="metric-title">速度 (duty)</div>
              <canvas id="speedChart" ref="speedCanvas" height="80"></canvas>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="inspector-panel">
      <div class="pill-row">
        <span class="pill" :class="isConnected ? 'ok' : 'warn'">{{ isConnected ? 'SYSTEM ONLINE' : 'DISCONNECTED' }}</span>
        <span class="pill" :class="statusRef.camera_connected ? 'ok' : 'warn'">{{ statusRef.camera_connected ? 'CAMERA OK' : 'CAMERA LOST' }}</span>
        <span class="pill" :class="statusRef.chassis_connected ? 'ok' : 'warn'">{{ statusRef.chassis_connected ? 'CHASSIS OK' : 'CHASSIS ERROR' }}</span>
        <span class="pill">{{ (statusRef.mode || 'manual').toUpperCase() }} MODE</span>
      </div>
      <div class="sidebar-scroll">
        <div class="card">
          <h3>状态</h3>
          <StatusGrid :tiles="statusTiles" :chassis-ok="statusRef.chassis_connected" :chassis-error="statusRef.chassis_error" />
          <div class="section">
            <div class="flex">
              <button id="btnAuto" :class="statusRef.mode === 'auto' ? '' : 'ghost'" @click="() => updateParam('auto_drive', 1)">切换：Auto</button>
              <button id="btnManual" :class="statusRef.mode === 'manual' ? '' : 'ghost'" @click="() => updateParam('auto_drive', 0)">切换：Manual</button>
              <button id="btnEstop" class="danger" @click="estop">急停 (E-STOP)</button>
            </div>
          </div>
        </div>

        <div class="card">
          <h3>视觉参数</h3>
          <div class="stack">
            <PrecisionControl label="binary_value" :min="0" :max="255" :step="1" v-model="params.binary_value" @change="val => updateParam('binary_value', val)" />
            <PrecisionControl label="canny_low_threshold" :min="0" :max="255" :step="1" v-model="params.canny_low_threshold" @change="val => updateParam('canny_low_threshold', val)" />
            <PrecisionControl label="hof_threshold" :min="0" :max="255" :step="1" v-model="params.hof_threshold" @change="val => updateParam('hof_threshold', val)" />
            <PrecisionControl label="hof_min_line_len" :min="0" :max="255" :step="1" v-model="params.hof_min_line_len" @change="val => updateParam('hof_min_line_len', val)" />
            <PrecisionControl label="hof_max_line_gap" :min="0" :max="255" :step="1" v-model="params.hof_max_line_gap" @change="val => updateParam('hof_max_line_gap', val)" />
          </div>
        </div>

        <div class="card">
          <h3>自动控制参数（转向）</h3>
          <div class="stack">
            <div class="field">
              <label>转向模式</label>
              <div>
                <select class="select" :value="params.steer_mode" @change="e => updateParam('steer_mode', Number((e.target as HTMLSelectElement).value))">
                  <option value="0">比例 (Kp)</option>
                  <option value="1">LQR</option>
                </select>
              </div>
            </div>
            <PrecisionControl label="steer_center" :min="800" :max="2200" :step="1" v-model="params.steer_center" @change="val => updateParam('steer_center', val)" />
            <PrecisionControl label="steer_invert (1/-1)" :min="-1" :max="1" :step="2" v-model="params.steer_invert" @change="val => updateParam('steer_invert', val)" />
            <div v-show="params.steer_mode === 0" class="stack">
              <PrecisionControl label="steer_k" :min="0" :max="30" :step="0.1" v-model="params.steer_k" @change="val => updateParam('steer_k', val)" />
            </div>
            <div v-show="params.steer_mode === 1" class="stack">
              <PrecisionControl label="lqr_q1" :min="0.1" :max="20" :step="0.1" v-model="params.lqr_q1" @change="val => updateParam('lqr_q1', val)" />
              <PrecisionControl label="lqr_q2" :min="0.1" :max="20" :step="0.1" v-model="params.lqr_q2" @change="val => updateParam('lqr_q2', val)" />
              <PrecisionControl label="lqr_r" :min="0.1" :max="10" :step="0.1" v-model="params.lqr_r" @change="val => updateParam('lqr_r', val)" />
              <PrecisionControl label="lqr_dt" :min="0.01" :max="0.2" :step="0.005" v-model="params.lqr_dt" @change="val => updateParam('lqr_dt', val)" />
              <PrecisionControl label="lqr_velocity" :min="0.1" :max="2" :step="0.05" v-model="params.lqr_velocity" @change="val => updateParam('lqr_velocity', val)" />
            </div>
          </div>
        </div>

        <div class="card">
          <h3>速度控制</h3>
          <div class="stack">
            <div class="field">
              <label>模式</label>
              <div>
                <select id="speed_mode" class="select" :value="params.speed_mode" @change="e => updateParam('speed_mode', Number((e.target as HTMLSelectElement).value))">
                  <option value="0">线性降速</option>
                  <option value="1">PID 调速</option>
                </select>
              </div>
            </div>
            <div id="speed_linear" class="stack speed-group" v-show="params.speed_mode === 0">
              <PrecisionControl label="motor_base" :min="0" :max="0.2" :step="0.01" v-model="params.motor_base" @change="val => updateParam('motor_base', val)" />
              <PrecisionControl label="motor_k" :min="0" :max="0.01" :step="0.0005" v-model="params.motor_k" @change="val => updateParam('motor_k', val)" />
            </div>
            <div id="speed_pid" class="stack speed-group" v-show="params.speed_mode === 1">
              <PrecisionControl label="speed_target" :min="0" :max="0.2" :step="0.005" v-model="params.speed_target" @change="val => updateParam('speed_target', val)" />
              <PrecisionControl label="speed_slowdown_gain" :min="0" :max="0.01" :step="0.0005" v-model="params.speed_slowdown_gain" @change="val => updateParam('speed_slowdown_gain', val)" />
              <PrecisionControl label="speed_kp" :min="0" :max="2" :step="0.05" v-model="params.speed_kp" @change="val => updateParam('speed_kp', val)" />
              <PrecisionControl label="speed_ki" :min="0" :max="1" :step="0.02" v-model="params.speed_ki" @change="val => updateParam('speed_ki', val)" />
              <PrecisionControl label="speed_kd" :min="0" :max="0.2" :step="0.005" v-model="params.speed_kd" @change="val => updateParam('speed_kd', val)" />
              <PrecisionControl label="speed_dt" :min="0.005" :max="0.1" :step="0.005" v-model="params.speed_dt" @change="val => updateParam('speed_dt', val)" />
            </div>
          </div>
        </div>

        <div class="card">
          <h3>手动控制</h3>
          <div class="stack">
            <PrecisionControl label="manual_motor (duty)" :min="-0.2" :max="0.2" :step="0.01" v-model="params.manual_motor" @change="val => updateParam('manual_motor', val)" />
            <PrecisionControl label="manual_servo (pos)" :min="800" :max="2200" :step="1" v-model="params.manual_servo" @change="val => updateParam('manual_servo', val)" />
          </div>
          <div class="section">
            <div class="input-inline">
              <label>速度(duty)</label>
              <input id="manual_motor_input" class="text-input" type="number" step="0.01" min="-0.2" max="0.2" :value="params.manual_motor" @change="e => updateParam('manual_motor', Number((e.target as HTMLInputElement).value))" />
              <label>转角(servo)</label>
              <input id="manual_servo_input" class="text-input" type="number" step="1" min="800" max="2200" :value="params.manual_servo" @change="e => updateParam('manual_servo', Number((e.target as HTMLInputElement).value))" />
              <button id="btnApplyManual" class="secondary" @click="() => updateParam('auto_drive', 0)">应用并切换 Manual</button>
            </div>
          </div>
        </div>

        <div class="card">
          <h3>底盘</h3>
          <div class="stack">
            <PrecisionControl label="scs_mode" :min="0" :max="2" :step="1" v-model="params.scs_mode" @change="val => updateParam('scs_mode', val)" />
            <PrecisionControl label="headlight" :min="0" :max="1" :step="1" v-model="params.headlight" @change="val => updateParam('headlight', val)" />
          </div>
        </div>
      </div>
    </div>

    <div class="system-overlay" v-if="showOverlay">
      <div class="overlay-card">
        <div class="spinner"></div>
        <div class="overlay-text">CONNECTING TO VEHICLE...</div>
        <button class="secondary" @click="dismissOverlay">继续离线查看</button>
      </div>
    </div>
  </div>
</template>
