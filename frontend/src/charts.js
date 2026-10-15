import { severityOrder, coverageSummary } from "./domain.js";

const dimensions = [
  {
    label: "命令执行",
    keys: ["shell_execute"],
    description: "Shell、子进程等命令执行能力",
  },
  {
    label: "文件访问",
    keys: ["file_read", "file_write", "file_delete"],
    description: "读取、写入或删除文件的能力",
  },
  {
    label: "网络访问",
    keys: ["network_access"],
    description: "连接网络与请求外部资源的能力",
  },
  {
    label: "数据与凭据",
    keys: ["database_read", "database_modify", "credential_access"],
    description: "访问数据库、修改数据或读取凭据的能力",
  },
  {
    label: "外部操作",
    keys: ["send_message", "external_state_change"],
    description: "发送消息或改变外部系统状态的能力",
  },
];

export function capabilityProfile(tools = [], status = "unavailable") {
  const available = ["success", "partial"].includes(status);
  const axes = dimensions.map((d) => ({
    ...d,
    value: available ? 0 : null,
    tools: [],
  }));
  let omitted = 0;
  for (const tool of tools) {
    for (const cap of tool.capabilities || []) {
      const axis = axes.find((a) => a.keys.includes(cap.capability));
      if (
        !axis ||
        !Number.isFinite(cap.impact) ||
        cap.impact < 1 ||
        cap.impact > 5
      ) {
        omitted++;
        continue;
      }
      if (!available) continue;
      axis.value = Math.max(axis.value, cap.impact);
      if (!axis.tools.some((t) => t.id === tool.id)) axis.tools.push(tool);
    }
  }
  return { axes, available, omitted };
}

export function moduleRiskRows(scan) {
  return [
    {
      key: "secret",
      route: "secrets",
      label: "Secret 安全",
      categories: ["secret"],
    },
    {
      key: "license",
      route: "licenses",
      label: "许可证",
      categories: ["license"],
    },
    {
      key: "agent_security",
      route: "agents",
      label: "Agent 安全",
      categories: ["agent_security", "tool_exposure", "unresolved"],
    },
    {key: 'tool_capability', route: 'components', label: '工具能力', categories: ['tool_capability']},
  ].filter(row => row.key in coverageSummary(scan).modules).map((row) => {
    const findings = (scan.findings || []).filter((f) =>
      row.categories.includes(f.category),
    );
    return {
      ...row,
      total: findings.length,
      status: scan.metadata?.scanners?.[row.key]?.status || "unavailable",
      counts: Object.fromEntries(
        severityOrder.map((s) => [
          s,
          findings.filter((f) => f.severity === s).length,
        ]),
      ),
    };
  });
}
