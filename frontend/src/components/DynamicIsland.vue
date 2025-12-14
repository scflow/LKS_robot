<script setup lang="ts">
import { computed, ref } from 'vue'

const props = defineProps<{ err: number }>()

const expanded = ref(false)
const warn = computed(() => Math.abs(props.err) > 10)
const cursorX = computed(() => {
  const clamped = Math.max(-40, Math.min(40, props.err))
  const ratio = clamped / 40
  const maxShift = 50
  return `${ratio * maxShift}px`
})
const errText = computed(() => props.err.toFixed(2))
</script>

<template>
  <div class="error-island" :class="{ warning: warn, expanded }" @click="expanded = !expanded" role="button" :title="expanded ? '收起' : '点击展开查看误差'">
    <div class="island-track">
      <div class="island-cursor" :class="{ warn }" :style="{ transform: `translate(${cursorX}, -50%)` }"></div>
    </div>
    <div class="island-info-wrapper">
      <div class="island-info">
        <span class="island-label">LATERAL ERROR</span>
        <span class="island-value">{{ errText }}</span>
      </div>
    </div>
  </div>
</template>
