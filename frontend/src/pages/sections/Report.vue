<script setup>
import { state } from "../../state";
import {
  relations,
  relationCounts,
  assessmentRows,
  statusLabel,
  relationshipCoverageText,
} from "../../component-security";
import { localize } from "../../language";
import { computed, ref } from "vue";
import { downloadReportPdf } from '../../report-pdf';
import Icon from "../../components/Icon.vue";
import Badge from "../../components/Badge.vue";
import RiskChart from "../../components/RiskChart.vue";
import {
  formatDate,
  sortFindings,
  categoryLabels,
  percent,
  coverageSummary,
  moduleNames,
  statusLabels,
  hasExample,
} from "../../domain";
const props = defineProps({ scan: Object });
defineEmits(["detail"]);
const coverage = computed(() => coverageSummary(props.scan));
const findings = computed(() => sortFindings(props.scan.findings));
const recommendations = computed(() => [
  ...new Set(findings.value.flatMap((f) => f.remediation || [])),
]);
const componentCounts = computed(() => relationCounts(state.componentSecurity));
const modelUsed = computed(
  () =>
    assessmentRows(state.componentSecurity).filter(
      (row) => row.assessment.model?.used === true,
    ).length,
);
const semanticModels = computed(() => [...new Map(
  assessmentRows(state.componentSecurity)
    .filter(row => row.assessment.model?.used === true)
    .map(row => {
      const model = row.assessment.model;
      return [`${model.name}@${model.version}`, model];
    }),
).values()]);
const paper = ref(null), exporting = ref(false), exportMessage = ref('');
async function downloadPdf() {
  if(exporting.value)return;
  exporting.value=true;exportMessage.value='正在生成 PDF，请稍等…';
  try { await downloadReportPdf(paper.value,props.scan.project_name);exportMessage.value='PDF 已生成，请查看浏览器下载列表。'; }
  catch { exportMessage.value='PDF 生成失败，请重试；也可以在 Chrome / Edge 中打开本页，使用打印保存。'; }
  finally { exporting.value=false; }
}
function print() {
  exportMessage.value='如果没有出现打印窗口，请使用“下载 PDF”，或在 Chrome / Edge 中打开本页后打印。';
  try { window.print(); } catch { /* The visible message supplies an alternative. */ }
}
</script>
<template>
  <div class="page-heading no-print">
    <div>
      <p class="eyebrow">YOUR SECURITY REPORT</p>
      <h1>让审查结果，成为下一步行动。</h1>
      <p>汇总发现、证据和处置建议，保留本次检测的实际覆盖边界。</p>
    </div>
    <div class="inline-actions">
      <a class="button secondary" :href="`/api/scans/${scan.id}/report`"
        ><Icon name="Download" :size="17" />导出 JSON</a
      ><button class="button secondary" @click="print">
        <Icon name="Printer" :size="17" />打印
      </button><button class="button primary" @click="downloadPdf" :disabled="exporting">
        <Icon name="Download" :size="17" />{{ exporting ? '正在生成 PDF…' : '下载 PDF' }}
      </button>
    </div>
  </div>
  <p v-if="exportMessage" class="report-export-message no-print" role="status">{{ exportMessage }}</p>
  <article ref="paper" class="report-paper">
    <header class="report-header">
      <div>
        <span class="report-wordmark"><Icon name="ShieldCheck" :size="26" />源界</span
        >
        <p class="eyebrow">OPEN SOURCE SECURITY AUDIT</p>
        <h1>项目安全审查报告</h1>
        <p>{{ scan.project_name }}</p>
      </div>
      <div class="report-stamp">
        <Icon name="FileCheck2" :size="38" /><span>静态 · 本地 · 可追溯</span>
      </div>
    </header>
    <div class="report-meta">
      <span
        >扫描时间 <b>{{ formatDate(scan.created_at) }}</b></span
      ><span
        >数据来源
        <b>{{
          hasExample(scan) ? "合成示例 · 实际执行" : "用户上传项目"
        }}</b></span
      ><span
        >扫描版本 <b>{{ scan.version }}</b></span
      ><span>扫描状态 <Badge :value="scan.status" kind="status" /></span>
    </div>
    <section class="report-section">
      <div class="report-section-title">
        <span>01</span>
        <h2>审查摘要与覆盖</h2>
      </div>
      <div class="report-summary">
        <RiskChart :findings="scan.findings" />
        <div class="report-coverage">
          <div v-for="(label, key) in coverage.modules" :key="key">
            <span>{{ label }}</span
            ><Badge
              :value="coverage.scanners[key]?.status || 'unavailable'"
              kind="status"
            />
          </div>
          <p>
            模块执行状态与风险等级分别描述“是否完成检查”和“发现了什么”。未发现风险，不代表没有风险。
          </p>
        </div>
      </div>
      <p class="report-note">
        本次发现 {{ scan.findings.length }} 项风险；{{ coverage.available }} / {{ coverage.total }}
        个适用模块产生有效结果。项目代码未被安装或执行。许可证完整评估库存请结合许可证明细查看。
        <span v-if="scan.metadata.scan_profile">检查方案：{{ scan.metadata.scan_profile.id }} · v{{ scan.metadata.scan_profile.version }}。</span>
      </p>
    </section>
    <section class="report-section">
      <div class="report-section-title">
        <span>02</span>
        <h2>风险发现与证据</h2>
      </div>
      <div v-if="!findings.length" class="report-note">
        当前规则覆盖下未产生风险发现，请同时关注检测覆盖与分析局限。
      </div>
      <div v-for="(f, index) in findings" :key="f.id" class="report-finding">
        <div class="report-finding-heading">
          <span class="finding-number">{{
            String(index + 1).padStart(2, "0")
          }}</span>
          <h3>{{ localize(f.title) }}</h3>
          <Badge :value="f.severity" />
        </div>
        <p class="muted small-text">
          {{ categoryLabels[f.category] }} · {{ f.rule_id }} · 置信度
          {{ percent(f.confidence) }}
        </p>
        <div class="report-evidence" v-for="(ev, i) in f.evidence" :key="i">
          <code
            >{{ ev.source_span?.path }}:{{ ev.source_span?.start_line }}</code
          >
          <p>{{ ev.masked_excerpt }}</p>
        </div>
        <ul class="readable-list">
          <li v-for="reason in f.rationale" :key="reason">
            {{ localize(reason) }}
          </li>
        </ul>
      </div>
    </section>
    <section class="report-section">
      <div class="report-section-title">
        <span>03</span>
        <h2>建议与下一步</h2>
      </div>
      <ol class="recommendation-list">
        <li v-for="step in recommendations" :key="step">
          {{ localize(step) }}
        </li>
        <li v-if="!recommendations.length">
          检查模块覆盖，结合项目使用方式开展人工复核。
        </li>
      </ol>
    </section>
    <section class="report-section">
      <div class="report-section-title">
        <span>04</span>
        <h2>方法与使用边界</h2>
      </div>
      <p>
        {{ scan.metadata.scan_profile && !scan.metadata.scan_profile.executed_modules.includes('agent_security') ? '本次未执行 Agent 工具暴露评分。' : `工具暴露评分方法：${scan.metadata.context_model || '未记录'}。` }}声明与能力分析状态及模型参与情况见第 05 节。本报告是静态分析的辅助结果，不构成整体安全保证或法律合规结论。动态绑定和未启用的检测能力不能被视为已验证。
      </p>
      <ul v-if="scan.warnings.length" class="readable-list">
        <li v-for="(warning, i) in scan.warnings" :key="i">{{ warning }}</li>
      </ul>
      <p class="report-id">扫描 ID：{{ scan.id }}</p>
    </section>
    <section class="report-section">
      <div class="report-section-title">
        <span>05</span>
        <h2>声明与能力关系</h2>
      </div>
      <template v-if="state.componentSecurity"
        ><p>
          场景：{{
            state.componentSecurity.scene === "install_precheck"
              ? "安装前检查"
              : "发布前检查"
          }}
          · 分析状态：{{ statusLabel(state.componentSecurity.status) }}
        </p>
        <div class="report-relations">
          <span
            v-for="(meta, key) in relations"
            :key="key"
            :style="{ color: meta.color }"
            >{{ meta.label }} <b>{{ componentCounts[key] }}</b></span
          >
        </div>
        <p>
          {{ relationshipCoverageText(state.componentSecurity) }}
          分数表示不一致风险，不是恶意概率；待复核、证据不足不等于已确认漏洞。
        </p>
        <p v-for="model in semanticModels" :key="`${model.name}@${model.version}`" class="report-model">
          实际参与的本地语义模型：{{ model.name }} ·
          版本 <span :title="model.version">{{ String(model.version).slice(0, 8) }}</span>
          · 参与 {{ modelUsed }} 项判断；完整版本见声明能力 JSON。
        </p>
        <p
          v-for="warning in state.componentSecurity.warnings || []"
          :key="warning"
        >
          {{ warning }}
        </p></template
      >
      <p v-else>
        声明能力数据暂不可用：{{ state.componentError || "无新版模块数据" }}
      </p>
      <div class="inline-actions no-print">
        <RouterLink :to="`/scan/${scan.id}/components`" class="text-button"
          >查看关系与证据 →</RouterLink
        ><a
          :href="`/api/scans/${scan.id}/component-security`"
          class="text-button"
          >导出声明能力 JSON ↗</a
        >
      </div>
    </section>
    <footer class="report-footer">
      <span>源界 · 开源前，多一份安心</span><span>敏感凭据已脱敏 · 请结合人工审查使用</span>
    </footer>
  </article>
</template>
