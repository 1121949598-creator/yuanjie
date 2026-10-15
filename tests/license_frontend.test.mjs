import assert from "node:assert/strict";
import test from "node:test";

import {
  LicenseApiError, detailEndpoint, getLicenseDetail, getLicenseOverview, overviewEndpoint,
  overviewParams,
} from "../src/yuanjian_agent/static/license-api.js";
import {
  classificationLabel, detailViewModel, displayExpression, displayLocation, emptyMessage,
  errorMessage, hasActiveFilters, overviewBackHref, overviewDetailHref, overviewNotice,
  overviewRowModel, pageCount, reasonLabel, reviewGuidance, severityLabel,
} from "../src/yuanjian_agent/static/license-pages.js";

const baseOverview = {
  scan_id: "scan-a", status: "success", inventory_available: true,
  summary: { packages: 3, dependencies: 1, licenses: 3, assessments: 4, manual_review_required: 3, by_classification: {} },
  coverage: { providers_complete: true, assessment_complete: true, dropped_records: 0 },
  pagination: { page: 1, page_size: 20, total: 4 }, items: [],
};

const item = {
  assessment_id: "assess-1", package_name: "Alpha", package_version: "1.0",
  canonical_expression: "MIT", original_expression: "mit", classification: "permissive",
  severity: null, manual_review_required: false,
  location: { file_path: "package.json", line: 17 },
};

const detail = {
  scan_id: "scan-a", status: "success",
  assessment: { assessment_id: "assess-1", classification: "permissive", severity: null, manual_review_required: false, alternative_terms: false },
  package: { name: "Alpha", version: "1.0", purl: "pkg:pypi/alpha@1.0", identifier: "PyPI::alpha:1.0" },
  normalization: { original_expression: "mit", canonical_expression: "MIT", status: "canonical", license_ids: ["MIT"], exception_ids: [] },
  location: { file_path: "package.json", line: 17 }, finding_refs: [], provider_refs: [],
};

test("overview API endpoint keeps only L3 query parameters", () => {
  const query = new URLSearchParams({ page: "2", page_size: "50", classification: "strong_copyleft", severity: "high", manual_review_required: "true", package_name: "alpha", license_expression: "GPL", file_path: "src", unknown: "drop" });
  const url = overviewEndpoint("scan /一", query);
  assert.equal(url, "/api/scans/scan%20%2F%E4%B8%80/licenses?page=2&page_size=50&classification=strong_copyleft&severity=high&manual_review_required=true&package_name=alpha&license_expression=GPL&file_path=src");
  assert.equal(overviewParams(query).has("unknown"), false);
});

test("overview client makes one GET request with combined filters", async () => {
  const calls = [];
  const fetchImpl = async (url, options) => { calls.push([url, options]); return { ok: true, json: async () => baseOverview }; };
  await getLicenseOverview("scan-a", new URLSearchParams("classification=network_copyleft&severity=high&manual_review_required=true&package_name=Beta&license_expression=AGPL&file_path=requirements"), fetchImpl);
  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], "/api/scans/scan-a/licenses?classification=network_copyleft&severity=high&manual_review_required=true&package_name=Beta&license_expression=AGPL&file_path=requirements");
  assert.equal(calls[0][1].method, "GET");
});

test("detail client requests only the assessment endpoint", async () => {
  const calls = [];
  await getLicenseDetail("scan-a", "assessment/1", async (url, options) => { calls.push([url, options]); return { ok: true, json: async () => detail }; });
  assert.deepEqual(calls.map((entry) => entry[0]), ["/api/scans/scan-a/licenses/assessment%2F1"]);
  assert.equal(detailEndpoint("scan-a", "assessment/1"), calls[0][0]);
  assert.equal(calls[0][1].method, "GET");
});

test("API client emits bounded errors and hides response internals", async () => {
  await assert.rejects(() => getLicenseDetail("scan-a", "missing", async () => ({ ok: false, status: 404, json: async () => ({ detail: "License assessment not found in this scan", stack: "secret" }) })), (error) => error instanceof LicenseApiError && error.status === 404 && !error.message.includes("secret"));
  await assert.rejects(() => getLicenseOverview("scan-a", "", async () => { throw new Error("filesystem secret"); }), (error) => error.status === 0 && error.message === "Network request failed");
});

test("overview loading payload uses backend summary without recounting", () => {
  assert.deepEqual(baseOverview.summary, { packages: 3, dependencies: 1, licenses: 3, assessments: 4, manual_review_required: 3, by_classification: {} });
});

test("assessment row preserves permissive null severity", () => {
  assert.deepEqual(overviewRowModel(item), { assessmentId: "assess-1", packageName: "Alpha", packageVersion: "1.0", expression: "MIT", classification: "宽松许可证", severity: "未分级", review: "已记录", location: "package.json:17" });
  assert.equal(severityLabel(null), "未分级");
});

test("high-risk manual-review row remains explicit", () => {
  const model = overviewRowModel({ ...item, classification: "strong_copyleft", severity: "high", manual_review_required: true });
  assert.equal(model.classification, "强 Copyleft");
  assert.equal(model.severity, "高");
  assert.equal(model.review, "待人工审核");
});

test("unknown package, original expression and unlocated fallbacks do not fabricate data", () => {
  const model = overviewRowModel({ ...item, package_name: null, package_version: null, canonical_expression: null, original_expression: "LicenseRef-Proprietary", location: null });
  assert.equal(model.packageName, "未知依赖包");
  assert.equal(model.packageVersion, "—");
  assert.equal(model.expression, "LicenseRef-Proprietary");
  assert.equal(model.location, "无精确位置");
});

test("overview pagination uses backend page metadata", () => {
  assert.equal(pageCount({ page: 2, page_size: 20, total: 41 }), 3);
  assert.equal(pageCount({ page: 1, page_size: 20, total: 0 }), 1);
});

test("filter detection ignores pagination but recognizes every domain filter", () => {
  assert.equal(hasActiveFilters("page=2&page_size=50"), false);
  for (const query of ["classification=unknown", "severity=medium", "manual_review_required=false", "package_name=x", "license_expression=MIT", "file_path=LICENSE"]) assert.equal(hasActiveFilters(query), true);
});

test("empty copy separates inventory-empty from no filter result", () => {
  assert.equal(emptyMessage({ ...baseOverview, summary: { ...baseOverview.summary, assessments: 0 } }, ""), "本次扫描未记录许可证评估项。");
  assert.equal(emptyMessage(baseOverview, "package_name=missing"), "当前筛选条件下没有许可证记录。");
});

test("historical inventory is unavailable rather than clean", () => {
  const payload = { ...baseOverview, status: "unavailable", inventory_available: false };
  assert.match(overviewNotice(payload).text, /未记录许可证库存/);
  assert.match(emptyMessage(payload, ""), /无法展示许可证评估/);
});

test("partial inventory stays visible and reports coverage gaps", () => {
  const notice = overviewNotice({ ...baseOverview, status: "partial", coverage: { providers_complete: false, assessment_complete: false, dropped_records: 2 } });
  assert.equal(notice.tone, "warning");
  assert.match(notice.text, /已有评估仍保留展示/);
  assert.match(notice.text, /覆盖缺口/);
});

test("failed inventory does not claim clean", () => {
  const notice = overviewNotice({ ...baseOverview, status: "failed" });
  assert.equal(notice.tone, "error");
  assert.match(notice.text, /不能据此认定项目无风险/);
});

test("classification labels avoid legal conclusions", () => {
  assert.equal(classificationLabel("weak_copyleft"), "弱 Copyleft");
  assert.equal(classificationLabel("network_copyleft"), "网络 Copyleft");
  assert.equal(classificationLabel("invalid"), "无效 SPDX 表达式");
});

test("detail model is assessment-based and preserves package and normalization", () => {
  const model = detailViewModel(detail);
  assert.equal(model.assessmentId, "assess-1");
  assert.equal(model.packageName, "Alpha");
  assert.equal(model.packageVersion, "1.0");
  assert.equal(model.originalExpression, "mit");
  assert.equal(model.canonicalExpression, "MIT");
  assert.equal(model.normalizationStatus, "canonical");
  assert.equal(model.findingCount, 0);
});

test("WITH exception remains present and requires review", () => {
  const expression = "GPL-2.0-only WITH Classpath-exception-2.0";
  const model = detailViewModel({ ...detail, assessment: { ...detail.assessment, classification: "strong_copyleft", severity: "high" }, normalization: { ...detail.normalization, original_expression: expression, canonical_expression: expression, exception_ids: ["Classpath-exception-2.0"] } });
  assert.equal(model.expression, expression);
  assert.deepEqual(model.exceptionIds, ["Classpath-exception-2.0"]);
});

test("OR alternative expression remains complete", () => {
  const expression = "MIT OR GPL-3.0-only";
  const model = detailViewModel({ ...detail, assessment: { ...detail.assessment, classification: "strong_copyleft", severity: "high", manual_review_required: true, alternative_terms: true }, normalization: { ...detail.normalization, original_expression: expression, canonical_expression: expression, license_ids: ["MIT", "GPL-3.0-only"] } });
  assert.equal(model.expression, expression);
  assert.equal(model.alternativeTerms, true);
});

test("permissive detail exists without findings and unlocated detail is explicit", () => {
  assert.equal(detailViewModel(detail).findingCount, 0);
  assert.equal(detailViewModel({ ...detail, location: null }).location, "无精确位置");
});

test("provider count reflects only explicit provider references", () => {
  assert.equal(detailViewModel({ ...detail, provider_refs: [{ name: "scancode" }] }).providerCount, 1);
});

test("friendly API errors cover 404, unfinished, schema, validation and server failures", () => {
  assert.match(errorMessage(new LicenseApiError(404, "License assessment not found in this scan")), /不存在该许可证评估/);
  assert.match(errorMessage(new LicenseApiError(409, "Scan results are not final")), /尚未完成/);
  assert.match(errorMessage(new LicenseApiError(409, "License inventory schema is not supported")), /版本暂不受支持/);
  assert.match(errorMessage(new LicenseApiError(422, "Invalid License query parameters")), /筛选条件无效/);
  assert.match(errorMessage(new LicenseApiError(500, "internal")), /无法加载/);
});

test("detail back navigation preserves overview URL state", () => {
  const query = "page=2&page_size=50&classification=strong_copyleft&unknown=drop";
  assert.equal(overviewDetailHref("scan-a", "assess-1", query), "/scans/scan-a/licenses/assess-1?page=2&page_size=50&classification=strong_copyleft");
  assert.equal(overviewBackHref("scan-a", query), "/scans/scan-a/licenses?page=2&page_size=50&classification=strong_copyleft");
});

test("reason and review guidance stay bounded engineering advice", () => {
  assert.match(reasonLabel("alternative_terms_require_review"), /实际采用的授权路径/);
  assert.match(reviewGuidance("network_copyleft"), /网络服务部署方式/);
  assert.equal(displayExpression({ canonical_expression: null, original_expression: null }), "Unknown");
  assert.equal(displayLocation(null), "无精确位置");
});
