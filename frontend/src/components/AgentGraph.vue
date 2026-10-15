<script setup>
import { computed, ref } from "vue";
import { capabilityLabels } from "../domain";
const props = defineProps({ data: Object });
defineEmits(["tool"]);
const filter = ref("all");
const agents = computed(() =>
  (props.data.agents || [])
    .filter((a) => filter.value === "all" || a.id === filter.value)
    .slice(0, 8),
);
const bindings = computed(() =>
  (props.data.bindings || []).filter((b) =>
    agents.value.some((a) => a.id === b.agent_id),
  ),
);
const tools = computed(() =>
  (props.data.tools || [])
    .filter((t) => bindings.value.some((b) => b.tool_id === t.id))
    .slice(0, 10),
);
const capabilities = computed(() =>
  [
    ...new Set(
      tools.value.flatMap((t) => t.capabilities.map((c) => c.capability)),
    ),
  ].slice(0, 10),
);
const height = computed(() =>
  Math.max(
    320,
    Math.max(
      agents.value.length,
      tools.value.length,
      capabilities.value.length,
    ) *
      65 +
      60,
  ),
);
const pos = (index, length) =>
  58 +
  ((height.value - 100) / Math.max(1, length)) * index +
  ((height.value - 100) / Math.max(1, length)) * 0.5;
const risk = (t) =>
  props.data.findings.some((f) =>
    f.evidence?.some((e) => e.details?.tool_id === t.id),
  );
const unresolved = computed(
  () =>
    bindings.value.filter((b) =>
      ["unresolved", "ambiguous"].includes(b.resolution_status),
    ).length,
);
</script>
<template>
  <div class="graph-toolbar">
    <div class="graph-legend">
      <span><i class="agent-dot"></i>Agent</span
      ><span><i class="tool-dot"></i>Tool</span
      ><span><i class="capability-dot"></i>Capability</span>
    </div>
    <select v-model="filter" aria-label="选择关系图 Agent">
      <option value="all">全部 Agent</option>
      <option v-for="agent in data.agents" :key="agent.id" :value="agent.id">
        {{ agent.name }}
      </option>
    </select>
  </div>
  <div class="graph-canvas">
    <svg
      v-if="agents.length"
      :viewBox="`0 0 980 ${height}`"
      role="img"
      aria-label="Agent、工具与能力关系图"
    >
      <text x="40" y="27" class="graph-heading">任务主体</text>
      <text x="365" y="27" class="graph-heading">已绑定的工具</text>
      <text x="730" y="27" class="graph-heading">工具能力</text>
      <g fill="none" stroke="#d4dded" stroke-width="1.7">
        <template v-for="b in bindings" :key="b.agent_id + '-' + b.tool_name">
          <path
            v-if="tools.some((t) => t.id === b.tool_id)"
            :d="`M240 ${pos(
              agents.findIndex((a) => a.id === b.agent_id),
              agents.length,
            )} C300 ${pos(
              agents.findIndex((a) => a.id === b.agent_id),
              agents.length,
            )},300 ${pos(
              tools.findIndex((t) => t.id === b.tool_id),
              tools.length,
            )},365 ${pos(
              tools.findIndex((t) => t.id === b.tool_id),
              tools.length,
            )}`"
            :stroke-dasharray="
              b.resolution_status === 'resolved_by_name' ? '5 4' : null
            "
          />
        </template>
        <template v-for="(tool, i) in tools" :key="tool.id">
          <path
            v-for="cap in tool.capabilities.filter((c) =>
              capabilities.includes(c.capability),
            )"
            :key="cap.capability"
            :d="`M605 ${pos(i, tools.length)} C660 ${pos(i, tools.length)},670 ${pos(capabilities.indexOf(cap.capability), capabilities.length)},730 ${pos(capabilities.indexOf(cap.capability), capabilities.length)}`"
          />
        </template>
      </g>
      <g
        v-for="(agent, i) in agents"
        :key="agent.id"
        :transform="`translate(40 ${pos(i, agents.length) - 24})`"
      >
        <rect width="200" height="48" rx="10" fill="#eef0ff" stroke="#c4ccf7" />
        <circle cx="21" cy="24" r="6" fill="#7270df" />
        <text x="37" y="29" class="graph-label">
          {{ agent.name.slice(0, 20) }}
        </text>
        <title>{{ agent.name }} · {{ agent.task_text }}</title>
      </g>
      <g
        v-for="(tool, i) in tools"
        :key="tool.id"
        :transform="`translate(365 ${pos(i, tools.length) - 24})`"
        class="graph-node"
        role="button"
        tabindex="0"
        :aria-label="`查看工具 ${tool.name}`"
        @click="$emit('tool', tool)"
        @keydown.enter="$emit('tool', tool)"
        @keydown.space.prevent="$emit('tool', tool)"
      >
        <rect
          width="240"
          height="48"
          rx="10"
          :fill="risk(tool) ? '#fff4f3' : '#f2f7ff'"
          :stroke="risk(tool) ? '#edb9b4' : '#b9d1f3'"
        />
        <circle
          cx="20"
          cy="24"
          r="6"
          :fill="risk(tool) ? '#ec7e70' : '#528ddd'"
        />
        <text x="36" y="29" class="graph-label">
          {{ tool.name.slice(0, 24) }}
        </text>
        <title>{{ tool.name }} · 点击查看能力与风险</title>
      </g>
      <g
        v-for="(cap, i) in capabilities"
        :key="cap"
        :transform="`translate(730 ${pos(i, capabilities.length) - 20})`"
      >
        <rect width="205" height="40" rx="20" fill="#f7fafb" stroke="#d9e5e9" />
        <circle cx="19" cy="20" r="4" fill="#68aaa4" />
        <text x="33" y="25" class="graph-label">
          {{ capabilityLabels[cap] || cap }}
        </text>
      </g>
    </svg>
    <div v-else class="empty-state">
      <h3>未恢复可展示的 Agent 绑定图</h3>
      <p>可以在下方工具与未解析绑定明细中查看已获得的结果。</p>
    </div>
  </div>
  <div class="graph-note">
    <span
      >点击工具节点查看详情 · 图中最多展示 8 个 Agent / 10 个
      Tool，完整记录见明细</span
    ><span v-if="unresolved" class="text-orange"
      >{{ unresolved }} 条绑定尚未解析</span
    >
  </div>
</template>
