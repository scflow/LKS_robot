<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  label: string
  min: number
  max: number
  step: number
  modelValue: number
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: number): void
  (e: 'change', value: number): void
}>()

const progress = computed(() => {
  const span = props.max - props.min || 1
  const pct = ((props.modelValue - props.min) / span) * 100
  return Math.min(100, Math.max(0, pct))
})

const onInput = (e: Event) => {
  const val = Number((e.target as HTMLInputElement).value)
  emit('update:modelValue', val)
  emit('change', val)
}
</script>

<template>
  <div class="field">
    <label>{{ props.label }}</label>
    <div class="row-control">
      <input
        type="range"
        class="ios-slider"
        :min="props.min"
        :max="props.max"
        :step="props.step"
        :value="props.modelValue"
        @input="onInput"
        :style="{ '--progress': progress + '%' }"
      />
      <input class="precision-input" type="number" :min="props.min" :max="props.max" :step="props.step" :value="props.modelValue" @input="onInput" />
    </div>
  </div>
</template>

<style scoped>
.row-control {
  display: flex;
  gap: 8px;
  align-items: center;
}
.field label {
  font-weight: 600;
  color: var(--text);
}
.precision-input {
  width: 90px;
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: var(--card-strong);
  color: var(--text);
  font-size: 13px;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.65);
}
</style>
