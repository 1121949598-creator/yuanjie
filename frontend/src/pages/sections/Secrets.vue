<script setup>
import { secretTypes } from "../../language";
import { ref, watch, computed } from "vue";
import { api, encode } from "../../api";
import Icon from "../../components/Icon.vue";
import Badge from "../../components/Badge.vue";
import { percent } from "../../domain";
const props = defineProps({ scan: Object });
defineEmits(["detail"]);
const data = ref(null),
  loading = ref(false),
  error = ref(""),
  severity = ref(""),
  type = ref(""),
  path = ref(""),
  query = ref(""),
  page = ref(1),
  tab = ref("overview");
let request = 0;
async function load() {
  const token = ++request;
  loading.value = true;
  error.value = "";
  const params = new URLSearchParams({
    page: String(page.value),
    page_size: "20",
  });
  if (severity.value) params.set("severity", severity.value);
  if (type.value) params.set("secret_type", type.value);
  if (query.value.trim()) params.set("file_path", query.value.trim());
  try {
    const value = await api(
      `/scans/${encode(props.scan.id)}/secrets?${params}`,
    );
    if (token === request) data.value = value;
  } catch (e) {
    if (token === request) error.value = e.message;
  } finally {
    if (token === request) loading.value = false;
  }
}
watch(
  () => [props.scan.id, page.value, severity.value, type.value, query.value],
  load,
  { immediate: true },
);
const shown = computed(() =>
  tab.value === "overview" ? data.value?.items.slice(0, 5) : data.value?.items,
);
function apply() {
  page.value = 1;
  query.value = path.value;
  if (query.value === path.value) load();
}
</script>
<template>
  <div class="page-heading">
    <div>
      <p class="eyebrow">SECRET SECURITY</p>
      <h1>让敏感凭据，止步于公开之前。</h1>
      <p>定位代码与配置中的疑似凭据，保留脱敏证据和清晰的处置建议。</p>
    </div>
    <span class="heading-illustration"
      ><Icon name="KeyRound" :size="32"
    /></span>
  </div>
  <div class="view-tabs">
    <button
      :class="{ active: tab === 'overview' }"
      @click="
        tab = 'overview';
        severity = '';
        type = '';
        query = '';
        path = '';
        page = 1;
      "
    >
      风险概览</button
    ><button :class="{ active: tab === 'details' }" @click="tab = 'details'">
      全部明细
    </button>
  </div>
  <div v-if="data" class="metric-grid">
    <div
      class="metric-card"
      v-for="[key, label, color] in [
        ['total', 'Secret 发现总数', 'blue'],
        ['high', '高风险', 'red'],
        ['medium', '中风险', 'orange'],
        ['critical', '严重风险', 'magenta'],
      ]"
      :key="key"
    >
      <span>{{ label }}</span
      ><b :class="`text-${color}`">{{ data.summary[key] }}</b
      ><small>{{
        key === "total" ? "按去重后的风险项统计" : "独立严重度，不与置信度混用"
      }}</small>
    </div>
  </div>
  <div v-if="data?.status !== 'success' && data" class="alert warning">
    <Icon name="Info" />
    <p>
      Secret 检测{{
        {
          partial: "部分完成",
          unavailable: "不可用",
          disabled: "未启用",
          failed: "失败",
        }[data.status] || "覆盖未知"
      }}。以下仅展示已保存的有效发现。
    </p>
  </div>
  <section class="panel">
    <div class="panel-heading">
      <h2>
        {{ tab === "overview" ? "优先关注的凭据风险" : "Secret 风险明细" }}
      </h2>
      <span class="micro-tag"
        ><Icon name="LockKeyhole" :size="12" />始终脱敏</span
      >
    </div>
    <form
      v-if="tab === 'details'"
      class="panel-toolbar filters"
      @submit.prevent="apply"
    >
      <div class="search-field">
        <Icon name="Search" :size="16" /><input
          v-model="path"
          placeholder="按文件路径搜索"
          aria-label="Secret 文件路径"
        />
      </div>
      <select
        v-model="severity"
        @change="page = 1"
        aria-label="Secret 风险等级"
      >
        <option value="">全部等级</option>
        <option value="critical">严重</option>
        <option value="high">高风险</option>
        <option value="medium">中风险</option>
        <option value="low">低风险</option>
        <option value="info">信息</option></select
      ><select v-model="type" @change="page = 1" aria-label="Secret 类型">
        <option value="">全部类型</option>
        <option v-for="(_, key) in data?.by_type" :key="key" :value="key">
          {{ secretTypes[key] || key }}
        </option></select
      ><button class="button secondary" type="submit">查询</button>
    </form>
    <div v-if="error" class="empty-state" role="alert">
      <p>{{ error }}</p>
      <button class="button secondary" @click="load">重试</button>
    </div>
    <div v-else-if="loading" class="empty-state">
      <Icon name="LoaderCircle" class="spin" />
      <p>正在读取风险记录</p>
    </div>
    <div v-else-if="!shown?.length" class="empty-state">
      <Icon name="ShieldCheck" :size="35" />
      <h3>没有匹配的 Secret 发现</h3>
      <p>请结合检测覆盖说明理解结果，或尝试调整筛选。</p>
    </div>
    <div v-else class="table-scroll">
      <table>
        <thead>
          <tr>
            <th>类型与文件位置</th>
            <th>脱敏凭据</th>
            <th>风险等级</th>
            <th>置信度</th>
            <th>出现位置</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in shown" :key="item.finding_id">
            <td>
              <button class="finding-title" @click="$emit('detail', item)">
                {{ secretTypes[item.secret_type] || item.secret_type }}</button
              ><small class="file-location"
                >{{ item.location?.file_path || "未记录" }}:{{
                  item.location?.line || "—"
                }}</small
              >
            </td>
            <td>
              <code class="secret-code">{{ item.masked_value }}</code>
            </td>
            <td><Badge :value="item.severity" /></td>
            <td>{{ percent(item.confidence) }}</td>
            <td>{{ item.occurrence_count }} 处</td>
            <td>
              <button class="text-button" @click="$emit('detail', item)">
                查看证据 <Icon name="ChevronRight" :size="15" />
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-if="data" class="table-footer">
      <span
        >共 {{ data.pagination.total }} 项{{
          tab === "overview" ? " · 展示前 5 项" : ""
        }}</span
      ><button
        v-if="tab === 'overview'"
        class="text-button"
        @click="tab = 'details'"
      >
        查看全部明细 <Icon name="ArrowRight" :size="15" />
      </button>
      <div v-else class="pagination">
        <button
          :disabled="page === 1 || loading"
          @click="page--"
          aria-label="上一页"
        >
          <Icon name="ChevronRight" class="rotate" :size="15" /></button
        ><span
          >{{ page }} /
          {{ Math.max(1, Math.ceil(data.pagination.total / 20)) }}</span
        ><button
          :disabled="page * 20 >= data.pagination.total || loading"
          @click="page++"
          aria-label="下一页"
        >
          <Icon name="ChevronRight" :size="15" />
        </button>
      </div>
    </div>
  </section>
  <div v-if="tab === 'overview' && data" class="two-columns section-gap">
    <section class="panel padded">
      <h2>凭据类型分布</h2>
      <div
        v-for="(count, key) in data.by_type"
        :key="key"
        class="distribution-row"
      >
        <span>{{ secretTypes[key] || key }}</span>
        <div class="distribution-bar">
          <i
            :style="{
              width: (count / Math.max(1, data.summary.total)) * 100 + '%',
            }"
          ></i>
        </div>
        <b>{{ count }}</b>
      </div>
      <p v-if="!Object.keys(data.by_type).length" class="muted">
        当前没有可统计的类型。
      </p>
    </section>
    <section class="panel padded soft-panel">
      <span class="small-feature-icon"><Icon name="Eye" /></span>
      <h2>看得见风险，看不见完整凭据</h2>
      <p>
        同一个 Secret
        在不同位置出现，会合并展示。进入详情可查看每一处保存的定位和轮换、移除等人工处置建议。
      </p>
    </section>
  </div>
</template>
