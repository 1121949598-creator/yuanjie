import {
  LicenseApiError, getLicenseDetail, getLicenseOverview, overviewParams,
} from "./license-api.js";

export const CLASSIFICATION_LABELS = Object.freeze({
  permissive: "宽松许可证",
  weak_copyleft: "弱 Copyleft",
  strong_copyleft: "强 Copyleft",
  network_copyleft: "网络 Copyleft",
  unknown: "未识别 / 需审核",
  invalid: "无效 SPDX 表达式",
});

export const SEVERITY_LABELS = Object.freeze({
  critical: "严重", high: "高", medium: "中", low: "低", info: "提示",
});

const STATUS_LABELS = Object.freeze({
  success: "执行完成", partial: "部分完成", failed: "执行失败",
  unavailable: "结果不可用", disabled: "未启用", pending: "等待扫描完成",
});

const REASON_LABELS = Object.freeze({
  catalog_permissive: "许可证已识别为宽松类型，请继续确认声明和归属要求。",
  weak_copyleft_review: "自动分类为弱 Copyleft，需要结合修改、链接和分发方式审核。",
  strong_copyleft_review: "自动分类为强 Copyleft，建议在分发前审核许可证义务。",
  network_copyleft_review: "自动分类为网络 Copyleft，需要结合网络服务部署方式审核。",
  unknown_license_review: "当前许可证不在自动分类目录中，需要人工确认。",
  invalid_expression_or_identifier: "原始声明无法按当前 SPDX 规则解析，需要人工检查。",
  alternative_terms_require_review: "组件声明了可选许可证条款，需要确认实际采用的授权路径。",
  exception_terms_require_review: "表达式包含许可证例外条款，需要人工确认其适用范围。",
  no_located_license_fact: "未找到带有精确位置的许可证记录，需要人工确认依赖声明。",
  profile_classification_override: "此评估应用了管理员配置的许可证分类规则。",
});

const GUIDANCE = Object.freeze({
  permissive: "请确认许可证声明及相关 notice / attribution 要求。",
  weak_copyleft: "建议人工确认修改、链接及分发场景下的许可证义务。",
  strong_copyleft: "建议在分发前进行许可证义务审核。",
  network_copyleft: "建议结合网络服务部署方式进行许可证义务审核。",
  unknown: "当前自动化规则无法确定许可证类别，需要人工确认。",
  invalid: "许可证表达式无法按当前 SPDX 规则解析，需要人工检查原始声明。",
});

export function classificationLabel(value) {
  return CLASSIFICATION_LABELS[value] || "未识别 / 需审核";
}

export function severityLabel(value) {
  return value == null ? "未分级" : (SEVERITY_LABELS[value] || "未分级");
}

export function statusLabel(value) {
  return STATUS_LABELS[value] || "状态未知";
}

export function reasonLabel(value) {
  return REASON_LABELS[value] || "自动化策略要求结合实际使用与分发场景进行人工确认。";
}

export function displayExpression(item) {
  return item?.canonical_expression || item?.original_expression || "Unknown";
}

export function displayLocation(location) {
  if (!location) return "无精确位置";
  return `${location.file_path}:${location.line}`;
}

export function hasActiveFilters(input) {
  const params = overviewParams(input);
  for (const key of ["classification", "severity", "manual_review_required", "package_name", "license_expression", "file_path"]) {
    if (params.has(key)) return true;
  }
  return false;
}

export function overviewNotice(payload) {
  if (!payload.inventory_available || payload.status === "unavailable") {
    return { tone: "warning", text: "该扫描未记录许可证库存，无法展示许可证评估。" };
  }
  if (payload.status === "partial") {
    const gap = !payload.coverage.providers_complete || !payload.coverage.assessment_complete || payload.coverage.dropped_records > 0;
    return { tone: "warning", text: gap ? "部分许可证结果可能不完整，扫描结果可能存在覆盖缺口。已有评估仍保留展示。" : "部分许可证结果可能不完整。已有评估仍保留展示。" };
  }
  if (payload.status === "failed") {
    return { tone: "error", text: "许可证处理执行失败；已有库存仅供核对，不能据此认定项目无风险。" };
  }
  return null;
}

export function emptyMessage(payload, query) {
  if (!payload.inventory_available) return "该扫描未记录许可证库存，无法展示许可证评估。";
  if (payload.summary.assessments === 0) return "本次扫描未记录许可证评估项。";
  if (hasActiveFilters(query)) return "当前筛选条件下没有许可证记录。";
  return "本页没有许可证记录。";
}

export function errorMessage(error) {
  if (!(error instanceof LicenseApiError)) return "许可证结果暂时无法加载，请稍后重试。";
  if (error.status === 404) {
    return error.message === "License assessment not found in this scan" ? "此扫描中不存在该许可证评估。" : "未找到该扫描。";
  }
  if (error.status === 409) {
    return error.message === "License inventory schema is not supported" ? "许可证库存版本暂不受支持。" : "扫描结果尚未完成，请稍后再试。";
  }
  if (error.status === 422) return "筛选条件无效，请检查后重试。";
  if (error.status === 0) return "网络连接失败，无法读取许可证结果。";
  return "许可证结果无法加载，请稍后重试。";
}

export function overviewDetailHref(scanId, assessmentId, query = new URLSearchParams()) {
  const suffix = overviewParams(query).toString();
  const base = `/scans/${encodeURIComponent(scanId)}/licenses/${encodeURIComponent(assessmentId)}`;
  return suffix ? `${base}?${suffix}` : base;
}

export function overviewBackHref(scanId, query = new URLSearchParams()) {
  const suffix = overviewParams(query).toString();
  const base = `/scans/${encodeURIComponent(scanId)}/licenses`;
  return suffix ? `${base}?${suffix}` : base;
}

export function pageCount(pagination) {
  return Math.max(1, Math.ceil(pagination.total / pagination.page_size));
}

export function reviewGuidance(classification) {
  return GUIDANCE[classification] || GUIDANCE.unknown;
}

export function overviewRowModel(item) {
  return {
    assessmentId: item.assessment_id,
    packageName: item.package_name || "未知依赖包",
    packageVersion: item.package_version || "—",
    expression: displayExpression(item),
    classification: classificationLabel(item.classification),
    severity: severityLabel(item.severity),
    review: item.manual_review_required ? "待人工审核" : "已记录",
    location: displayLocation(item.location),
  };
}

export function detailViewModel(payload) {
  const assessment = payload.assessment;
  const normalization = payload.normalization;
  return {
    assessmentId: assessment.assessment_id,
    packageName: payload.package?.name || "未知依赖包",
    packageVersion: payload.package?.version || "—",
    expression: normalization?.canonical_expression || normalization?.original_expression || "Unknown",
    originalExpression: normalization?.original_expression || "—",
    canonicalExpression: normalization?.canonical_expression || "—",
    normalizationStatus: normalization?.status || "—",
    classification: classificationLabel(assessment.classification),
    severity: severityLabel(assessment.severity),
    review: assessment.manual_review_required ? "待人工审核" : "已记录",
    location: displayLocation(payload.location),
    exceptionIds: normalization?.exception_ids || [],
    alternativeTerms: assessment.alternative_terms,
    findingCount: payload.finding_refs.length,
    providerCount: payload.provider_refs.length,
  };
}

function element(tag, options = {}, children = []) {
  const node = document.createElement(tag);
  if (options.className) node.className = options.className;
  if (options.text != null) node.textContent = String(options.text);
  for (const [name, value] of Object.entries(options.attrs || {})) node.setAttribute(name, String(value));
  for (const child of children) node.append(child);
  return node;
}

function badge(text, className) {
  return element("span", { className: `pill ${className || ""}`.trim(), text });
}

function setStatus(node, status) {
  node.className = `pill status-${status}`;
  node.textContent = statusLabel(status);
}

function setNotice(node, notice) {
  node.hidden = !notice;
  if (!notice) return;
  node.className = `notice ${notice.tone || ""}`.trim();
  node.textContent = notice.text;
}

function setDefinitionList(node, entries) {
  node.replaceChildren();
  for (const [term, value] of entries) {
    node.append(element("dt", { text: term }), element("dd", { text: value ?? "—" }));
  }
}

function syncForm(form, query) {
  const params = overviewParams(query);
  for (const control of form.elements) {
    if (!control.name) continue;
    control.value = params.get(control.name) || (control.name === "page_size" ? "20" : "");
  }
}

function formQuery(form) {
  const params = overviewParams(new FormData(form));
  params.set("page", "1");
  if (!params.has("page_size")) params.set("page_size", "20");
  return params;
}

function navigateQuery(query, replace = false) {
  const suffix = overviewParams(query).toString();
  const target = suffix ? `${location.pathname}?${suffix}` : location.pathname;
  history[replace ? "replaceState" : "pushState"]({}, "", target);
}

function renderOverviewRows(root, payload, query) {
  const rows = root.querySelector("#license-rows");
  rows.replaceChildren();
  for (const item of payload.items) {
    const model = overviewRowModel(item);
    const link = element("a", {
      className: "table-link", text: "查看详情",
      attrs: { href: overviewDetailHref(payload.scan_id, model.assessmentId, query), "aria-label": `查看 ${model.packageName} 的许可证详情` },
    });
    const row = element("tr", {}, [
      element("td", {}, [element("strong", { text: model.packageName })]),
      element("td", { text: model.packageVersion }),
      element("td", {}, [element("code", { text: model.expression })]),
      element("td", {}, [badge(model.classification, `classification-${item.classification}`)]),
      element("td", {}, [badge(model.severity, item.severity ? `severity-${item.severity}` : "severity-none")]),
      element("td", {}, [badge(model.review, item.manual_review_required ? "review-required" : "review-recorded")]),
      element("td", { text: model.location }), element("td", {}, [link]),
    ]);
    rows.append(row);
  }
}

function renderOverview(root, payload, query) {
  root.querySelector("#license-loading").hidden = true;
  root.querySelector("#license-error").hidden = true;
  root.querySelector("#license-content").hidden = false;
  setStatus(root.querySelector("#module-status"), payload.status);
  setNotice(root.querySelector("#license-notice"), overviewNotice(payload));
  root.querySelector("#summary-packages").textContent = payload.summary.packages;
  root.querySelector("#summary-dependencies").textContent = payload.summary.dependencies;
  root.querySelector("#summary-licenses").textContent = payload.summary.licenses;
  root.querySelector("#summary-review").textContent = payload.summary.manual_review_required;
  const classifications = root.querySelector("#classification-summary");
  classifications.replaceChildren();
  for (const key of Object.keys(CLASSIFICATION_LABELS)) {
    const count = payload.summary.by_classification[key] || 0;
    classifications.append(element("div", { className: "classification-card" }, [badge(classificationLabel(key), `classification-${key}`), element("b", { text: count })]));
  }
  root.querySelector("#result-count").textContent = `共 ${payload.pagination.total} 项评估`;
  renderOverviewRows(root, payload, query);
  const empty = root.querySelector("#license-empty");
  empty.hidden = payload.items.length > 0;
  empty.textContent = emptyMessage(payload, query);
  const pagination = root.querySelector("#license-pagination");
  const pages = pageCount(payload.pagination);
  pagination.hidden = payload.pagination.total === 0;
  root.querySelector("#page-label").textContent = `第 ${payload.pagination.page} / ${pages} 页`;
  root.querySelector("#previous-page").disabled = payload.pagination.page <= 1;
  root.querySelector("#next-page").disabled = payload.pagination.page >= pages;
}

export async function initOverview(root) {
  const scanId = root.dataset.scanId;
  const form = root.querySelector("#license-filters");
  const load = async () => {
    const query = overviewParams(location.search);
    syncForm(form, query);
    root.querySelector("#license-loading").hidden = false;
    root.querySelector("#license-error").hidden = true;
    try {
      renderOverview(root, await getLicenseOverview(scanId, query), query);
    } catch (error) {
      root.querySelector("#license-loading").hidden = true;
      root.querySelector("#license-content").hidden = true;
      const target = root.querySelector("#license-error");
      target.textContent = errorMessage(error);
      target.hidden = false;
      const errorStatus = error.status === 404 || error.message === "License inventory schema is not supported"
        ? "unavailable" : error.status === 409 ? "pending" : "failed";
      setStatus(root.querySelector("#module-status"), errorStatus);
    }
  };
  form.addEventListener("submit", (event) => { event.preventDefault(); navigateQuery(formQuery(form)); load(); });
  root.querySelector("#clear-filters").addEventListener("click", () => { navigateQuery(new URLSearchParams("page=1&page_size=20")); load(); });
  const changePage = (offset) => {
    const query = overviewParams(location.search);
    const current = Number(query.get("page") || "1");
    query.set("page", String(Math.max(1, current + offset)));
    if (!query.has("page_size")) query.set("page_size", "20");
    navigateQuery(query); load();
  };
  root.querySelector("#previous-page").addEventListener("click", () => changePage(-1));
  root.querySelector("#next-page").addEventListener("click", () => changePage(1));
  addEventListener("popstate", load);
  await load();
}

function renderDetail(root, payload) {
  root.querySelector("#license-loading").hidden = true;
  root.querySelector("#license-error").hidden = true;
  root.querySelector("#license-detail-content").hidden = false;
  const assessment = payload.assessment;
  const normalization = payload.normalization;
  const model = detailViewModel(payload);
  root.querySelector("#detail-package-name").textContent = model.packageName;
  root.querySelector("#detail-license-expression").textContent = model.expression;
  const badges = root.querySelector("#detail-badges");
  badges.replaceChildren(
    badge(classificationLabel(assessment.classification), `classification-${assessment.classification}`),
    badge(severityLabel(assessment.severity), assessment.severity ? `severity-${assessment.severity}` : "severity-none"),
    badge(assessment.manual_review_required ? "待人工审核" : "已记录", assessment.manual_review_required ? "review-required" : "review-recorded"),
    badge(statusLabel(payload.status), `status-${payload.status}`),
  );
  setNotice(root.querySelector("#license-notice"), overviewNotice({ ...payload, inventory_available: true, coverage: { providers_complete: payload.status === "success", assessment_complete: payload.status === "success", dropped_records: 0 } }));
  setDefinitionList(root.querySelector("#assessment-list"), [
    ["分类", classificationLabel(assessment.classification)], ["风险等级", severityLabel(assessment.severity)],
    ["审核状态", assessment.manual_review_required ? "待人工审核" : "已记录"],
    ["判断依据", reasonLabel(assessment.reason)], ["技术原因", assessment.reason],
    ["Assessment ID", assessment.assessment_id], ["策略状态", assessment.policy_status],
  ]);
  setDefinitionList(root.querySelector("#package-list"), [
    ["名称", payload.package?.name], ["版本", payload.package?.version], ["PURL", payload.package?.purl],
    ["标识符", payload.package?.identifier], ["位置", displayLocation(payload.location)],
  ]);
  setDefinitionList(root.querySelector("#normalization-list"), [
    ["原始表达式", normalization?.original_expression], ["规范 SPDX 表达式", normalization?.canonical_expression],
    ["规范化状态", normalization?.status], ["许可证 ID", normalization?.license_ids?.join(", ") || "—"],
    ["例外条款", normalization?.exception_ids?.join(", ") || "—"],
  ]);
  const special = root.querySelector("#special-guidance");
  const messages = [];
  if (assessment.alternative_terms) messages.push("该组件声明了可选许可证条款，需要确认实际采用的授权路径。完整表达式已保留，系统不会代替你选择许可证。 ");
  if (assessment.exception_review || normalization?.exception_ids?.length) messages.push("许可证例外条款需要人工确认其适用范围；当前策略不会据此自动降低审核优先级。 ");
  special.textContent = messages.join("").trim();
  special.hidden = messages.length === 0;
  const findings = root.querySelector("#finding-list");
  findings.replaceChildren();
  if (!payload.finding_refs.length) findings.append(element("p", { className: "muted", text: "没有关联风险 Finding；许可证评估本身仍然有效。" }));
  for (const finding of payload.finding_refs) findings.append(element("div", { className: "detail-list-item" }, [badge(severityLabel(finding.severity), `severity-${finding.severity}`), element("div", {}, [element("strong", { text: finding.title }), element("small", { text: `规则 ${finding.rule_id}` })])]));
  const providers = root.querySelector("#provider-list");
  providers.replaceChildren();
  if (!payload.provider_refs.length) providers.append(element("p", { className: "muted", text: "未记录可展示的检测来源。" }));
  for (const provider of payload.provider_refs) providers.append(element("div", { className: "detail-list-item" }, [badge(statusLabel(provider.status), `status-${provider.status}`), element("div", {}, [element("strong", { text: provider.name }), element("small", { text: `${provider.version || "版本未知"} · ${provider.execution_mode}` })])]));
  root.querySelector("#review-guidance").textContent = reviewGuidance(assessment.classification);
}

export async function initDetail(root) {
  const { scanId, assessmentId } = root.dataset;
  root.querySelector("#license-back").href = overviewBackHref(scanId, location.search);
  try {
    renderDetail(root, await getLicenseDetail(scanId, assessmentId));
  } catch (error) {
    root.querySelector("#license-loading").hidden = true;
    const target = root.querySelector("#license-error");
    target.textContent = errorMessage(error);
    target.hidden = false;
  }
}

if (typeof document !== "undefined") {
  const overviewRoot = document.querySelector("[data-license-overview]");
  const detailRoot = document.querySelector("[data-license-detail]");
  if (overviewRoot) initOverview(overviewRoot);
  if (detailRoot) initDetail(detailRoot);
}
