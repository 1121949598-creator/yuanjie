<script setup>
import { ref, computed, watch, onBeforeUnmount } from "vue";
import { api, encode } from "../../api";
import { state } from "../../state";
import {
  relations,
  statusLabel,
  relativeLocation,
  assessmentRows,
  relationCounts,
  evidenceFor,
  relationshipCoverageText,
} from "../../component-security";
import Icon from "../../components/Icon.vue";
import CrystalCat from "../../components/WatercolorCat.vue";
const props = defineProps({ scanId: String });
const dialog = ref(null);
let returnFocus;
watch(dialog, (el) => {
  if (el) {
    returnFocus = document.activeElement;
    el.focus();
  } else returnFocus?.focus();
});
function trap(event) {
  if (event.key !== "Tab") return;
  const items = dialog.value?.querySelectorAll(
    "button, a[href], input, [tabindex='0']",
  );
  if (!items?.length) return;
  const first = items[0],
    last = items[items.length - 1];
  if (
    event.shiftKey &&
    (document.activeElement === first ||
      document.activeElement === dialog.value)
  ) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}
const data = ref(null),
  loading = ref(false),
  error = ref(""),
  filter = ref("all"),
  search = ref(""),
  selected = ref(null);
let controller;
async function load(force = false) {
  if (!force && state.componentSecurity?.scan_id === props.scanId) {
    data.value = state.componentSecurity;
    return;
  }
  controller?.abort();
  const request = new AbortController();
  controller = request;
  loading.value = true;
  error.value = "";
  data.value = null;
  selected.value = null;
  try {
    const result = await api(
      `/scans/${encode(props.scanId)}/component-security`,
      { signal: request.signal },
    );
    if (!request.signal.aborted) {
      data.value = result;
      state.componentSecurity = result;
      state.componentError = "";
    }
  } catch (e) {
    if (!request.signal.aborted) error.value = e.message;
  } finally {
    if (!request.signal.aborted) loading.value = false;
  }
}
watch(
  () => props.scanId,
  () => {
    filter.value = "all";
    search.value = "";
    load();
  },
  { immediate: true },
);
onBeforeUnmount(() => controller?.abort());
const rows = computed(() => assessmentRows(data.value));
const counts = computed(() => relationCounts(data.value));
const filtered = computed(() =>
  rows.value.filter(
    (row) =>
      (filter.value === "all" || row.assessment.relation === filter.value) &&
      (row.entry.component?.name + " " + row.capability?.capability)
        .toLowerCase()
        .includes(search.value.toLowerCase()),
  ),
);
const evidence = computed(() =>
  selected.value ? evidenceFor(selected.value) : [],
);
const modelCount = computed(
  () => rows.value.filter((row) => row.assessment.model?.used === true).length,
);
</script>
<template>
  <section class="component-security">
    <div v-if="loading" class="panel empty-state">
      <Icon name="LoaderCircle" class="spin" />
      <h3>正在读取声明与能力</h3>
    </div>
    <div v-else-if="error" class="panel empty-state">
      <Icon name="CloudOff" />
      <h3>暂时无法读取</h3>
      <p>{{ error }}</p>
      <button class="button secondary" @click="load(true)">重试</button>
    </div>
    <template v-else-if="data">
      <div
        class="component-coverage"
        :class="{ degraded: data.status !== 'success' }"
      >
        <Icon :name="data.status === 'success' ? 'CircleCheck' : 'Info'" />
        <div>
          <b>关系分析：{{ statusLabel(data.status) }}</b>
          <p>
            {{ relationshipCoverageText(data) }}
          </p>
          <span
            v-for="warning in data.warnings || []"
            :key="warning"
            class="warning-code"
            >{{ warning }}</span
          >
        </div>
      </div>
      <div class="relation-stats">
        <button
          v-for="(meta, key) in relations"
          :key="key"
          :class="['relation-stat', { active: filter === key }]"
          :style="{ '--relation-color': meta.color }"
          :aria-pressed="filter === key"
          @click="filter = filter === key ? 'all' : key"
        >
          <span
            >{{ meta.label }}
            <Icon
              :name="
                key === 'inconsistent'
                  ? 'TriangleAlert'
                  : key === 'justified'
                    ? 'Check'
                    : 'CircleHelp'
              "
              :size="18" /></span
          ><b>{{ counts[key] }}</b
          ><small>{{ meta.hint }}</small>
        </button>
      </div>
      <div class="component-tools">
        <label
          ><Icon name="Search" :size="18" /><input
            v-model="search"
            placeholder="搜索组件或能力"
            aria-label="搜索组件或能力" /></label
        ><button
          class="text-button"
          @click="
            filter = 'all';
            search = '';
          "
        >
          显示全部（{{ rows.length }}）
        </button>
      </div>
      <div class="component-table panel" v-if="filtered.length">
        <table>
          <thead>
            <tr>
              <th>组件 / 声明用途</th>
              <th>静态能力</th>
              <th>关联判断</th>
              <th>模型 / 覆盖</th>
              <th>证据</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in filtered"
              :key="
                row.entry.component.component_id + row.assessment.assessment_id
              "
            >
              <td>
                <b>{{ row.entry.component.name }}</b
                ><small>{{ row.entry.component.component_type }}</small>
                <p>
                  {{
                    row.entry.component.declared_purpose || "未提取到声明用途"
                  }}
                </p>
              </td>
              <td>
                <code>{{
                  row.capability?.capability || row.assessment.capability_id
                }}</code
                ><small>{{ row.capability?.action }}</small>
              </td>
              <td>
                <span
                  class="relation-pill"
                  :style="{ color: relations[row.assessment.relation]?.color }"
                  >{{
                    relations[row.assessment.relation]?.label ||
                    row.assessment.relation
                  }}</span
                ><small
                  >不一致风险分数
                  {{
                    typeof row.assessment.score === "number"
                      ? row.assessment.score.toFixed(2)
                      : "—"
                  }}</small
                >
              </td>
              <td>
                <b>{{
                  row.assessment.model?.used === true
                    ? "模型已参与"
                    : "模型未参与"
                }}</b
                ><small>算法 {{ statusLabel(row.entry.result?.status) }}</small
                ><small>解析 {{ statusLabel(row.entry.parser?.status) }}</small>
              </td>
              <td>
                <button class="text-button" @click="selected = row">
                  查看依据 <Icon name="ArrowUpRight" :size="15" />
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="panel empty-state">
        <CrystalCat
          small
          :mood="data.status === 'success' ? 'thinking' : 'warning'"
        />
        <h3>
          {{ rows.length ? "没有符合筛选的判断" : "尚无可展示的关系判断" }}
        </h3>
        <p>零项判断不表示项目安全。请结合组件解析与模块覆盖情况查看。</p>
      </div>
      <details class="component-parser panel">
        <summary>组件与解析覆盖（{{ data.components?.length || 0 }}）</summary>
        <article
          v-for="entry in data.components || []"
          :key="entry.component?.component_id"
        >
          <b>{{ entry.component?.name }}</b>
          <p>
            声明提取：{{ statusLabel(entry.component?.extraction_status) }} ·
            解析器：{{ statusLabel(entry.parser?.status) }} · 算法：{{
              statusLabel(entry.result?.status)
            }}
          </p>
          <p>
            {{
              [
                ...(entry.component?.extraction_reasons || []),
                ...(entry.parser?.warnings || []),
                ...(entry.result?.warnings || []),
              ].join(" · ") || "没有额外覆盖警告"
            }}
          </p>
        </article>
      </details>
    </template>
    <div
      v-if="selected"
      class="component-detail-backdrop"
      @click.self="selected = null"
      @keydown.esc="selected = null"
    >
      <section
        ref="dialog"
        @keydown="trap"
        class="component-detail"
        role="dialog"
        aria-modal="true"
        aria-label="声明能力证据详情"
        tabindex="-1"
      >
        <header>
          <div>
            <span class="workspace-label">判断依据</span>
            <h2>{{ selected.entry.component.name }}</h2>
          </div>
          <button
            class="icon-button"
            aria-label="关闭证据详情"
            @click="selected = null"
          >
            <Icon name="X" />
          </button>
        </header>
        <h3>声明用途</h3>
        <p>
          {{ selected.entry.component.declared_purpose || "未提取到声明用途" }}
        </p>
        <p
          v-for="(span, i) in selected.entry.component.source_spans || []"
          :key="i"
        >
          <code>{{ relativeLocation(span) }}</code>
        </p>
        <h3>能力与判断</h3>
        <p>
          <b>{{ selected.capability?.capability }}</b> ·
          {{ relations[selected.assessment.relation]?.label }} · 不一致风险分数
          {{ selected.assessment.score }}
        </p>
        <p>
          动作：{{ selected.capability?.action }} · 范围：{{
            selected.capability?.resource
          }}
        </p>
        <p>
          静态控制：{{
            selected.capability?.controls?.join("、") || "未提取到"
          }}
        </p>
        <ul>
          <li v-for="(reason, i) in selected.assessment.reasons || []" :key="i">
            {{ reason.message }} <small>（{{ reason.code }}）</small>
          </li>
        </ul>
        <h3>不确定性</h3>
        <p>
          {{ selected.assessment.uncertainty?.level || "未知" }} ·
          {{
            selected.assessment.uncertainty?.reasons?.join("、") || "无额外原因"
          }}
        </p>
        <h3>模型是否参与</h3>
        <p>
          {{
            selected.assessment.model?.used === true
              ? "是，模型已参与该项判断"
              : "否，模型未参与该项判断"
          }}
        </p>
        <p>
          {{ selected.assessment.model?.name || "未提供模型名称" }} ·
          {{ selected.assessment.model?.provider }} ·
          {{ selected.assessment.model?.version }}
        </p>
        <h3>能力边界</h3>
        <div
          v-for="boundary in selected.entry.boundaries || []"
          :key="boundary.boundary_id"
          class="evidence-block"
        >
          <p>数据：{{ boundary.data_scope?.join("、") || "未知" }}</p>
          <p>网络：{{ boundary.network_target?.join("、") || "未知" }}</p>
          <p>
            凭据使用：{{ boundary.credential_use ? "存在" : "未提取到" }} ·
            执行模式：{{ boundary.execution_mode }}
          </p>
        </div>
        <h3>脱敏源码证据</h3>
        <article v-for="item in evidence" :key="item.id" class="evidence-block">
          <template v-if="item.item"
            ><b>{{ relativeLocation(item.item.source_span) }}</b
            ><small>{{ item.id }}</small>
            <pre>{{ item.item.masked_excerpt || "无可展示片段" }}</pre>
          </template>
          <p v-else>引用 {{ item.id }} 未找到对应证据，需复核。</p>
        </article>
        <p v-if="!evidence.length">没有可解析的证据引用，需复核。</p>
        <button class="button secondary" @click="selected = null">
          返回关系清单
        </button>
      </section>
    </div>
  </section>
</template>
