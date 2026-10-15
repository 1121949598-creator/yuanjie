// Stable example IDs decide the scene and landing page, not the incoming journey.
const flows = {
  release: { mode: 'project', section: 'workspace', label: '发布前基础检查', icon: 'ShieldCheck' },
  research: { mode: 'agent', section: 'agents', label: 'Agent 安全', icon: 'Bot' },
  secrets: { mode: 'project', section: 'secrets', label: '敏感凭据', icon: 'KeyRound' },
  dynamic: { mode: 'agent', section: 'agents', label: '动态绑定', icon: 'GitBranch' },
  mcp: { mode: 'download', section: 'components', label: '工具能力', icon: 'Network' },
};
export function exampleFlow(id) {
  return Object.hasOwn(flows, id) ? flows[id] : { mode: 'project', section: 'workspace', label: '综合检查', icon: 'ShieldCheck' };
}
