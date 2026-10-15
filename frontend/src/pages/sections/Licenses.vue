<script setup>
import { ref, watch } from "vue";
import { api, encode } from "../../api";
import Icon from "../../components/Icon.vue";
import Badge from "../../components/Badge.vue";
import { classificationLabels } from "../../domain";
const props = defineProps({ scan: Object });
defineEmits(["detail"]);
const data = ref(null),
  loading = ref(false),
  error = ref(""),
  tab = ref("overview"),
  page = ref(1),
  classification = ref(""),
  review = ref(""),
  input = ref(""),
  query = ref("");
let request = 0;
async function load() {
  const token = ++request;
  loading.value = true;
  error.value = "";
  const params = new URLSearchParams({
    page: String(page.value),
    page_size: "20",
  });
  if (classification.value) params.set("classification", classification.value);
  if (review.value) params.set("manual_review_required", review.value);
  if (query.value.trim()) params.set("package_name", query.value.trim());
  try {
    const value = await api(
      `/scans/${encode(props.scan.id)}/licenses?${params}`,
    );
    if (token === request) data.value = value;
  } catch (e) {
    if (token === request) error.value = e.message;
  } finally {
    if (token === request) loading.value = false;
  }
}
watch(
  () => [
    props.scan.id,
    page.value,
    classification.value,
    review.value,
    query.value,
  ],
  load,
  { immediate: true },
);
function apply() {
  page.value = 1;
  query.value = input.value;
  load();
}
</script>
<template>
  <div class="page-heading">
    <div>
      <p class="eyebrow">LICENSE & DEPENDENCIES</p>
      <h1>了解依赖，也了解使用它的边界。</h1>
      <p>识别许可声明、检查来源与完整性，把需要人工核查的事项提前看见。</p>
    </div>
    <span class="heading-illustration"
      ><Icon name="FileCheck2" :size="32"
    /></span>
  </div>
  <div class="view-tabs">
    <button
      :class="{ active: tab === 'overview' }"
      @click="
        tab = 'overview';
        classification = '';
        review = '';
        query = '';
        input = '';
        page = 1;
      "
    >
      许可证概览</button
    ><button :class="{ active: tab === 'details' }" @click="tab = 'details'">
      全部明细
    </button>
  </div>
  <div v-if="data" class="metric-grid">
    <div
      class="metric-card"
      v-for="[key, label] in [
        ['packages', '包身份'],
        ['dependencies', '依赖关系'],
        ['assessments', '许可评估项'],
        ['manual_review_required', '待人工复核'],
      ]"
      :key="key"
    >
      <span>{{ label }}</span
      ><b
        :class="key === 'manual_review_required' ? 'text-orange' : 'text-blue'"
        >{{ data.inventory_available ? data.summary[key] : "—" }}</b
      ><small>{{
        key === "packages"
          ? "可能包含根包与不同版本身份"
          : key === "assessments"
            ? "一项评估对应一条明细"
            : "来自已保存的许可证库存"
      }}</small>
    </div>
  </div>
  <div
    v-if="
      data && (data.status !== 'success' || !data.coverage.inventory_complete)
    "
    class="alert warning"
  >
    <Icon name="AlertTriangle" />
    <div>
      <b>{{
        data.status === "unavailable"
          ? "许可证检测当前不可用"
          : "许可证结果存在覆盖缺口"
      }}</b>
      <p>
        {{
          data.status === "unavailable"
            ? "主机尚未获得可用的许可证 Provider 结果。请配置可信 ScanCode 工具后重新扫描；零条发现不等于合规通过。"
            : "部分提供者、库存或评估未完整完成。请结合以下记录与数据来源人工复核。"
        }}
      </p>
    </div>
  </div>
  <div v-if="tab === 'overview' && data" class="two-columns section-gap">
    <section class="panel padded">
      <h2>许可证分类</h2>
      <div
        v-for="(n, key) in data.summary.by_classification"
        :key="key"
        class="distribution-row"
      >
        <span>{{ classificationLabels[key] || key }}</span>
        <div class="distribution-bar">
          <i
            :class="{ orange: key !== 'permissive' }"
            :style="{
              width: (n / Math.max(1, data.summary.assessments)) * 100 + '%',
            }"
          ></i>
        </div>
        <b>{{ n }}</b>
      </div>
      <p v-if="!data.summary.assessments" class="muted">
        尚无可展示的许可评估。
      </p>
    </section>
    <section class="panel padded">
      <h2>检测来源与覆盖</h2>
      <div
        v-for="provider in data.providers"
        :key="provider.name"
        class="provider-item"
      >
        <div>
          <b>{{ provider.name }}</b
          ><small
            >{{ provider.version || "版本未记录" }} ·
            {{ provider.execution_mode }}</small
          >
        </div>
        <Badge :value="provider.status" kind="status" />
      </div>
      <div class="coverage-facts">
        <span
          >提供者完整
          <b>{{ data.coverage.providers_complete ? "是" : "否" }}</b></span
        ><span
          >评估完整
          <b>{{ data.coverage.assessment_complete ? "是" : "否" }}</b></span
        ><span
          >丢弃记录 <b>{{ data.coverage.dropped_records }}</b></span
        >
      </div>
    </section>
  </div>
  <section class="panel section-gap">
    <div class="panel-heading">
      <h2>
        {{ tab === "overview" ? "优先关注的许可评估" : "许可证评估明细" }}
      </h2>
      <span class="micro-tag">信息识别与人工复核</span>
    </div>
    <form
      v-if="tab === 'details'"
      class="panel-toolbar filters"
      @submit.prevent="apply"
    >
      <div class="search-field">
        <Icon name="Search" :size="16" /><input
          v-model="input"
          placeholder="搜索包名称"
          aria-label="许可证包名称"
        />
      </div>
      <select
        v-model="classification"
        @change="page = 1"
        aria-label="许可证分类"
      >
        <option value="">全部分类</option>
        <option
          v-for="(label, key) in classificationLabels"
          :value="key"
          :key="key"
        >
          {{ label }}
        </option></select
      ><select v-model="review" @change="page = 1" aria-label="人工复核筛选">
        <option value="">全部评估</option>
        <option value="true">需人工复核</option>
        <option value="false">无需人工复核</option></select
      ><button class="button secondary" type="submit">查询</button>
    </form>
    <div v-if="error" class="empty-state">
      <p>{{ error }}</p>
      <button class="button secondary" @click="load">重试</button>
    </div>
    <div v-else-if="loading" class="empty-state">
      <Icon name="LoaderCircle" class="spin" />
      <p>读取许可证库存</p>
    </div>
    <div v-else-if="!data?.items.length" class="empty-state">
      <Icon name="FileCheck2" :size="36" />
      <h3>暂无匹配的许可评估</h3>
      <p>请结合上方提供者状态和覆盖信息理解结果。</p>
    </div>
    <div v-else class="table-scroll">
      <table>
        <thead>
          <tr>
            <th>包 / 观察位置</th>
            <th>许可证表达式</th>
            <th>许可分类</th>
            <th>风险等级</th>
            <th>人工复核</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="item in tab === 'overview'
              ? data.items.slice(0, 5)
              : data.items"
            :key="item.assessment_id"
          >
            <td>
              <button class="finding-title" @click="$emit('detail', item)">
                {{ item.package_name || "许可证观察记录" }}</button
              ><small class="file-location">{{
                item.package_version ||
                item.location?.file_path ||
                "未记录版本/位置"
              }}</small>
            </td>
            <td>
              <code class="license-expression">{{
                item.canonical_expression || item.original_expression || "未知"
              }}</code>
            </td>
            <td>
              {{
                classificationLabels[item.classification] || item.classification
              }}
            </td>
            <td><Badge :value="item.severity" /></td>
            <td>
              <span
                class="review-label"
                :class="{ required: item.manual_review_required }"
                >{{ item.manual_review_required ? "需要复核" : "未要求" }}</span
              >
            </td>
            <td>
              <button
                class="icon-button"
                @click="$emit('detail', item)"
                aria-label="查看许可证详情"
              >
                <Icon name="ChevronRight" :size="17" />
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-if="data" class="table-footer">
      <span>共 {{ data.pagination.total }} 项评估 · 不等同于依赖数量</span
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
</template>
