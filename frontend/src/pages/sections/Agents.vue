<script setup>
import { ref, watch, computed } from "vue";
import { api, encode } from "../../api";
import { capabilityLabels, sortFindings } from "../../domain";
import Icon from "../../components/Icon.vue";
import FindingsTable from "../../components/FindingsTable.vue";
import AgentGraph from "../../components/AgentGraph.vue";
import CapabilityRadar from "../../components/CapabilityRadar.vue";
const props = defineProps({ scan: Object });
const skipped = computed(() => ['disabled','not_applicable'].includes(props.scan.metadata.scanners.agent_security?.status)
  || (props.scan.metadata.scan_profile && !props.scan.metadata.scan_profile.executed_modules.includes('agent_security')));
defineEmits(["detail"]);
const data = ref(null),
  loading = ref(false),
  error = ref(""),
  tab = ref("overview"),
  tool = ref(null),
  search = ref("");
let request = 0;
async function load() {
  const token = ++request;
  loading.value = true;
  error.value = "";
  try {
    const value = await api(`/scans/${encode(props.scan.id)}/agent-security`);
    if (token === request) data.value = value;
  } catch (e) {
    if (token === request) error.value = e.message;
  } finally {
    if (token === request) loading.value = false;
  }
}
watch(() => props.scan.id, load, { immediate: true });
const unresolved = computed(
  () =>
    data.value?.bindings.filter((b) =>
      ["unresolved", "ambiguous"].includes(b.resolution_status),
    ) || [],
);
const filteredTools = computed(
  () =>
    data.value?.tools.filter((t) =>
      `${t.name} ${t.description}`
        .toLowerCase()
        .includes(search.value.toLowerCase()),
    ) || [],
);
const toolFindings = computed(
  () =>
    data.value?.findings.filter((f) =>
      f.evidence?.some((e) => e.details?.tool_id === tool.value?.id),
    ) || [],
);
const boundAgents = computed(
  () =>
    data.value?.agents.filter((a) =>
      data.value.bindings.some(
        (b) => b.agent_id === a.id && b.tool_id === tool.value?.id,
      ),
    ) || [],
);
function selectTool(item) {
  tool.value = item;
  setTimeout(
    () =>
      document.getElementById("tool-detail")?.scrollIntoView({
        behavior: matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "instant"
          : "smooth",
        block: "center",
      }),
    30,
  );
}
</script>
<template>
  <div v-if="skipped" class="panel empty-state">
    <Icon name="Info" :size="30" />
    <h2>{{ scan.metadata.scanners.agent_security.status === 'disabled' ? '本次未执行 Agent 专项' : scan.metadata.scanners.agent_security.status === 'partial' ? '当前源码无法完成 Agent 结构识别' : '未识别到受支持的 Agent 结构' }}</h2>
    <p>这不是 Agent 检查通过或安全结论。需要审查任务、绑定工具和权限，请从专项入口提交包含这些声明的源码包。</p>
    <RouterLink to="/new?mode=agent" class="button primary">进入 Agent 专项审查</RouterLink>
  </div>
  <template v-else>
  <div class="page-heading">
    <div>
      <p class="eyebrow">AGENT SECURITY</p>
      <h1>给 Agent 合适的能力，而不是所有能力。</h1>
      <p>把任务、工具和能力联系起来，理解每一条授权的必要性。</p>
    </div>
    <span class="heading-illustration"><Icon name="Bot" :size="34" /></span>
  </div>
  <div class="view-tabs">
    <button :class="{ active: tab === 'overview' }" @click="tab = 'overview'">
      安全概览与关系图</button
    ><button :class="{ active: tab === 'details' }" @click="tab = 'details'">
      工具与风险明细
    </button>
  </div>
  <div v-if="error" class="panel empty-state">
    <p>{{ error }}</p>
    <button class="button secondary" @click="load">重试</button>
  </div>
  <div v-else-if="loading" class="panel empty-state">
    <Icon name="LoaderCircle" class="spin" />
    <p>正在恢复 Agent 安全视图</p>
  </div>
  <template v-else-if="data"
    ><div class="metric-grid">
      <div
        class="metric-card"
        v-for="[label, count] in [
          ['Agent', data.agents.length],
          ['Tool', data.tools.length],
          ['风险发现', data.findings.length],
          ['未解析绑定', unresolved.length],
        ]"
        :key="label"
      >
        <span>{{ label }}</span
        ><b :class="label === '未解析绑定' ? 'text-orange' : 'text-blue'">{{
          count
        }}</b
        ><small>{{
          label === "未解析绑定"
            ? "包含 unresolved 与 ambiguous"
            : "来自静态解析结果"
        }}</small>
      </div>
    </div>
    <div v-if="tab === 'overview'" class="agent-radar section-gap">
      <CapabilityRadar :tools="data.tools" :status="data.status.status" />
    </div>
    <section v-if="tab === 'overview'" class="panel graph-panel section-gap">
      <div class="panel-heading">
        <h2><Icon name="Network" :size="19" />Agent — Tool — Capability</h2>
        <span class="micro-tag">静态绑定关系</span>
      </div>
      <AgentGraph :data="data" @tool="selectTool" />
    </section>
    <section v-if="tab === 'details'" class="panel">
      <div class="panel-heading">
        <h2>工具清单</h2>
        <div class="search-field">
          <Icon name="Search" :size="16" /><input
            v-model="search"
            placeholder="搜索工具名称或描述"
            aria-label="搜索工具"
          />
        </div>
      </div>
      <div v-if="!filteredTools.length" class="empty-state">
        <p>没有匹配的工具。</p>
      </div>
      <div v-else class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>工具名称</th>
              <th>框架</th>
              <th>能力</th>
              <th>静态控制</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in filteredTools" :key="item.id">
              <td>
                <button class="finding-title" @click="selectTool(item)">
                  {{ item.name }}</button
                ><small class="file-location">{{
                  item.source_spans?.[0]?.path
                }}</small>
              </td>
              <td>{{ item.framework }}</td>
              <td>
                <div class="tag-list">
                  <span
                    v-for="cap in item.capabilities"
                    :key="cap.capability"
                    class="capability-tag"
                    >{{
                      capabilityLabels[cap.capability] || cap.capability
                    }}</span
                  >
                </div>
              </td>
              <td>
                {{
                  item.controls.length
                    ? "已识别 " + item.controls.length + " 项"
                    : "未发现显式控制"
                }}
              </td>
              <td>
                <button class="text-button" @click="selectTool(item)">
                  详情
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
    <section v-if="tool" id="tool-detail" class="panel tool-detail section-gap">
      <div class="panel-heading">
        <h2><Icon name="Terminal" :size="19" />{{ tool.name }}</h2>
        <button
          class="icon-button"
          @click="tool = null"
          aria-label="收起工具详情"
        >
          <Icon name="X" :size="18" />
        </button>
      </div>
      <div class="padded">
        <p>{{ tool.description || "未记录工具描述" }}</p>
        <div v-for="agent in boundAgents" :key="agent.id" class="agent-task">
          <span class="micro-tag">{{ agent.name }} 的任务</span>
          <p>{{ agent.task_text || "未提取到明确任务" }}</p>
        </div>
        <div class="capability-details">
          <div v-for="(cap, index) in tool.capabilities" :key="index">
            <b>{{ capabilityLabels[cap.capability] || cap.capability }}</b
            ><span>能力影响权重 {{ cap.impact }} / 5</span>
            <p>{{ cap.rationale }}</p>
            <small
              >{{ cap.source_span?.path }}:{{
                cap.source_span?.start_line
              }}</small
            >
          </div>
        </div>
        <p class="small-text muted">
          能力影响权重描述工具能造成的影响；风险等级由任务上下文中的 Finding
          决定。
        </p>
        <div class="tag-list">
          <span
            class="capability-tag"
            v-for="control in tool.controls"
            :key="control"
            >{{ control }}</span
          ><span class="muted" v-if="!tool.controls.length"
            >未发现显式静态安全控制</span
          >
        </div>
      </div>
      <FindingsTable
        :items="toolFindings"
        compact
        @select="(item) => $emit('detail', item)"
      />
    </section>
    <section class="panel section-gap">
      <div class="panel-heading">
        <h2>
          {{ tab === "overview" ? "需要关注的工具暴露" : "全部 Agent 风险" }}
        </h2>
        <span class="micro-tag">{{ data.findings.length }} 项</span>
      </div>
      <FindingsTable
        :items="
          tab === 'overview'
            ? sortFindings(data.findings).slice(0, 5)
            : sortFindings(data.findings)
        "
        @select="(item) => $emit('detail', item)"
      />
    </section>
    <section v-if="unresolved.length" class="panel padded section-gap">
      <h2><Icon name="GitBranch" :size="19" /> 未解析的绑定</h2>
      <p class="muted">
        动态加载等行为无法仅靠静态代码确定，系统保留不确定性，交由开发者复核。
      </p>
      <div class="unresolved-item" v-for="(b, i) in unresolved" :key="i">
        <div>
          <b>{{ b.tool_name }}</b
          ><span class="micro-tag">{{ b.resolution_status }}</span>
        </div>
        <p>{{ b.resolution_reason }}</p>
        <small
          >{{ b.registration_span?.path }}:{{
            b.registration_span?.start_line
          }}</small
        >
      </div>
    </section>
    <div class="method-note">
      <Icon name="Info" :size="17" />
      <p>
        本次评分方法：<code>{{ data.scoring_model }}</code> · 规则版本
        {{ data.rules_version }}。{{
          data.scoring_model === "deterministic-context-baseline"
            ? "使用确定性任务上下文基线，没有调用大模型或加载训练分类器。"
            : "以本次保存的模型标识与对应评测说明为准。"
        }}
      </p>
    </div></template
  >
  </template>
</template>
