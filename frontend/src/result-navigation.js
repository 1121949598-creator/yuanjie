import { agentFindings } from './domain.js';

export const resultLabels = {
  workspace: '结果概览',
  secrets: '敏感凭据',
  licenses: '许可证与依赖',
  agents: '任务与权限',
  components: '声明与能力',
  overview: '风险清单',
  report: '检测报告',
};

// Saved scope controls new records. URL/browser preferences are legacy hints,
// not authority to add checks that were never requested.
export function resultNavigation(scan, { mode = 'project', professional = false, componentSecurity = null } = {}) {
  if (!scan) return [];
  const plan = scan.metadata?.scan_profile;
  const requested = plan?.requested_modules || [];
  const showAgents = plan ? requested.includes('agent_security')
    : professional || mode === 'agent' || agentFindings(scan.findings).length > 0
      || !!(scan.agents?.length || scan.tools?.length);
  const showComponents = plan ? requested.some(key => ['tool_capability', 'component_security'].includes(key))
    : professional || mode === 'agent' || mode === 'download'
      || (componentSecurity?.scan_id === scan.id && !!componentSecurity.components?.length);
  return [
    ['workspace', 'LayoutDashboard', resultLabels.workspace, '先看检查覆盖、主要发现和下一步建议'],
    ...(!plan || requested.includes('secret') ? [['secrets', 'KeyRound', resultLabels.secrets, '核对疑似密钥、密码和脱敏证据']] : []),
    ...(!plan || requested.includes('license') ? [['licenses', 'FileCheck2', resultLabels.licenses, '查看许可库存、依赖声明与待复核项']] : []),
    ...(showAgents ? [['agents', 'Bot', resultLabels.agents, '查看 Agent 任务、工具绑定与权限边界']] : []),
    ...(showComponents ? [['components', 'GitCompareArrows', plan?.id === 'download' || (!plan && mode === 'download') ? '工具能力' : resultLabels.components, '核对用途声明、静态能力和源码依据']] : []),
    ['overview', 'ScanLine', resultLabels.overview, '搜索和筛选本次扫描的完整风险列表'],
    ['report', 'FileText', resultLabels.report, '汇总本次结果，下载 PDF 或导出 JSON'],
  ];
}
