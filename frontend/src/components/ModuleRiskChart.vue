<script setup>
import { computed, ref } from "vue";
import { moduleRiskRows } from "../charts";
import { severityOrder, severityLabels, statusLabels } from "../domain";
import Icon from "./Icon.vue";
const props = defineProps({ scan: Object });
const selected = ref("all");
const rows = computed(() => moduleRiskRows(props.scan));
const levels = computed(() =>
  selected.value === "all" ? severityOrder : [selected.value],
);
const count = (row) => levels.value.reduce((n, s) => n + row.counts[s], 0);
const maximum = computed(() => Math.max(1, ...rows.value.map(count)));
const palette = {
  critical: "#b9244c",
  high: "#e14b54",
  medium: "#e3a02f",
  low: "#4e7cdc",
  info: "#9ba9bf",
};
</script>
<template>
  <section class="panel module-risk-chart">
    <div class="panel-heading">
      <h2><Icon name="LayoutDashboard" :size="20" />模块风险对比</h2>
      <span class="micro-tag">真实发现数量</span>
    </div>
    <div class="visual-toolbar"><p>按严重度展开，定位优先处理的模块</p></div>
    <div class="chart-filter" aria-label="选择风险等级">
      <button
        :class="{ active: selected === 'all' }"
        @click="selected = 'all'"
        :aria-pressed="selected === 'all'"
      >
        全部</button
      ><button
        v-for="level in severityOrder"
        :key="level"
        @click="selected = selected === level ? 'all' : level"
        :class="{ active: selected === level }"
        :aria-pressed="selected === level"
      >
        <i :style="{ background: palette[level] }"></i
        >{{ severityLabels[level] }}
      </button>
    </div>
    <div class="module-bars">
      <RouterLink
        v-for="row in rows"
        :key="row.key"
        :to="`/scan/${scan.id}/${row.route}`"
        class="module-bar-row"
        :aria-label="`${row.label}，${count(row)}项匹配发现，${statusLabels[row.status]}，查看详情`"
        ><div class="module-bar-title">
          <b>{{ row.label }}</b
          ><span>{{ statusLabels[row.status] }}</span
          ><strong
            >{{
              !row.total && !["success", "partial"].includes(row.status)
                ? "—"
                : count(row)
            }}<small
              v-if="row.total || ['success', 'partial'].includes(row.status)"
            >
              项</small
            ></strong
          >
        </div>
        <div class="module-bar-track">
          <span
            v-for="level in levels"
            :key="level"
            :style="{
              width: (row.counts[level] / maximum) * 100 + '%',
              background: palette[level],
            }"
            :title="`${severityLabels[level]}：${row.counts[level]} 项`"
            ><span v-if="row.counts[level]">{{ row.counts[level] }}</span></span
          >
        </div>
        <p v-if="!count(row)" class="bar-empty-note">
          {{
            ["success", "partial"].includes(row.status)
              ? "当前筛选下无风险发现"
              : "该模块未获得完整有效结果"
          }}
        </p></RouterLink
      >
    </div>
    <div class="chart-axis">
      <span>0 项</span><span>统一数量刻度 · {{ maximum }} 项</span>
    </div>
    <div class="comparison-tip">
      <Icon name="Info" :size="18" />
      <p>
        点击等级筛选，点击条形进入模块。仅展示本次所选检查范围；Agent 数量包含工具暴露与未解析绑定。
      </p>
    </div>
    <p class="visual-footnote">
      风险项数量不等于受影响文件数；未执行的模块以“—”显示。
    </p>
  </section>
</template>
