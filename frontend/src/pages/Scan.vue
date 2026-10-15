<script setup>
import { watch, computed, ref } from "vue";
import { useRoute } from "vue-router";
import { state, loadScan } from "../state";
import { formatDate, hasExample } from "../domain";
import Icon from "../components/Icon.vue";
import Badge from "../components/Badge.vue";
import Coverage from "../components/Coverage.vue";
import DetailDrawer from "../components/DetailDrawer.vue";
import Overview from "./sections/Overview.vue";
import Secrets from "./sections/Secrets.vue";
import Licenses from "./sections/Licenses.vue";
import Agents from "./sections/Agents.vue";
import Components from "./sections/Components.vue";
import Report from "./sections/Report.vue";
import CrystalCat from "../components/WatercolorCat.vue";
import { journeys, scanJourney } from "../journeys";
const route = useRoute(),
  detail = ref(null),
  detailKind = ref("finding");
const scan = computed(() => state.scan),
  section = computed(() => route.params.section || "workspace");
const journey = computed(() => journeys[scanJourney(route.params.id, route.query.mode, scan.value)]);
watch(
  () => route.params.id,
  (id) => {
    detail.value = null;
    loadScan(id);
  },
  { immediate: true },
);
watch(section, () => (detail.value = null));
function open(item, kind) {
  detailKind.value =
    kind || (item.category === "secret" ? "secret" : "finding");
  detail.value = item;
}
</script>
<template>
  <div v-if="state.scanLoading" class="panel empty-state loading-large">
    <Icon name="LoaderCircle" class="spin" :size="30" />
    <h3>正在读取扫描结果</h3>
    <p>加载保存的风险与证据</p>
  </div>
  <div v-else-if="state.scanError" class="panel empty-state loading-large">
    <Icon name="AlertTriangle" :size="34" />
    <h3>暂时无法读取这次扫描</h3>
    <p>{{ state.scanError }}</p>
    <div class="inline-actions">
      <button class="button secondary" @click="loadScan(route.params.id)">
        重试</button
      ><RouterLink :to="{path: '/history', query: {mode: scanJourney(route.params.id, route.query.mode)}}" class="button primary"
        >返回扫描历史</RouterLink
      >
    </div>
  </div>
  <template v-else-if="scan"
    ><div class="result-journey"><CrystalCat small :mood="scan.findings?.length ? 'warning' : scan.status === 'completed' ? 'success' : 'thinking'" /><div><small>{{ journey.audience }} · {{ journey.title }}</small><template v-if="section === 'components'"><h1>{{ journey.scene === 'install_precheck' ? '工具能做什么？' : '声明与能力是否一致？' }}</h1><p>{{ journey.scene === 'install_precheck' ? '核对用途声明与静态能力，查看访问范围和代码证据，再决定是否安装。' : '核对用途声明与静态能力，查看不一致、待复核项及代码证据。' }}</p></template><p v-else>{{ journey.scene === 'install_precheck' ? '先看工具的能力与访问范围，再决定是否安装。' : journey.title === 'Agent 专项审查' ? '逐项核对任务、绑定工具和敏感权限。' : '先处理疑似凭据，再确认开源使用与检查缺口。' }}</p></div></div><div class="scan-context">
      <div class="context-project">
        <span class="project-icon"><Icon name="Folder" :size="21" /></span>
        <div>
          <b>{{ scan.project_name }}</b
          ><span
            >{{ hasExample(scan) ? "合成示例" : "项目扫描" }}<i>·</i
            >{{ formatDate(scan.created_at) }}<i>·</i
            ><span class="scan-id-label">扫描编号：<code :title="scan.id">{{ scan.id.slice(0, 8) }}</code></span></span
          >
        </div>
      </div>
      <Badge :value="scan.status" kind="status" />
    </div>
    <Coverage :scan="scan" />
    <p v-if="scan.metadata.scan_profile" class="scan-plan-note">
      检查方案：{{ journey.title }} · v{{ scan.metadata.scan_profile.version }}。
      执行范围已保存在本次记录中，不随当前入口切换。
    </p>
    <div v-if="scan.metadata.scan_profile?.agent_review_recommended" class="alert" role="status">
      <span>源码中识别到 Agent 或 MCP 相关结构。本次只做发布前基础检查，尚未审查任务与工具权限。</span>
      <RouterLink to="/new?mode=agent">提交到 Agent 专项审查 →</RouterLink>
    </div>
    <Overview
      v-if="['workspace', 'overview'].includes(section)"
      :scan="scan"
      :workspace="section === 'workspace'"
      @detail="open" />
    <Secrets
      v-else-if="section === 'secrets'"
      :scan="scan"
      @detail="(item) => open(item, 'secret')" />
    <Licenses
      v-else-if="section === 'licenses'"
      :scan="scan"
      @detail="(item) => open(item, 'license')" />
    <Agents v-else-if="section === 'agents'" :scan="scan" @detail="open" />
    <Components v-else-if="section === 'components'" :scan-id="scan.id" />
    <Report v-else-if="section === 'report'" :scan="scan" @detail="open" />
    <div v-else class="panel empty-state">
      <h2>页面不存在</h2>
      <RouterLink :to="`/scan/${scan.id}/workspace`">回到结果概览</RouterLink>
    </div>
    <DetailDrawer
      :scan-id="scan.id"
      :item="detail"
      :kind="detailKind"
      @close="detail = null"
  /></template>
</template>
<style scoped>
.result-journey h1 { margin: 8px 0; font-size: clamp(24px, 2.4vw, 32px); line-height: 1.35; color: #243e4b; }
.scan-id-label { white-space: nowrap; }
@media (max-width: 760px) { .scan-id-label { display: none; } }
</style>
