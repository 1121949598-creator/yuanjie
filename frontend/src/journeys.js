export const journeys = {
  download: {
    title: '检查下载的工具', audience: '普通用户', scene: 'install_precheck',
    heading: '安装之前，先看清它能做什么。',
    description: '准备使用 Skill、MCP 或开源工具？导入下载的源码 ZIP，了解它会接触哪些文件、网络和凭据。',
    action: '开始安装前检查', result: 'components',
  },
  project: {
    title: '检查自己的项目', audience: '项目作者', scene: 'release_precheck',
    heading: '分享之前，把遗漏找出来。',
    description: '上传你准备公开的项目，检查疑似密钥、许可证与依赖信息，保留可回看的证据。',
    action: '开始发布前检查', result: 'workspace',
  },
  agent: {
    title: 'Agent 专项审查', audience: '专业用户', scene: 'release_precheck',
    heading: '任务需要的，与工具能做的。',
    description: '面向 Agent 开发者，审查任务描述、Tool 绑定、敏感权限与声明—能力关系。',
    action: '开始 Agent 专项审查', result: 'agents',
  },
};
export function journeyKey(value) { return Object.hasOwn(journeys, value) ? value : 'project'; }
const resultSections = new Set(['workspace', 'components', 'agents', 'secrets']);
export function rememberJourney(id, mode, section) {
  try { localStorage.setItem(`openguard.journey.${id}`, journeyKey(mode)); } catch {}
  if (resultSections.has(section)) {
    try { localStorage.setItem(`openguard.example-result.${id}`, section); } catch {}
  }
}
export function scanJourney(id, fallback, scan) {
  const persisted = scan?.id === id ? (scan.metadata?.scan_profile?.id || scan.scan_profile?.id) : null;
  if (Object.hasOwn(journeys, persisted)) return persisted;
  try { return journeyKey(localStorage.getItem(`openguard.journey.${id}`) || fallback); } catch { return journeyKey(fallback); }
}
export function historyResultPath(scan, fallback) {
  const scene = scan.metadata?.component_security_scene;
  const defaultMode = scene === 'install_precheck' ? 'download'
    : scene === 'release_precheck' && journeyKey(fallback) === 'download' ? 'project'
    : journeyKey(fallback);
  const mode = scanJourney(scan.id, defaultMode, scan);
  let section = journeys[mode].result;
  try {
    const saved = localStorage.getItem(`openguard.example-result.${scan.id}`);
    if (resultSections.has(saved)) section = saved;
  } catch {}
  return `/scan/${encodeURIComponent(scan.id)}/${section}?mode=${mode}`;
}
