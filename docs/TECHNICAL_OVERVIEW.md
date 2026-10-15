# 源界技术概览

## 1. 处理链路

```text
本地目录 / ZIP
      ↓
安全导入与文件限额检查
      ↓
Secret → License → Agent/Tool/MCP
      ↓
统一 Finding、Evidence、脱敏和覆盖状态
      ↓
SQLite + JSON 结果
      ↓
Web 工作台 / CLI / HTML-PDF 报告
```

扫描过程只读取待审项目的源码和静态配置，不导入、不安装、不执行待审代码，不启动待审 MCP Server，也不验证真实凭据。

## 2. 主要模块

| 模块 | 作用 |
| --- | --- |
| Secret Security | 规则、熵、上下文过滤、占位符过滤、掩码和 HMAC 指纹 |
| License Security | 许可证、依赖身份、SPDX 规范化和外部 Provider 覆盖状态 |
| Agent Security | Agent、Tool、Binding、能力分类、任务相关性和过度暴露风险 |
| Safe Import | ZIP 路径穿越、符号链接、文件数量、体积和压缩比检查 |
| Reporting | 结果持久化、证据定位、覆盖状态和报告导出 |

## 3. 结果解释

`success`、`partial`、`unavailable`、`disabled` 和 `failed` 表示模块覆盖状态，不是“安全/不安全”的简单结论。没有 Finding 不等于项目绝对安全；评审时应同时查看 Finding、Evidence、warnings 和扫描器状态。

Agent 的动态绑定、未覆盖框架、外部许可证工具缺失等情况会被明确标记为不确定或不可用，不能被解释为已经完整检查。

## 4. 可复现边界

本提交包提供源码、构建后的 Web 资源、合成示例、测试和安装/启动脚本。模型权重、外部许可证工具和本机运行数据不作为无条件的默认依赖；若启用这些能力，应按技术报告和运行日志核对实际覆盖。
