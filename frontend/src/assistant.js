import { reactive } from 'vue';
export const assistant = reactive({ phase: '', fileReady: false, error: '' });
export function resetAssistant() { Object.assign(assistant, { phase: '', fileReady: false, error: '' }); }
export function taskHint({ phase, error, fileReady, loading, scanError, scan, complete, section, path }) {
  if (error || scanError) return { mood: 'warning', title: '这一步需要再试一次', text: '操作未完成。请查看页面中的错误说明；不要把失败当成检查通过。' };
  if (phase) return { mood: phase === 'uploading' ? 'thinking' : 'analyzing', title: phase === 'uploading' ? '正在上传源码' : '正在静态分析', text: phase === 'uploading' ? '上传完成后会开始检查，不执行目标代码。' : '服务未提供分阶段进度。请等待实际结果，不需要重复提交。' };
  if (loading) return { mood: 'thinking', title: '正在读取结果', text: '正在读取保存的风险和证据，请稍等。' };
  if (path.startsWith('/scan/') && scan) {
    if (!complete) return { mood: 'warning', title: '结果有检查缺口', text: '请先看模块覆盖状态。未启用或部分完成的检查，不能算作通过。' };
    if (scan.findings?.length) return { mood: 'warning', title: '有项目需要复核', text: section === 'report' ? '报告保留了风险与证据，请逐项核对。' : '点击风险条目查看证据，再判断该怎样处理。' };
    return { mood: 'success', title: '这次检查已完成', text: '当前静态检查未发现风险，不代表绝对安全，仍需结合实际使用范围判断。' };
  }
  if (fileReady) return { mood: 'success', title: '源码包准备好了', text: '点击开始检查。我会在这里陪你等结果。' };
  if (path === '/entry') return { mood: 'guide', title: '选一条适合你的路线', text: '这是本地欢迎入口，不需要账号，也不会收集密码。' };
  if (path === '/history') return { mood: 'guide', title: '接着看上次的结果', text: '打开一条记录，可以继续查看证据或导出报告。' };
  return { mood: 'guide', title: '你好，我是小护', text: path === '/new' ? '准备源码 ZIP。下载的工具、自己的项目和专业 Agent，记得选对检查入口。' : '下载的工具先检查再安装，自己的项目先检查再发布。点击我可以收起提示。' };
}
