<script setup>
import { severityLabel, statusLabels } from "../domain";
defineProps({ value: String, kind: { default: "severity" } });
</script>
<template>
  <span class="badge" :class="value || 'neutral'"
    ><i></i
    >{{
      kind === "status"
        ? statusLabels[value] || value || "未知"
        : severityLabel(value)
    }}</span
  >
</template>
