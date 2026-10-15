<script setup>
import { localize } from "../language";
import { ref, watch, onBeforeUnmount, nextTick } from "vue";
import Icon from "./Icon.vue";
import Badge from "./Badge.vue";
import { api, encode } from "../api";
import { percent, classificationLabels } from "../domain";
const props = defineProps({ scanId: String, kind: String, item: Object });
const emit = defineEmits(["close"]);
const data = ref(null),
  error = ref(""),
  loading = ref(false),
  panel = ref(null);
let request = 0,
  previousFocus;
async function fetchDetail() {
  const token = ++request;
  data.value = null;
  error.value = "";
  loading.value = true;
  try {
    const item = props.item;
    if (!item) return;
    const path =
      props.kind === "secret"
        ? `/scans/${encode(props.scanId)}/secrets/${encode(item.finding_id || item.id)}`
        : props.kind === "license"
          ? `/scans/${encode(props.scanId)}/licenses/${encode(item.assessment_id)}`
          : null;
    const value = path ? await api(path) : item;
    if (token === request) data.value = value;
  } catch (e) {
    if (token === request) error.value = e.message;
  } finally {
    if (token === request) loading.value = false;
  }
}
function keydown(e) {
  if (e.key === "Escape") emit("close");
  if (e.key === "Tab" && panel.value) {
    const els = [
      ...panel.value.querySelectorAll(
        'button,a[href],input,select,[tabindex="0"]',
      ),
    ].filter((n) => !n.disabled);
    const first = els[0],
      last = els.at(-1);
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last?.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first?.focus();
    }
  }
}
watch(
  () => [props.item, props.scanId, props.kind],
  async () => {
    if (props.item) {
      previousFocus = document.activeElement;
      document.body.style.overflow = "hidden";
      document.addEventListener("keydown", keydown);
      await fetchDetail();
      await nextTick();
      panel.value?.querySelector("button")?.focus();
    } else {
      request++;
      document.body.style.overflow = "";
      document.removeEventListener("keydown", keydown);
      previousFocus?.focus?.();
    }
  },
  { immediate: true },
);
onBeforeUnmount(() => {
  request++;
  document.body.style.overflow = "";
  document.removeEventListener("keydown", keydown);
});
</script>
<template>
  <Teleport to="body"
    ><div v-if="item" class="drawer-overlay" @click.self="$emit('close')">
      <section
        ref="panel"
        class="detail-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="detail-title"
      >
        <header>
          <div>
            <p class="eyebrow">EVIDENCE & INSIGHTS</p>
            <h2 id="detail-title">
              {{
                kind === "license"
                  ? "许可证详情"
                  : kind === "secret"
                    ? "Secret 风险详情"
                    : "风险证据详情"
              }}
            </h2>
          </div>
          <button
            class="icon-button"
            @click="$emit('close')"
            aria-label="关闭详情"
          >
            <Icon name="X" />
          </button>
        </header>
        <div v-if="loading" class="empty-state">
          <Icon name="LoaderCircle" class="spin" />
          <p>读取保存的证据</p>
        </div>
        <div v-else-if="error" class="empty-state">
          <Icon name="AlertTriangle" />
          <p>{{ error }}</p>
          <button class="button secondary" @click="fetchDetail">重试</button>
        </div>
        <div v-else-if="data" class="drawer-body">
          <template v-if="kind === 'license'"
            ><div class="detail-hero">
              <Badge :value="data.assessment.severity" />
              <h2>{{ data.package?.name || "许可证观察记录" }}</h2>
              <p>
                {{ data.package?.version || "版本未记录" }} ·
                {{
                  classificationLabels[data.assessment.classification] ||
                  data.assessment.classification
                }}
              </p>
            </div>
            <dl class="detail-fields">
              <dt>规范许可证</dt>
              <dd>{{ data.normalization?.canonical_expression || "未知" }}</dd>
              <dt>原始表达式</dt>
              <dd>{{ data.normalization?.original_expression || "未记录" }}</dd>
              <dt>人工复核</dt>
              <dd>
                {{
                  data.assessment.manual_review_required
                    ? "需要复核"
                    : "当前策略未要求复核"
                }}
              </dd>
              <dt>文件位置</dt>
              <dd>
                {{ data.location?.file_path || "未记录"
                }}<span v-if="data.location">:{{ data.location.line }}</span>
              </dd>
              <dt>数据来源</dt>
              <dd>{{ data.license?.source || "未记录" }}</dd>
            </dl>
            <h3>判断依据</h3>
            <p class="evidence-text">{{ localize(data.assessment.reason) }}</p>
            <h3>数据提供者</h3>
            <div
              class="provider-item"
              v-for="p in data.provider_refs"
              :key="p.name"
            >
              <span>{{ p.name }} {{ p.version }}</span
              ><Badge :value="p.status" kind="status" />
            </div>
            <div class="alert info">
              <Icon name="Info" />
              <p>
                许可分类用于辅助人工复核，不代表法律合规结论。请结合使用与分发方式核查许可义务。
              </p>
            </div></template
          >
          <template v-else
            ><div class="detail-hero">
              <Badge :value="data.severity" />
              <h2>{{ localize(data.message || data.title) }}</h2>
              <p>
                规则 {{ data.rule_id }} · 置信度 {{ percent(data.confidence) }}
              </p>
            </div>
            <div v-if="data.masked_value" class="masked-value">
              <Icon name="LockKeyhole" :size="19" /><code>{{
                data.masked_value
              }}</code
              ><span>已脱敏</span>
            </div>
            <h3>
              定位与证据
              <span class="count-label">{{ data.evidence?.length || 0 }}</span>
            </h3>
            <article
              class="evidence-card"
              v-for="(ev, i) in data.evidence"
              :key="i"
            >
              <div>
                <Icon name="FileText" :size="15" /><code
                  >{{ ev.location?.file_path || ev.source_span?.path }}:{{
                    ev.location?.line || ev.source_span?.start_line
                  }}</code
                >
              </div>
              <p>{{ ev.masked_excerpt || ev.masked_value || "证据未记录" }}</p>
              <small v-if="ev.details?.evidence_kind">{{
                ev.details.evidence_kind === "registration"
                  ? "工具注册位置"
                  : "工具实现位置"
              }}</small>
            </article>
            <template v-if="data.rationale?.length"
              ><h3>为什么需要关注</h3>
              <ul class="readable-list">
                <li v-for="reason in data.rationale" :key="reason">
                  {{ localize(reason) }}
                </li>
              </ul></template
            >
            <h3>建议你这样处理</h3>
            <ol class="recommendation-list">
              <li
                v-for="step in data.remediation?.steps ||
                data.remediation ||
                []"
                :key="step"
              >
                {{ localize(step) }}
              </li>
            </ol>
            <div class="alert info">
              <Icon name="Info" />
              <p>
                以上为人工处置建议。系统不会自动修改代码，也不会验证或使用真实凭据。
              </p>
            </div></template
          >
        </div>
      </section>
    </div></Teleport
  >
</template>
