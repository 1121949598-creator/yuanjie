<script setup>
import {
  ref,
  onBeforeUnmount,
  computed,
  inject,
  watch,
} from "vue";
import { useRouter, useRoute } from "vue-router";
import Icon from "../components/Icon.vue";
import { journeys, journeyKey, rememberJourney } from "../journeys";
const mode = computed(() => journeyKey(route.query.mode));
const journey = computed(() => journeys[mode.value]);
const scene = computed(() => journey.value.scene);
const guide = computed(() => ({
  download: {
    title: '下载工具怎么检查？',
    introduction: '准备使用 Skill、MCP 或开源工具？先从原项目下载源码 ZIP，再在下方导入，查看它会接触哪些文件、网络和凭据，以及能否执行命令。',
    keep: '保留 SKILL.md、源码、依赖声明与 MCP 配置',
    coverage: '检查组件声明与静态可见能力，并保留来源与脱敏证据。',
  },
  project: {
    title: '自己的项目怎么检查？',
    introduction: '准备公开自己的项目？把源码和配置打包为 ZIP，在下方上传，检查疑似凭据、许可证与依赖声明。',
    keep: '保留源码、README、LICENSE、依赖声明与配置',
    coverage: '上传项目源码、配置、README、LICENSE 和依赖声明，检查疑似凭据、许可证及依赖信息。',
  },
  agent: {
    title: 'Agent 专项怎么检查？',
    introduction: '准备检查 Agent 的任务和权限？将 Agent 源码打包为 ZIP，在下方导入，查看任务声明、Tool 绑定、敏感能力及声明—能力关系。',
    keep: '保留任务声明、Agent / Tool 源码、依赖与配置',
    coverage: '静态解析已支持的 Python Agent / Tool 结构并保留证据。动态发现、复杂绑定或声明缺失时，可能需要人工复核。',
  },
})[mode.value]);
import { uploadScan } from "../api";
import ScanProgress from "../components/ScanProgress.vue";
import { state } from "../state";
import { assistant, resetAssistant } from '../assistant';
const route = useRoute();
const router = useRouter(),
  file = ref(null),
  input = ref(null),
  drag = ref(false),
  error = ref(""),
  busy = ref(false),
  phase = ref(""),
  progress = ref(0),
  seconds = ref(0),
  selectedName = ref("");
const setArtwork = inject("page-artwork", () => {});
watch([busy, phase, file, error], () => {
  Object.assign(assistant, { phase: busy.value ? phase.value : '', fileReady: !!file.value, error: error.value });
}, { immediate: true });
watch(busy, (value) => setArtwork(value ? "scan" : null), {
  immediate: true,
});
let clock;
let mounted = true;
const limit = computed(() => state.system?.max_upload_bytes || 104857600);
onBeforeUnmount(() => {
  resetAssistant();
  mounted = false;
  setArtwork(null);
  clearInterval(clock);
});
function choose(value) {
  error.value = "";
  if (!value) return;
  file.value = null;
  if (!value.name.toLowerCase().endsWith(".zip")) {
    error.value = "请选择 ZIP 格式的项目文件。";
    return;
  }
  if (value.size > limit.value) {
    error.value = `ZIP 超过 ${Math.floor(limit.value / 1048576)} MiB 上传限制。`;
    return;
  }
  file.value = value;
}
function clearFile() {
  file.value = null;
  if (input.value) input.value.value = "";
}
function drop(e) {
  drag.value = false;
  choose(e.dataTransfer.files[0]);
}
async function start() {
  if (busy.value || !file.value) return;
  busy.value = true;
  error.value = "";
  seconds.value = 0;
  progress.value = 0;
  phase.value = "uploading";
  selectedName.value = file.value?.name;
  clock = setInterval(() => seconds.value++, 1000);
  try {
    const data = await uploadScan(
      file.value,
      (p) => (progress.value = p),
      () => (phase.value = "analyzing"),
      scene.value,
      mode.value,
    );
    rememberJourney(data.scan_id, mode.value);
    if (mounted) await router.push(`/scan/${data.scan_id}/${journey.value.result}?mode=${mode.value}`);
  } catch (e) {
    error.value = e.message;
    busy.value = false;
  } finally {
    clearInterval(clock);
  }
}
</script>
<template>
  <ScanProgress v-if="busy" :phase="phase" :selected-name="selectedName" :progress="progress" :seconds="seconds" :mode="mode" />
  <div v-else class="project-import">
    <div class="page-heading">
      <div>
        <p class="workspace-label">{{ journey.audience }} / {{ journey.title }}</p>
        <h1>{{ journey.heading }}</h1>
      </div>
    </div>
    <div v-if="error" class="alert error" role="alert">
      <Icon name="AlertTriangle" /><span>{{ error }}</span
      ><button class="icon-button" @click="error = ''" aria-label="关闭错误">
        <Icon name="X" :size="17" />
      </button>
    </div>
    <section class="download-guide" aria-labelledby="download-guide-title">
      <h2 id="download-guide-title"><Icon name="FileText" :size="18" />{{ guide.title }}</h2>
      <p>{{ guide.introduction }}</p>
      <p v-if="mode === 'project'">需要审查 Agent 的任务与权限？请使用 <RouterLink to="/new?mode=agent">Agent 专项审查</RouterLink>。</p>
      <ul class="download-checklist">
        <li><Icon name="Check" :size="17" /><span>{{ guide.keep }}</span></li>
        <li><Icon name="X" :size="17" /><span>去掉 <code>.venv</code>、<code>node_modules</code> 和缓存</span></li>
        <li><Icon name="Eye" :size="17" /><span>{{ mode === 'download' ? '确认来源，并有权下载和提交源码检查' : '确认你有权上传这些代码与配置' }}</span></li>
      </ul>
      <p class="download-scope">这里只静态读取源码，不自动访问链接、下载或安装工具，也不运行项目或启动 MCP Server。</p>
      <details>
        <summary>检测范围与结果说明</summary>
        <p>{{ guide.coverage }}先看模块是否完整执行；“未发现”不等于绝对安全，{{ mode === 'download' ? '安装' : '发布或使用' }}决定仍需结合证据和人工复核。</p>
        <p>{{ state.system?.license_provider_configured ? '当前服务已配置许可证工具，执行情况以本次扫描的模块状态为准。' : '当前服务未配置许可证工具；许可证模块会明确显示不可用，其他模块以实际覆盖情况为准。' }}</p>
      </details>
    </section>
    <div class="upload-grid upload-grid-download">
      <section class="panel upload-panel">
        <div class="panel-heading">
          <h2><Icon :name="mode === 'download' ? 'Download' : mode === 'agent' ? 'Bot' : 'UploadCloud'" />{{ mode === 'download' ? '导入下载的工具包' : mode === 'agent' ? '导入 Agent 源码' : '上传自己的项目' }}</h2>
          <span class="upload-format"
            >.zip / {{ Math.floor(limit / 1048576) }} MiB 以内</span
          >
        </div>
        <div
          class="dropzone"
          :class="{ dragging: drag, selected: file }"
          @dragover.prevent="drag = true"
          @dragleave.prevent="drag = false"
          @drop.prevent="drop"
        >
          <div class="upload-icon">
            <Icon :name="file ? 'FileArchive' : 'UploadCloud'" :size="38" />
          </div>
          <h3>{{ file ? file.name : "把 ZIP 放在这里" }}</h3>
          <p>
            {{
              file
                ? `${(file.size / 1048576).toFixed(2)} MiB · 已准备好扫描`
                : "或从电脑中选择一个 ZIP 文件"
            }}
          </p>
          <button class="button secondary" @click="input.click()">
            <Icon :name="file ? 'RefreshCw' : 'Folder'" :size="17" />{{
              file ? "更换文件" : "选择文件"
            }}</button
          ><input
            ref="input"
            type="file"
            accept=".zip"
            hidden
            @change="choose($event.target.files[0])"
          /><small
            >{{ mode === 'download' ? 'Skill（SKILL.md）/ MCP 配置与源码' : mode === 'agent' ? '已支持的 Python Agent / Tool 结构' : '项目源码 / 配置 / 依赖声明' }} · 最大
            {{ Math.floor(limit / 1048576) }} MiB</small
          >
          <button
            v-if="file"
            class="text-button remove-upload"
            @click="clearFile"
          >
            移除文件
          </button>
        </div>
        <div class="upload-bottom">
          <span
            ><Icon name="LockKeyhole" :size="16" /> 静态读取，不运行项目</span
          ><button class="button primary" :disabled="!file" @click="start()">
            {{ journey.action }} <Icon name="ArrowRight" :size="17" />
          </button>
        </div>
      </section>
    </div>
  </div>
</template>
<style scoped>
.upload-grid.upload-grid-download { grid-template-columns: minmax(0, 1fr); }
.download-guide { margin: 0 0 24px; padding: 18px 20px; background: #edf6f8e8; border-left: 3px solid #79adc6; }
.download-guide h2 { display: flex; align-items: center; gap: 8px; margin: 0 0 8px; font-size: 17px; }
.download-guide p { margin: 8px 0; font-size: 14px; line-height: 1.75; color: #4d6978; }
.download-checklist { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px 20px; list-style: none; padding: 0; margin: 14px 0; }
.download-checklist li { display: flex; align-items: flex-start; gap: 8px; font-size: 13px; }
.download-checklist svg { flex-shrink: 0; margin-top: 3px; color: #658078; }
.download-checklist code { overflow-wrap: anywhere; color: #3c5680; }
.download-guide .download-scope { font-size: 12px; }
.download-guide details { border-top: 1px solid #d5e5e8; padding-top: 10px; }
.download-guide summary { cursor: pointer; color: #304462; font-size: 13px; }
.download-guide summary:focus-visible { outline: 2px solid #176ac0; outline-offset: 4px; }
@media (max-width: 760px) {
  .download-checklist { grid-template-columns: minmax(0, 1fr); gap: 8px; }
  .download-guide { padding: 14px 16px; }
}
</style>
