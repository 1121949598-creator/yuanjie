<script setup>
import { computed, ref, watch } from "vue";
import { capabilityProfile } from "../charts";
import Icon from "./Icon.vue";
import Badge from "./Badge.vue";
const props = defineProps({
  noun: { default: "工具" },
  tools: { default: () => [] },
  status: { default: "unavailable" },
});
const selected = ref("all"),
  active = ref(0);
watch(
  () => props.tools,
  () => {
    selected.value = "all";
    active.value = 0;
  },
);
const current = computed(() =>
  selected.value === "all"
    ? props.tools
    : props.tools.filter((t) => t.id === selected.value),
);
const profile = computed(() => capabilityProfile(current.value, props.status));
const axis = computed(() => profile.value.axes[active.value]);
function point(i, r) {
  const angle = ((-90 + i * 72) * Math.PI) / 180;
  return { x: 240 + Math.cos(angle) * r, y: 177 + Math.sin(angle) * r };
}
const polygon = (r) =>
  Array.from({ length: 5 }, (_, i) => {
    const p = point(i, r);
    return `${p.x},${p.y}`;
  }).join(" ");
const values = computed(() =>
  profile.value.axes
    .map((a, i) => {
      const p = point(i, ((a.value || 0) / 5) * 110);
      return `${p.x},${p.y}`;
    })
    .join(" "),
);
</script>
<template>
  <section class="panel capability-radar">
    <div class="panel-heading">
      <h2><Icon name="ShieldCheck" :size="20" />五维{{ noun }}能力</h2>
      <Badge :value="status" kind="status" />
    </div>
    <div class="visual-toolbar">
      <p>越靠外，已识别能力的影响越高</p>
      <select v-model="selected" aria-label="雷达图工具范围">
        <option value="all">全部{{ noun }}（{{ tools.length }}）</option>
        <option v-for="tool in tools" :key="tool.id" :value="tool.id">
          {{ tool.name }}
        </option>
      </select>
    </div>
    <div v-if="!profile.available" class="empty-state radar-empty">
      <Icon name="Info" :size="32" />
      <h3>能力画像暂不可用</h3>
      <p>请先获得有效的 Agent 分析结果。</p>
    </div>
    <template v-else>
      <svg
        class="radar-svg"
        viewBox="0 0 480 350"
        role="group"
        aria-label="五维工具能力雷达图，量程零至五，越大表示能力影响越高"
      >
        <polygon
          v-for="level in [5, 4, 3, 2, 1]"
          :key="level"
          :points="polygon(level * 22)"
          :fill="level % 2 ? '#f1f4ff' : '#f9fbff'"
          stroke="#bbc9e4"
          stroke-width="1"
        />
        <line
          v-for="(_, i) in profile.axes"
          :key="'line' + i"
          x1="240"
          y1="177"
          :x2="point(i, 110).x"
          :y2="point(i, 110).y"
          stroke="#c2cde3"
        />
        <text
          v-for="level in [1, 2, 3, 4, 5]"
          :key="'scale' + level"
          x="246"
          :y="177 - level * 22 + 4"
          class="radar-scale"
        >
          {{ level }}
        </text>
        <polygon
          v-if="tools.length"
          class="radar-area"
          :points="values"
          fill="#22b9d3"
          fill-opacity=".24"
          stroke="#337fd0"
          stroke-width="2.5"
          stroke-linejoin="round"
        />
        <circle
          v-for="(item, i) in profile.axes"
          :key="'point-' + i"
          :cx="point(i, (item.value / 5) * 110).x"
          :cy="point(i, (item.value / 5) * 110).y"
          :r="active === i ? 6 : 4"
          fill="#fff"
          stroke="#07889f"
          stroke-width="2"
          @mouseenter="active = i"
        />
        <g
          v-for="(item, i) in profile.axes"
          :key="item.label"
          class="radar-axis"
          tabindex="0"
          role="button"
          :aria-label="`${item.label}：${item.value}，涉及${item.tools.length}个工具`"
          :aria-pressed="active === i"
          @mouseenter="active = i"
          @focus="active = i"
          @click="active = i"
          @keydown.enter="active = i"
          @keydown.space.prevent="active = i"
        >
          <rect
            :x="point(i, 145).x - (i === 0 ? 55 : i < 3 ? 8 : 102)"
            :y="point(i, 145).y - 19"
            width="110"
            height="48"
            rx="6"
            fill="transparent"
            pointer-events="all"
          />
          <text
            :x="point(i, 145).x"
            :y="point(i, 145).y"
            :text-anchor="i === 0 ? 'middle' : i < 3 ? 'start' : 'end'"
            class="radar-label"
            :class="{ chosen: active === i }"
          >
            {{ item.label }}
            <tspan :x="point(i, 145).x" dy="22" class="radar-value">
              {{ item.value }} / 5
            </tspan>
          </text>
          <title>
            {{ item.description }} · {{ item.tools.length }} 个{{ noun }}
          </title>
        </g>
      </svg>
      <div class="radar-insight" aria-live="polite">
        <div>
          <b>{{ axis.label }}</b
          ><strong>{{ axis.value }}<small> / 5</small></strong>
        </div>
        <p>{{ axis.description }}</p>
        <p class="radar-tool-names">
          {{
            axis.tools.length
              ? axis.tools.map((t) => t.name).join("、")
              : "此范围未识别到该类能力"
          }}
        </p>
      </div>
    </template>
    <p class="visual-footnote">
      各维度取所选{{ noun }}的最高影响值，来自静态分析。0
      表示未识别；不代表安全评分。{{
        status === "partial" ? "本次覆盖不完整。" : ""
      }}{{
        profile.omitted
          ? `另有 ${profile.omitted} 条能力记录不适用于此图。`
          : ""
      }}
    </p>
  </section>
</template>
