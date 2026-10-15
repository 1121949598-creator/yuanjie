<script setup>
import { computed } from "vue";
import { severityOrder, severityLabel } from "../domain";
const props = defineProps({ findings: { default: () => [] } });
const colors = ["#bd2852", "#ee6b6b", "#f4ac4b", "#6b91e5", "#b1bed5"];
const counts = computed(() =>
  severityOrder.map(
    (s) => props.findings.filter((f) => f.severity === s).length,
  ),
);
const gradient = computed(() => {
  let sum = 0;
  const total = props.findings.length;
  if (!total) return "#edf0f7";
  return (
    "conic-gradient(" +
    counts.value
      .map((n, i) => {
        let start = sum;
        sum += (n / total) * 100;
        return `${colors[i]} ${start}% ${sum}%`;
      })
      .join(",") +
    ")"
  );
});
</script>
<template>
  <div class="risk-chart">
    <div
      class="donut"
      :style="{ background: gradient }"
      role="img"
      :aria-label="`风险分布，共 ${findings.length} 项`"
    >
      <div>
        <b>{{ findings.length }}</b
        ><span>风险发现</span>
      </div>
    </div>
    <div class="chart-legend">
      <div v-for="(severity, i) in severityOrder" :key="severity">
        <span
          ><i :style="{ background: colors[i] }"></i
          >{{ severityLabel(severity) }}</span
        ><b>{{ counts[i] }}<small>项</small></b>
      </div>
    </div>
  </div>
</template>
