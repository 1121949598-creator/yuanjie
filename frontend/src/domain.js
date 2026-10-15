export const severityOrder = ["critical", "high", "medium", "low", "info"];
export const severityLabels = {
  critical: "严重",
  high: "高风险",
  medium: "中风险",
  low: "低风险",
  info: "信息",
};
export const statusLabels = {
  success: "已完成",
  completed: "已完成",
  partial: "部分完成",
  unavailable: "不可用",
  disabled: "未执行",
  failed: "失败",
  not_applicable: "不适用",
};
export const moduleNames = {
  secret: "Secret 安全",
  license: "许可证",
  agent_security: "Agent 安全",
  tool_capability: "工具能力",
  component_security: "声明与能力",
};
export const categoryLabels = {
  secret: "Secret",
  license: "许可证",
  agent_security: "Agent 安全",
  tool_exposure: "工具暴露",
  unresolved: "未解析绑定",
  tool_capability: "工具能力",
};
export const capabilityLabels = {
  file_read: "读取文件",
  file_write: "写入文件",
  file_delete: "删除文件",
  shell_execute: "执行 Shell",
  network_access: "网络访问",
  database_read: "数据库读取",
  database_modify: "数据库写入",
  send_message: "发送消息",
  credential_access: "访问凭据",
  external_state_change: "外部状态变更",
};
export const classificationLabels = {
  permissive: "宽松许可",
  weak_copyleft: "弱 Copyleft",
  strong_copyleft: "强 Copyleft",
  network_copyleft: "网络 Copyleft",
  unknown: "未知许可",
  invalid: "表达式无效",
  manual_review: "需人工复核",
  unclassified: "未分类",
};
export const severityLabel = (value) =>
  value == null ? "不适用" : severityLabels[value] || value;
export const percent = (value) =>
  value == null || !Number.isFinite(Number(value))
    ? "—"
    : `${Math.round(Number(value) * 100)}%`;
export const formatDate = (value) =>
  value
    ? new Date(value).toLocaleString("zh-CN", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";
export const agentFindings = (items = []) =>
  items.filter((f) =>
    ["agent_security", "tool_exposure", "unresolved"].includes(f.category),
  );
export function coverageSummary(scan) {
  const scanners = scan?.metadata?.scanners || {};
  const keys = scan?.metadata?.scan_profile?.requested_modules || ['secret', 'license', 'agent_security'];
  const modules = Object.fromEntries(keys.map(key => [key, moduleNames[key] || key]));
  const applicable = keys.filter(key => scanners[key]?.status !== 'not_applicable');
  const available = applicable.filter((k) =>
    ["success", "partial"].includes(scanners[k]?.status),
  ).length;
  const complete = applicable.length > 0 && keys.every(
    (k) => ['success', 'not_applicable'].includes(scanners[k]?.status),
  );
  return { available, complete, scanners, modules, total: applicable.length };
}
export function summarizeRisk(scan) {
  const findings = scan?.findings || [];
  const level = severityOrder.find((s) =>
    findings.some((f) => f.severity === s),
  );
  return level
    ? { label: severityLabel(level), level }
    : coverageSummary(scan).complete
      ? { label: "未发现已覆盖风险", level: "none" }
      : { label: "覆盖待补全", level: "unknown" };
}
export function sortFindings(items = []) {
  return [...items].sort(
    (a, b) =>
      severityOrder.indexOf(a.severity) - severityOrder.indexOf(b.severity) ||
      (b.confidence ?? 0) - (a.confidence ?? 0),
  );
}
export const findingLocation = (f) => f?.evidence?.[0]?.source_span || null;
export const hasExample = (scan) =>
  Boolean(scan?.metadata?.presentation?.synthetic || /^synthetic-(release|research|secrets|dynamic|mcp)$/.test(scan?.project_name || ""));
