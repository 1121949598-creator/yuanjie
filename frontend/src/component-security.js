export const relations = {
  justified: {
    label: "关联合理",
    hint: "声明与能力关联充分，不代表绝对安全",
    color: "#27857d",
  },
  needs_review: {
    label: "待复核",
    hint: "范围、目标或控制信息需要人工确认",
    color: "#b37c1c",
  },
  inconsistent: {
    label: "不一致",
    hint: "能力与声明用途明显不一致",
    color: "#c65043",
  },
  insufficient_evidence: {
    label: "证据不足",
    hint: "目前无法作可靠判断",
    color: "#718294",
  },
};
export const statuses = {
  success: "已完成",
  partial: "部分完成",
  unavailable: "不可用",
  failed: "执行失败",
  resolved: "已解析",
  unresolved: "未解析",
  disabled: "未执行",
  not_applicable: "不适用",
};
export const statusLabel = (value) => statuses[value] || value || "未知";
export function relativeLocation(span) {
  const path = span?.path;
  if (
    typeof path !== "string" ||
    !path ||
    /^[a-z]:|^[\\/]|(^|[\\/])\.\.([\\/]|$)/i.test(path)
  )
    return "位置不可展示";
  return (
    path + (Number.isInteger(span.start_line) ? ":" + span.start_line : "")
  );
}
export function assessmentRows(data) {
  return (data?.components || []).flatMap((entry) =>
    (entry.result?.assessments || []).map((assessment) => ({
      entry,
      assessment,
      capability: (entry.capabilities || []).find(
        (c) => c.capability_id === assessment.capability_id,
      ),
    })),
  );
}
export function relationCounts(data) {
  const counts = Object.fromEntries(
    Object.keys(relations).map((key) => [key, 0]),
  );
  for (const { assessment } of assessmentRows(data))
    if (assessment.relation in counts) counts[assessment.relation]++;
  return counts;
}
export function evidenceFor(row) {
  const refs = [
    ...new Set([
      ...(row.assessment.evidence_refs || []),
      ...(row.assessment.reasons || []).flatMap((r) => r.evidence_refs || []),
    ]),
  ];
  return refs.map((id) => ({
    id,
    item: (row.entry.evidence || []).find((e) => e.evidence_id === id),
  }));
}

export function relationshipCoverageText(data) {
  if (data?.status === 'disabled') return '本次基础检查未执行声明与能力分析。需要检查 Agent 任务与权限时，请从 Agent 专项入口重新提交源码包。';
  if (data?.status === 'not_applicable') return '没有识别到受支持的 Agent 结构，本次未执行 Agent 声明与能力分析。这不是安全结论。';
  if (data?.status === 'unavailable') return '这次扫描没有可用的声明能力数据。历史记录仍可查看其他模块；重新扫描可生成新版结果。';
  const rows = assessmentRows(data);
  const components = data?.components || [];
  const capabilities = components.reduce((total, entry) => total + (entry.capabilities?.length || 0), 0);
  if (!rows.length) return capabilities
    ? `已识别 ${components.length} 个组件、${capabilities} 项能力，但尚未生成关系判断。请查看算法状态与证据缺口；这不是检查通过。`
    : `已识别 ${components.length} 个组件，但未提取到可判断的静态能力，因此没有生成关系判断。不是模型判断为安全，请展开“组件与解析覆盖”查看缺口。`;
  const used = rows.filter(row => row.assessment.model?.used === true).length;
  return `已生成 ${rows.length} 项关系判断，其中 ${used} 项使用语义模型。${used < rows.length ? '其余为未使用语义模型的判断，请结合规则、证据与覆盖状态复核。' : '请结合证据与覆盖状态复核。'}`;
}
