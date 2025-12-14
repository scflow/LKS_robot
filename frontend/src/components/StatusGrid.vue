<script setup lang="ts">
defineProps<{
  tiles: { label: string; value: string }[]
  chassisOk: boolean
  chassisError?: string
}>()
</script>

<template>
  <div class="status-grid">
    <div v-for="tile in tiles" :key="tile.label" class="stat-box">
      <span class="stat-label">{{ tile.label }}</span>
      <span class="stat-value">{{ tile.value }}</span>
    </div>
    <div class="status-row" :class="{ error: !chassisOk }" :title="chassisOk ? 'Chassis Connected' : chassisError || 'Connection Failed'">
      <div class="status-text">
        <span class="title">Chassis</span>
        <span class="desc">{{ chassisOk ? 'Connected' : 'Connection Failed' }}</span>
      </div>
      <div class="status-indicator" :class="chassisOk ? 'green' : 'red'"></div>
    </div>
  </div>
</template>
