const keys = [
  "binary_value","canny_low_threshold","hof_threshold","hof_min_line_len","hof_max_line_gap",
  "auto_drive","steer_k","steer_invert",
  "speed_mode","motor_base","motor_k",
  "speed_target","speed_slowdown_gain","speed_kp","speed_ki","speed_kd","speed_dt",
  "manual_motor","manual_servo","scs_mode","headlight"
];

const api = {
  async loadParams() {
    const res = await fetch("/api/params");
    return res.json();
  },
  async postParams(payload) {
    await fetch("/api/params", {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify(payload)
    });
  },
  async estop() {
    await fetch("/api/estop", { method: "POST" });
  },
  async loadStatus() {
    const res = await fetch("/api/status");
    return res.json();
  }
};

const ui = (() => {
  let postTimer = null;
  let streamSelect;
  let streamImage;
  let overlay;
  let editing = false;
  let roiPoints = [];
  let videoWrap;
  let backendOverlay = null;
  let camDot;
  let camText;
  let camChip;
  let themeBtn;
  let themeIcon;
  let speedLinear;
  let speedPid;
  let islandDot;
  let islandValue;
  let errChart;
  let speedChart;
  const errHistory = [];
  const speedHistory = [];
  const MAX_POINTS = 120;

  function setVal(id, v) {
    const el = document.getElementById(id);
    const out = document.getElementById(id + "_val");
    if (el) el.value = v;
    if (out) out.textContent = v;
    if (id === "auto_drive") document.getElementById("auto_drive_val").textContent = v;
  }

  function updateToggleBtn(v){
    const btn = document.getElementById("btnToggle");
    btn.textContent = `切换：${parseInt(v,10)===1 ? "Auto" : "Manual"}`;
  }

  function updateStream() {
    const stream = streamSelect.value;
    streamImage.src = `/stream/${stream}?t=${Date.now()}`;
  }

  function resizeCanvas() {
    if (!overlay || !streamImage) return;
    const rect = streamImage.getBoundingClientRect();
    overlay.width = rect.width;
    overlay.height = rect.height;
  }

  function drawOverlay() {
    if (!overlay) return;
    const ctx = overlay.getContext("2d");
    ctx.clearRect(0, 0, overlay.width, overlay.height);
    const w = overlay.width;
    const h = overlay.height;

    // 后端提供的检测线段
    if (backendOverlay && backendOverlay.frame && backendOverlay.frame.w > 0) {
      const sx = w / backendOverlay.frame.w;
      const sy = h / backendOverlay.frame.h;
      ctx.lineWidth = 3;
      ctx.strokeStyle = "rgba(76,141,246,0.9)";
      (backendOverlay.lines || []).forEach(seg => {
        ctx.beginPath();
        ctx.moveTo(seg.x1 * sx, seg.y1 * sy);
        ctx.lineTo(seg.x2 * sx, seg.y2 * sy);
        ctx.stroke();
      });
      const roi = backendOverlay.roi || [];
      if (roi.length >= 3) {
        ctx.lineWidth = 2;
        ctx.strokeStyle = "rgba(58,200,182,0.8)";
        ctx.fillStyle = "rgba(58,200,182,0.12)";
        ctx.beginPath();
        roi.forEach((p, i) => {
          const x = p[0] * sx;
          const y = p[1] * sy;
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        });
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
      }
    }

    // 前端编辑中的 ROI（规范化）
    if (roiPoints.length > 0) {
      ctx.lineWidth = 2;
      ctx.strokeStyle = editing ? "rgba(255,255,255,0.9)" : "rgba(200,200,200,0.7)";
      ctx.fillStyle = "rgba(255,255,255,0.18)";
      ctx.beginPath();
      roiPoints.forEach((p, i) => {
        const x = p.x * w;
        const y = p.y * h;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      if (roiPoints.length >= 3) ctx.closePath();
      ctx.fill();
      ctx.stroke();
      ctx.fillStyle = "rgba(255,255,255,0.95)";
      roiPoints.forEach(p => {
        ctx.beginPath();
        ctx.arc(p.x * w, p.y * h, 4, 0, Math.PI * 2);
        ctx.fill();
      });
    }
  }

  function updateCameraIndicator(status) {
    if (!camDot || !camText) return;
    const ok = !!status.camera_connected;
    camDot.classList.toggle("ok", ok);
    camDot.classList.toggle("bad", !ok);
    camText.textContent = ok ? "摄像头已连接" : (status.camera_error || "摄像头未连接");
    if (camChip) camChip.title = status.camera_error || "";
  }

  function updateSpeedModeUI(modeVal) {
    const isPid = parseInt(modeVal, 10) === 1;
    if (speedLinear) speedLinear.style.display = isPid ? "none" : "flex";
    if (speedPid) speedPid.style.display = isPid ? "flex" : "none";
  }

  function updateIsland(errVal) {
    if (!islandDot || !islandValue) return;
    const e = Number(errVal) || 0;
    islandValue.textContent = e.toFixed(1);
    // -40~40 映射到轨道宽度（160px），留 80% 区间
    const clamped = Math.max(-40, Math.min(40, e));
    const ratio = clamped / 40; // -1..1
    const maxShift = 70; // px
    islandDot.style.transform = `translate(${ratio * maxShift}px, -50%)`;
  }

  function pushHistory(arr, val) {
    arr.push({ t: Date.now(), v: val });
    if (arr.length > MAX_POINTS) arr.shift();
  }

  function drawSparkline(canvas, data, opts = {}) {
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const w = canvas.width;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);
    if (!data.length) return;
    const values = data.map(d => d.v);
    const min = opts.min ?? Math.min(...values);
    const max = opts.max ?? Math.max(...values);
    const range = max - min || 1;
    const step = data.length > 1 ? w / (data.length - 1) : w;

    ctx.strokeStyle = "rgba(76,141,246,0.85)";
    ctx.lineWidth = 2;
    ctx.beginPath();
    data.forEach((d, i) => {
      const x = i * step;
      const y = h - ((d.v - min) / range) * h;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
  }

  function applyTheme(theme) {
    const t = theme === "light" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", t);
    localStorage.setItem("theme", t);
    if (themeBtn) {
      themeBtn.classList.toggle("active", true);
      if (themeIcon) {
        const nextIcon = t === "light" ? "/assets/light.svg" : "/assets/dark.svg";
        themeIcon.src = nextIcon;
        themeIcon.alt = t;
      }
      themeBtn.dataset.theme = t;
    }
  }

  function bindThemeToggle() {
    themeBtn = document.getElementById("themeToggle");
    themeIcon = document.getElementById("themeIcon");
    if (themeBtn) {
      themeBtn.addEventListener("click", () => {
        const current = document.documentElement.getAttribute("data-theme") || "dark";
        const next = current === "dark" ? "light" : "dark";
        applyTheme(next);
      });
    }
    const saved = localStorage.getItem("theme") || "dark";
    applyTheme(saved);
  }

  function schedulePost(extraPayload=null) {
    if (postTimer) clearTimeout(postTimer);
    postTimer = setTimeout(async () => {
      const payload = {};
      keys.forEach(k => {
        const el = document.getElementById(k);
        if (!el) return;
        payload[k] = el.value;
      });

      if (extraPayload) Object.assign(payload, extraPayload);

      payload["auto_drive"] = parseInt(payload["auto_drive"], 10);
      payload["steer_invert"] = parseInt(payload["steer_invert"], 10);
      payload["speed_mode"] = parseInt(payload["speed_mode"], 10);
      payload["hof_threshold"] = parseInt(payload["hof_threshold"], 10);
      payload["hof_min_line_len"] = parseInt(payload["hof_min_line_len"], 10);
      payload["hof_max_line_gap"] = parseInt(payload["hof_max_line_gap"], 10);
      payload["binary_value"] = parseInt(payload["binary_value"], 10);
      payload["canny_low_threshold"] = parseInt(payload["canny_low_threshold"], 10);
      payload["manual_servo"] = parseInt(payload["manual_servo"], 10);
      payload["scs_mode"] = parseInt(payload["scs_mode"], 10);
      payload["headlight"] = parseInt(payload["headlight"], 10);

      payload["steer_k"] = parseFloat(payload["steer_k"]);
      payload["motor_base"] = parseFloat(payload["motor_base"]);
      payload["motor_k"] = parseFloat(payload["motor_k"]);
      payload["speed_target"] = parseFloat(payload["speed_target"]);
      payload["speed_slowdown_gain"] = parseFloat(payload["speed_slowdown_gain"]);
      payload["speed_kp"] = parseFloat(payload["speed_kp"]);
      payload["speed_ki"] = parseFloat(payload["speed_ki"]);
      payload["speed_kd"] = parseFloat(payload["speed_kd"]);
      payload["speed_dt"] = parseFloat(payload["speed_dt"]);
      payload["manual_motor"] = parseFloat(payload["manual_motor"]);

      if (roiPoints.length >= 3) {
        payload["roi_points"] = roiPoints.map(p => [p.x, p.y]);
      } else if (extraPayload && extraPayload.roi_points) {
        payload["roi_points"] = extraPayload.roi_points;
      }

      await api.postParams(payload);
      await loadParams();
    }, 80);
  }

  async function loadParams() {
    const data = await api.loadParams();
    keys.forEach(k => setVal(k, data[k]));
    updateToggleBtn(data["auto_drive"]);
    updateSpeedModeUI(data["speed_mode"]);
    document.getElementById("manual_motor_input").value = Number(data["manual_motor"]).toFixed(2);
    document.getElementById("manual_servo_input").value = parseInt(data["manual_servo"], 10);

    if (Array.isArray(data["roi_points"])) {
      roiPoints = data["roi_points"].map(p => ({ x: Number(p[0]), y: Number(p[1]) }));
      document.getElementById("roi_count").textContent = roiPoints.length;
      drawOverlay();
    }
  }

  function bindSliders() {
    keys.forEach(k => {
      const el = document.getElementById(k);
      const out = document.getElementById(k + "_val");
      if (!el) return;
      el.addEventListener("input", () => {
        if (out) out.textContent = el.value;
        if (k === "auto_drive") updateToggleBtn(parseInt(el.value,10));
        if (k === "speed_mode") updateSpeedModeUI(el.value);
        schedulePost();
      });
    });
  }

  function bindActions() {
    document.getElementById("btnToggle").addEventListener("click", ()=>{
      const cur = parseInt(document.getElementById("auto_drive").value, 10);
      const nxt = cur === 1 ? 0 : 1;
      setVal("auto_drive", nxt);
      updateToggleBtn(nxt);
      schedulePost();
    });

    document.getElementById("btnEstop").addEventListener("click", async ()=>{
      await api.estop();
      await loadParams();
    });

    document.getElementById("btnApplyManual").addEventListener("click", ()=>{
      const duty = parseFloat(document.getElementById("manual_motor_input").value);
      const servo = parseInt(document.getElementById("manual_servo_input").value, 10);

      setVal("auto_drive", 0);
      updateToggleBtn(0);
      setVal("manual_motor", duty.toFixed(2));
      setVal("manual_servo", servo);

      schedulePost({ auto_drive: 0, manual_motor: duty, manual_servo: servo });
    });

    streamSelect.addEventListener("change", updateStream);
    streamImage.addEventListener("load", () => {
      resizeCanvas();
      drawOverlay();
    });
    document.getElementById("btnFullscreen").addEventListener("click", () => {
      const wrap = videoWrap || streamImage.parentElement;
      if (!document.fullscreenElement) {
        wrap.requestFullscreen?.();
      } else {
        document.exitFullscreen?.();
      }
    });
    // 使用 icon 展示
    const btnFs = document.getElementById("btnFullscreen");
    if (btnFs) {
      btnFs.textContent = "⤢";
      btnFs.title = "全屏切换";
    }
  }

    function bindROI() {
      const btnEdit = document.getElementById("btnEditROI");
      const btnClear = document.getElementById("btnClearROI");
      btnEdit.addEventListener("click", () => {
        const wasEditing = editing;
        editing = !editing;
        overlay.classList.toggle("editing", editing);
        btnEdit.textContent = editing ? "退出编辑" : "编辑 ROI";
        // 退出编辑时自动下发当前点位（>=3 使用，<3 视为清空）
        if (wasEditing && !editing) {
          const payload = roiPoints.length >= 3
            ? { roi_points: roiPoints.map(p => [p.x, p.y]) }
            : { roi_points: [] };
          schedulePost(payload);
        }
      });
      btnClear.addEventListener("click", () => {
        roiPoints = [];
        document.getElementById("roi_count").textContent = roiPoints.length;
        drawOverlay();
        schedulePost({ roi_points: [] });
      });
      overlay.addEventListener("click", (e) => {
        if (!editing) return;
        const rect = overlay.getBoundingClientRect();
        const x = (e.clientX - rect.left) / rect.width;
        const y = (e.clientY - rect.top) / rect.height;
        roiPoints.push({ x, y });
        document.getElementById("roi_count").textContent = roiPoints.length;
        drawOverlay();
        // 实时下发 ROI（点数 <3 时视为清空，>=3 才生效）
        schedulePost({ roi_points: roiPoints.length >= 3 ? roiPoints.map(p => [p.x, p.y]) : [] });
      });
      overlay.addEventListener("dblclick", () => {
        if (!editing) return;
        editing = false;
        overlay.classList.remove("editing");
        btnEdit.textContent = "编辑 ROI";
        schedulePost({ roi_points: roiPoints.length >= 3 ? roiPoints.map(p => [p.x, p.y]) : [] });
      });
      window.addEventListener("resize", () => {
        resizeCanvas();
        drawOverlay();
      });
      document.addEventListener("fullscreenchange", () => {
        resizeCanvas();
        drawOverlay();
      });
    }

  async function pollStatus() {
    try {
      const s = await api.loadStatus();
      const view = `
        <div class="status-tile"><span class="sub">模式</span><strong>${s.mode}</strong></div>
        <div class="status-tile"><span class="sub">FPS</span><strong>${Number(s.fps).toFixed(1)}</strong></div>
        <div class="status-tile"><span class="sub">err</span><strong>${Number(s.err).toFixed(2)}</strong></div>
        <div class="status-tile"><span class="sub">servo</span><strong>${s.servo_position}</strong></div>
        <div class="status-tile"><span class="sub">motor</span><strong>${Number(s.motor_duty).toFixed(2)}</strong></div>
        <div class="status-tile"><span class="sub">串口</span><strong>${s.chassis_connected}</strong><div class="mono" style="color:${s.chassis_error ? '#f45b69':'var(--sub)'}">${s.chassis_error || ''}</div></div>
      `;
      document.getElementById("status").innerHTML = view;
      backendOverlay = s.overlay || null;
      updateCameraIndicator(s);
      updateIsland(s.err || 0);
      pushHistory(errHistory, Number(s.err) || 0);
      pushHistory(speedHistory, Number(s.motor_duty) || 0);
      drawSparkline(errChart, errHistory, { min: -40, max: 40 });
      drawSparkline(speedChart, speedHistory, { min: 0, max: 0.2 });
      resizeCanvas();
      drawOverlay();
    } catch (e) {}
    setTimeout(pollStatus, 220);
  }

  async function init(){
    streamSelect = document.getElementById("streamSelect");
    streamImage = document.getElementById("streamImage");
    overlay = document.getElementById("overlay");
    videoWrap = document.querySelector(".video-wrap");
    camDot = document.getElementById("camDot");
    camText = document.getElementById("camText");
    camChip = document.getElementById("camChip");
    speedLinear = document.getElementById("speed_linear");
    speedPid = document.getElementById("speed_pid");
    islandDot = document.getElementById("islandDot");
    islandValue = document.getElementById("islandValue");
    errChart = document.getElementById("errChart");
    speedChart = document.getElementById("speedChart");
    bindThemeToggle();
    bindSliders();
    bindActions();
    bindROI();
    updateStream();
    await loadParams();
    pollStatus();
    resizeCanvas();
  }

  return { init };
})();

document.addEventListener("DOMContentLoaded", () => ui.init());
