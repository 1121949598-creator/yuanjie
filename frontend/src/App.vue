<script setup>
import { computed, onMounted, ref, provide, watch } from "vue";
import { useRoute } from "vue-router";
import Icon from "./components/Icon.vue";
import RiverArt from "./components/RiverArt.vue";
import Brand from "./components/Brand.vue";
import TaskPet from './components/TaskPet.vue';
import CurrentMotion from './components/CurrentMotion.vue';
import { state, loadSystem, resetScanSession } from "./state";
import { journeys, journeyKey, scanJourney } from "./journeys";
import { sidebarRiskCounts } from './sidebar-risk';
import { resultLabels, resultNavigation } from './result-navigation';
const route = useRoute(),
  menu = ref(false),
  help = ref(false);
// The floating switch is retired; system reduced-motion remains authoritative.
onMounted(() => {
  document.documentElement.dataset.motion = 'on';
  window.dispatchEvent(new Event('openguard-motion'));
});
const scanId = computed(() => route.params.id);
const lastResultJourney = ref('project');
watch(() => route.path, (path) => {
  if (['/', '/entry'].includes(path)) {
    resetScanSession();
    lastResultJourney.value = 'project';
    menu.value = false;
    help.value = false;
  }
}, { immediate: true, flush: 'sync' });
watch(() => state.scan?.id, (id) => {
  if (id && id === scanId.value) lastResultJourney.value = scanJourney(id, route.query.mode, state.scan);
});
// Keep results within a session; returning home/entry starts a fresh session.
const resultScanId = computed(() => scanId.value || state.scan?.id);
const section = computed(() => route.params.section || "workspace");
const activeJourney = computed(() => scanId.value ? scanJourney(scanId.value, route.query.mode, state.scan) : journeyKey(route.query.mode));
const resultJourney = computed(() => resultScanId.value
  ? scanJourney(resultScanId.value, scanId.value ? route.query.mode : lastResultJourney.value, state.scan)
  : activeJourney.value);
const professional = computed(() => resultJourney.value === 'agent' || (!state.scan?.metadata?.scan_profile && scanId.value && route.query.professional === '1'));
const riskCounts = computed(() => sidebarRiskCounts(
  state.scan?.id === resultScanId.value ? state.scan : null,
  state.componentSecurity,
));
const selectedScan = computed(() => state.scan?.id === resultScanId.value ? state.scan : null);
const nav = computed(() => resultNavigation(selectedScan.value, {
  mode: resultJourney.value, professional: professional.value, componentSecurity: state.componentSecurity,
}));
const title = computed(() =>
  route.path === "/new"
    ? journeys[activeJourney.value].title
    : route.path === '/examples' ? '已有示例' : route.path === "/history"
      ? "扫描历史"
      : nav.value.find((n) => n[0] === section.value)?.[2] || resultLabels[section.value] || "检查工作台",
);
const artworkOverride = ref(null);
provide("page-artwork", (value) => (artworkOverride.value = value));
watch(
  () => route.fullPath,
  () => (artworkOverride.value = null),
);
const artwork = computed(
  () =>
    artworkOverride.value ||
    (['/history', '/examples'].includes(route.path) ? "history" : route.path === "/new"
      ? activeJourney.value === 'download' ? 'download' : activeJourney.value === 'agent' ? 'agent' : 'upload'
      : section.value === "agents"
        ? "scan"
        : "report"),
);
const verse = computed(
  () =>
    ({
      upload: "好的安全，始于一次简单的上传。",
      scan: "每一次检测，都向更安全前进一步。",
      report: "看见风险，也是守护美好的开始。",
    })[artwork.value],
);
onMounted(loadSystem);
</script>
<template>
  <CurrentMotion />
  <TaskPet v-if="['/', '/entry'].includes(route.path)" />
  <RouterView v-if="['/', '/entry'].includes(route.path)" />
  <div v-else class="app-shell">
    <aside class="sidebar" :class="{ open: menu }">
      <Brand :turn-duration="12" />
      <div class="sidebar-content">
        <RouterLink class="new-scan-button" :to="{path: '/new', query: {mode: activeJourney}}" @click="menu = false"
          ><Icon name="Plus" :size="18" /> 新建扫描</RouterLink
        >
        <section class="sidebar-group" aria-labelledby="check-group-label">
        <h2 id="check-group-label" class="sidebar-group-label">开始检查</h2>
        <div class="sidebar-journeys">
          <RouterLink v-for="(item, key) in journeys" :key="key" :to="`/new?mode=${key}`" :class="{selected: activeJourney === key}" @click="menu = false"><Icon :name="key === 'download' ? 'Download' : key === 'agent' ? 'Bot' : 'UploadCloud'" :size="17" /><span>{{ item.title }}</span></RouterLink>
        </div>
        </section>
        <section class="sidebar-group result-group" aria-labelledby="result-group-label">
        <h2 id="result-group-label" class="sidebar-group-label">本次结果</h2>
        <p v-if="selectedScan" class="sidebar-current-project" :title="selectedScan.project_name">{{ selectedScan.project_name }}</p>
        <nav v-if="nav.length" aria-label="本次扫描结果">
          <template v-for="[key, icon, label, hint] in nav" :key="key"
            ><RouterLink
              v-if="resultScanId"
              :to="{path: `/scan/${resultScanId}/${key}`, query: {mode: resultJourney, ...(scanId && route.query.professional === '1' ? {professional: '1'} : {})}}"
              :class="{ active: !!scanId && section === key }"
              :title="hint"
              :aria-current="scanId && section === key ? 'page' : undefined"
              @click="menu = false"
              ><Icon :name="icon" /><span>{{ label }}</span
              ><span
                v-if="riskCounts[key] > 0"
                class="nav-count"
                :data-risk-section="key"
                :style="{'--risk-badge-size': riskCounts[key] >= 1000 ? '36px' : riskCounts[key] >= 100 ? '32px' : '24px'}"
                :title="`${label}：${riskCounts[key]} 项${key === 'components' ? '声明与能力不一致' : '风险发现'}`"
                :aria-label="`${riskCounts[key]} 项${key === 'components' ? '声明与能力不一致' : '风险发现'}`"
                >{{ riskCounts[key] }}</span
              ></RouterLink
            ></template
          >
        </nav>
        <p v-else class="sidebar-result-empty">{{ scanId && state.scanLoading ? '正在读取本次结果…' : scanId && state.scanError ? '结果读取失败，请在页面中重试或从扫描历史重新打开。' : '上传源码或运行示例后，在这里查看结果。' }}</p>
        </section>
        <section class="sidebar-group" aria-labelledby="records-group-label">
        <h2 id="records-group-label" class="sidebar-group-label">示例与记录</h2>
        <RouterLink class="history-nav examples-nav" :to="{path: '/examples', query: {mode: activeJourney}}" :class="{active: route.path === '/examples'}" @click="menu = false"><Icon name="FileText" :size="17" /><span>已有示例</span></RouterLink>
        <RouterLink
          class="history-nav"
          :to="{path: '/history', query: {mode: activeJourney}}"
          :class="{ active: route.path === '/history' }"
          @click="menu = false"
          ><Icon name="History" />扫描历史</RouterLink
        >
        </section>
      </div>
      <div class="sidebar-pet-slot"><TaskPet v-if="route.path !== '/mascot'" /></div>
      <div class="sidebar-bottom">
        <span class="status-dot" :class="{ offline: !state.system }"></span
        ><span>{{ state.system ? "本地服务已连接" : "本地服务未连接" }}</span
        ><span class="version">v{{ state.system?.version || "0.1.0" }}</span>
      </div>
    </aside>
    <button
      v-if="menu"
      class="mobile-backdrop"
      @click="menu = false"
      aria-label="收起导航"
    ></button>
    <div class="main-shell">
      <header class="topbar">
        <div class="breadcrumbs">
          <button
            class="icon-button mobile-menu"
            @click="menu = !menu"
            aria-label="切换导航"
          >
            <Icon name="Menu" /></button
          ><span class="breadcrumb-home">工作空间</span
          ><Icon name="ChevronRight" :size="14" /><b>{{ title }}</b>
        </div>
        <div class="topbar-actions">
          <span class="local-label"
            ><span class="status-dot"></span> 本地静态审查</span
          ><button
            class="icon-button"
            @click="help = !help"
            aria-label="查看使用说明"
          >
            <Icon name="HelpCircle" /></button
          >
        </div>
      </header>
      <div v-if="help" class="help-panel">
        <button
          class="icon-button close"
          @click="help = false"
          aria-label="关闭说明"
        >
          <Icon name="X" />
        </button>
        <h3>开始你的第一次安全审查</h3>
        <p>上传 Python 项目的 ZIP，或运行合成示例。扫描不会执行项目代码。</p>
        <p>
          根据所选入口查看实际执行的检查模块与覆盖状态。普通项目先看凭据和许可；任务与权限使用 Agent 专项。可在报告页下载 PDF 或导出 JSON。
        </p>
        <p>
          {{
            state.system?.license_provider_configured
              ? "许可证工具已配置，实际覆盖以扫描结果为准。"
              : "许可证外部工具未配置，相关结果将明确标记不可用。"
          }}
        </p>
      </div>
      <main class="content" :class="`scene-${artwork}`">
        <div class="workspace-scene"><RiverArt :variant="artwork" /></div>
        <div class="scene-verse" aria-hidden="true">
          {{ verse }}<span>守护</span>
        </div>
        <div class="workspace-page" :key="route.fullPath"><RouterView /></div>
      </main>
      <footer class="app-footer">
        <span>源界 · AI 开源项目安全审查</span><span>不执行目标代码 · 敏感凭据脱敏展示</span>
      </footer>
    </div>
  </div>
</template>
<style src="./workspace.css"></style>
<style src="./river-theme.css"></style>
<style src="./page-scenes.css"></style>
<style src="./redesign.css"></style>
<style src="./living.css"></style>
<style scoped>
.sidebar .sidebar-group { margin: 0 0 16px; }
.sidebar .sidebar-group-label { margin: 0 10px 6px; font-size: 12px; line-height: 1.5; font-weight: 500; color: #536c79; }
.sidebar .sidebar-journeys { margin: 0; gap: 2px; }
.sidebar .new-scan-button { margin-bottom: 16px; }
.sidebar .sidebar-current-project { margin: 0 10px 8px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; color: #243e4b; }
.sidebar .sidebar-result-empty { margin: 0 10px; color: #536c79; font-size: 12px; line-height: 1.7; }
.sidebar .sidebar-group a:focus-visible { outline: 2px solid #176ac0; outline-offset: -2px; }
.sidebar nav a { gap: 8px; padding-inline: 8px; }
.sidebar nav a > span:first-of-type { min-width: 0; font-size: 13px; }
.sidebar .nav-count {
  margin-left: auto; display: inline-flex; align-items: center; justify-content: center;
  width: var(--risk-badge-size); min-width: var(--risk-badge-size); height: var(--risk-badge-size);
  padding: 0; flex-shrink: 0; border-radius: 50%; background: #176ac0; color: #fff;
  font-size: 12px; font-weight: 600; line-height: 1; font-variant-numeric: tabular-nums;
}
</style>
