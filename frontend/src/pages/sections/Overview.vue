<script setup>
import { state } from "../../state";
import { localize } from "../../language";
import { computed, ref } from "vue";
import { useRoute } from 'vue-router';
import { scanJourney } from '../../journeys';
import Icon from "../../components/Icon.vue";
import Badge from "../../components/Badge.vue";
import FindingsTable from "../../components/FindingsTable.vue";
import RiskChart from "../../components/RiskChart.vue";
import CapabilityRadar from "../../components/CapabilityRadar.vue";
import ModuleRiskChart from "../../components/ModuleRiskChart.vue";
import {
  agentFindings,
  sortFindings,
  summarizeRisk,
  coverageSummary,
} from "../../domain";
const props = defineProps({ scan: Object, workspace: Boolean });
const emit = defineEmits(["detail"]);
const route = useRoute();
const mode = computed(() => scanJourney(props.scan.id, route.query.mode, props.scan));
const professional = computed(() => mode.value === 'agent' || (!props.scan.metadata.scan_profile && route.query.professional === '1'));
const search = ref(""),
  filter = ref("all"),
  page = ref(1);
const sorted = computed(() => sortFindings(props.scan.findings));
const matches = computed(() =>
  sorted.value.filter(
    (f) =>
      (filter.value === "all" ||
        f.category === filter.value ||
        (filter.value === "agent" && agentFindings([f]).length)) &&
      `${f.title} ${localize(f.title)} ${f.evidence?.[0]?.source_span?.path || ""}`
        .toLowerCase()
        .includes(search.value.toLowerCase()),
  ),
);
const componentTools = computed(() =>
  (state.componentSecurity?.components || []).map((entry) => ({
    id: entry.component.component_id,
    name: entry.component.name,
    capabilities: entry.capabilities || [],
  })),
);
const radarTools = computed(() =>
  componentTools.value.length ? componentTools.value : props.scan.tools,
);
const radarStatus = computed(() =>
  state.componentSecurity
    ? state.componentSecurity.status
    : props.scan.metadata.scanners.agent_security?.status,
);
const risk = computed(() => summarizeRisk(props.scan));
const coverage = computed(() => coverageSummary(props.scan));
const modules = computed(() => [
  {
    key: "secrets",
    icon: "KeyRound",
    name: "敏感凭据",
    en: "SECRET DETECTION",
    count: props.scan.summary.secrets,
    desc: "敏感凭据与配置泄露",
    status: props.scan.metadata.scanners.secret?.status,
  },
  {
    key: "licenses",
    icon: "FileCheck2",
    name: "许可证与依赖",
    en: "LICENSE COMPLIANCE",
    count: props.scan.summary.licenses,
    desc: "许可风险与人工复核",
    status: props.scan.metadata.scanners.license?.status,
  },
  {
    key: "agents",
    icon: "Bot",
    name: "任务与权限",
    en: "AGENT SECURITY",
    count: agentFindings(props.scan.findings).length,
    desc: "任务、工具与能力边界",
    status: props.scan.metadata.scanners.agent_security?.status,
  },
  {
    key: "components",
    icon: "GitCompareArrows",
    name: mode.value === 'download' ? '工具能力' : '声明与能力',
    en: "INTENT & CAPABILITY",
    count: state.componentSecurity?.summary?.assessments ?? "—",
    desc: "四类关系、模型状态与源码证据",
    status: state.componentSecurity?.status || "unavailable",
  },
].filter(module => professional.value || (mode.value === 'download' ? module.key !== 'agents' : !['agents','components'].includes(module.key))));
</script>
<template>
  <div class="page-heading overview-heading">
    <div>
      <p class="workspace-label">
        {{ workspace ? "项目 / 扫描结果" : "项目 / 风险总览" }}
      </p>
      <h1>
        {{
          workspace ? "检查完了，先看这几处。" : "逐项确认，再回到代码里处理。"
        }}
      </h1>
      <p>
        {{
          workspace
            ? "先核对扫描覆盖，再从高风险项开始。每个发现都可以打开证据。"
            : "按类别或文件路径缩小范围，打开一项查看定位和处理建议。"
        }}
      </p>
    </div>
    <RouterLink class="button secondary" :to="`/scan/${scan.id}/report`"
      ><Icon name="FileText" :size="17" />查看报告</RouterLink
    >
  </div>
  <div class="module-grid">
    <RouterLink
      v-for="(module, i) in modules"
      :key="module.key"
      :to="{path: `/scan/${scan.id}/${module.key}`, query: route.query}"
      class="module-card"
      :class="`module-${i}`"
      ><div class="module-card-top">
        <span class="module-icon"><Icon :name="module.icon" :size="23" /></span
        ><Icon name="ArrowUpRight" :size="18" />
      </div>
      <h2>{{ module.name }}</h2>
      <div class="module-number">
        <b>{{
          ["unavailable", "disabled", "failed", "not_applicable"].includes(module.status) &&
          module.count === 0
            ? "—"
            : module.count
        }}</b
        ><span>{{ module.key === "components" ? "项关系" : "项发现" }}</span>
      </div>
      <div class="module-card-bottom">
        <span>{{ module.desc }}</span
        ><Badge
          v-if="module.status"
          :value="module.status"
          kind="status"
        /><span v-else class="tiny-arrow">查看全部 →</span>
      </div></RouterLink
    >
  </div>
  <div class="overview-lower">
    <section class="panel priorities">
      <div class="panel-heading">
        <h2>
          <Icon name="Zap" :size="19" />{{
            workspace ? "优先关注" : "风险清单"
          }}
        </h2>
        <span class="micro-tag">{{
          workspace ? "按风险等级排序" : `${matches.length} 项`
        }}</span>
      </div>
      <div v-if="!workspace" class="panel-toolbar">
        <div class="search-field">
          <Icon name="Search" :size="16" /><input
            v-model="search"
            @input="page = 1"
            placeholder="搜索风险名称或文件路径"
            aria-label="搜索全部风险"
          />
        </div>
        <select v-model="filter" @change="page = 1" aria-label="筛选风险类别">
          <option value="all">全部类型</option>
          <option value="secret">Secret</option>
          <option value="license">许可证</option>
          <option v-if="professional || agentFindings(scan.findings).length" value="agent">Agent 安全</option>
          <option v-if="mode === 'download' || scan.findings.some(f => f.category === 'tool_capability')" value="tool_capability">工具能力</option>
        </select>
      </div>
      <FindingsTable
        :items="
          workspace
            ? sorted.slice(0, 5)
            : matches.slice((page - 1) * 20, page * 20)
        "
        :compact="true"
        @select="(item) => emit('detail', item)"
      />
      <div class="table-footer">
        <span>{{
          workspace
            ? "查看原始定位与脱敏证据"
            : "发现数量不等于凭据出现位置数量"
        }}</span
        ><RouterLink
          v-if="workspace"
          :to="`/scan/${scan.id}/overview`"
          class="text-button"
          >查看全部 <Icon name="ArrowRight" :size="15"
        /></RouterLink>
        <div v-else class="pagination">
          <button :disabled="page === 1" @click="page--" aria-label="上一页">
            <Icon name="ChevronRight" class="rotate" :size="15" /></button
          ><span
            >{{ page }} /
            {{ Math.max(1, Math.ceil(matches.length / 20)) }}</span
          ><button
            :disabled="page * 20 >= matches.length"
            @click="page++"
            aria-label="下一页"
          >
            <Icon name="ChevronRight" :size="15" />
          </button>
        </div>
      </div>
    </section>
    <section class="panel risk-distribution">
      <div class="panel-heading">
        <h2>风险分布</h2>
        <Icon name="SlidersHorizontal" :size="18" />
      </div>
      <RiskChart :findings="scan.findings" />
      <div class="risk-conclusion">
        <span>当前最高风险</span
        ><b :class="`text-${risk.level}`">{{ risk.label }}</b>
      </div>
      <p class="chart-note">
        已获得 {{ coverage.available }} / {{ coverage.total }}
        个适用模块的有效结果。等级反映发现项，不代表整体安全认证。
      </p>
    </section>
  </div>
  <div v-if="professional || mode === 'download'" class="data-visual-grid section-gap">
    <CapabilityRadar
      :tools="radarTools"
      :status="radarStatus"
      :noun="componentTools.length ? '组件' : '工具'"
    />
    <ModuleRiskChart :scan="scan" />
  </div>
  <div v-if="professional || !scan.metadata.scan_profile" class="insight-banner">
    <span class="insight-icon"><Icon name="GitBranch" :size="26" /></span>
    <div>
      <h3>{{ professional ? '想知道工具为什么被标记？' : '项目中包含 Agent？' }}</h3>
      <p>{{ professional ? '打开绑定关系，看看它服务哪个任务、具备哪些能力。' : '进入专业分析，查看任务、工具绑定和权限边界。已有发现仍会保留在报告中。' }}</p>
    </div>
    <RouterLink :to="{path: `/scan/${scan.id}/agents`, query: {...route.query, professional: '1'}}" class="button secondary"
      >{{ professional ? '查看 Agent 关系图' : '查看专业分析' }} <Icon name="ArrowUpRight" :size="16"
    /></RouterLink>
  </div>
</template>
