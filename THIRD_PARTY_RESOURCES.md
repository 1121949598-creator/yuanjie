# 第三方资源与自主开发边界

## 声明—能力语义关联（Contract 1.0）

| 资源 | 用途 / 采用方式 | 固定版本 / 许可 | 验证与分发边界 |
|---|---|---|---|
| [paraphrase-multilingual-MiniLM-L12-v2](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2) | 本地 CPU 语义向量，仅比较声明用途与 B 输出的标准化能力事实 | revision `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`；`model.safetensors` SHA-256 `eaa086f0ffee582aeb45b36e34cdd1fe2d6de2bef61f8a559a1bbc9bd955917b`；模型卡标注 Apache-2.0 | 当前代码包不含模型权重；正式分发前须复核模型卡、训练数据说明和通知文件。模型不可用时必须输出 `partial` 且 `model.used=false` |
| sentence-transformers / PyTorch / Transformers | 上述本地模型的可选运行依赖 | C 的验证版本分别为 `6.1.0`、`2.14.0+cpu`、`5.17.0`；具体许可证以实际发行包为准 | 不并入主依赖锁；按 `experiments/requirements-contract-cpu.txt` 建立隔离环境，不把缓存、权重或第三方源码装入提交包 |

语义相似度不是恶意概率或安全结论。能力事实、证据约束、敏感边界和降级策略由本项目自研规则负责；输入不发送到外部模型服务。

## License L4 真实工具验证（2026-09-10）

| 资源 | 用途 / 采用方式 | 版本 / 许可 | 验证与边界 |
|---|---|---|---|
| [ScanCode Toolkit v32.5.0](https://github.com/aboutcode-org/scancode-toolkit/releases/tag/v32.5.0) | 官方 CPython 3.12 Windows bundle；仅通过受控 CLI → JSON Adapter 使用 | 32.5.0；Apache-2.0；官方 zip SHA-256 `d659258d8067d36403f8a4df21ca0446b1a56f615754c92139d8a264d57abe49` | 隔离于目标项目；不 import `packagedcode` / `licensedcode`，不复制 parser/database；真实 fixture matrix 与 E2E 已执行 |

L4 fixture 是源鉴自建最小静态样本；没有复制上游大型 corpus。仓库内 ScanCode 33.0.0rc1 源码和 ORT 源码仅用于字段/架构审计，33 RC 不进入支持范围；本轮没有运行 ORT、包管理器或构建工具。

## License L2 新增直接依赖（2026-09-10）

| 资源 | 用途 / 采用方式 | 版本 / 许可 | 自主边界 |
|---|---|---|---|
| [PyPA packaging](https://packaging.pypa.io/en/stable/licenses.html) | 使用公开 `packaging.licenses.canonicalize_license_expression` / `InvalidLicenseExpression` 做 SPDX 语法校验与 canonicalization | `packaging>=26.3,<27`，已安装并测试 26.3；Apache-2.0 OR BSD-2-Clause，依据当前发行包 `packaging-26.3.dist-info/licenses/LICENSE`、LICENSE.APACHE、LICENSE.BSD | 不复制库源码或 SPDX DB；源鉴自行实现输入限额、20 项审核分类 Catalog、组合审核策略、Finding 投影和库存持久化 |

本轮将环境原已存在的 packaging 明确声明为源鉴直接运行依赖，没有安装/下载包。没有复制 ScanCode license database/package parser、ORT classifications/evaluator 或任何 Secret 上游规则。ScanCode/ORT 的引用方式与 L1 来源记录不变；实际 executable 均未发现，**未执行真实工具验证**。完整设计及边界见 [L2 报告](docs/LICENSE_POLICY_INTEGRATION.md)。

本清单用于比赛合规。提交前须把“版本/commit”列固定为实际使用或查阅时的 commit，并复核许可证。

| 资源 | 用途 | 采用方式 | 许可证/版本记录 | 自研边界 |
|---|---|---|---|---|
| Yelp detect-secrets | Secret 插件、过滤器与基线设计参考 | 设计参考，未复制界面和源码 | Apache-2.0；提交前固定 commit | 统一 Finding、上下文评分、脱敏、修复复测自研 |
| AgentDojo | 任务/工具/安全/效用分离的评测思想 | 论文和测试设计参考 | MIT；提交前固定 commit | 本项目做源码发布前静态审查，不运行其环境 |
| ToolEmu | 危险能力与安全场景 | 分类参考 | Apache-2.0；提交前固定 commit | 静态 AST 证据与规则实现自研 |
| Snyk agent-scan | Agent/MCP 发现与风险类别竞品参考 | 竞品分析，不启动 MCP Server | 提交前复核仓库许可证与 commit | 本项目坚持不执行第三方项目 |
| NVIDIA SkillSpector | 过度权限、描述—行为不一致规则参考 | 竞品和规则术语参考 | Apache-2.0；提交前固定 commit | LangChain/CrewAI/MCP 解析和模型自研 |
| FastAPI / Jinja2 / SQLite | 本地 Web 与持久化 | 运行依赖 | 版本范围见 pyproject.toml | 页面、API 与数据结构自研 |
| scikit-learn | TF-IDF、逻辑回归、评测指标 | 运行依赖 | BSD-3-Clause；版本范围见 pyproject.toml | 特征设计、切分策略和实验脚本自研 |
| PyYAML | 版本化规则和实验配置 | 运行依赖 | MIT；版本范围见 pyproject.toml | 规则内容自研 |

禁止把第三方仓库源码直接纳入公开数据集，除非逐项确认许可证、归属与再分发义务。

## License L1 上游整合记录（2026-09-10）

采用 **Adapter integration / No source vendoring**。以下 commit 为本机已有参考仓库的源码审阅版本，不能当成实际安装或实际运行版本。

| 项目 / 官方仓库 | 用途与整合方式 | 本轮实际测试情况 | 许可证依据 | 源码 / 数据复制 |
|---|---|---|---|---|
| [ScanCode Toolkit](https://github.com/aboutcode-org/scancode-toolkit) | 用户已安装的 CLI；静态 license/package 扫描；JSON 经本项目适配、校验、白名单投影 | 本机 executable 未发现，真实 smoke unavailable；自写 fake CLI 与合成 JSON 使用版本标识 32.4.1，不代表真实工具验证 | [固定 commit NOTICE](https://github.com/aboutcode-org/scancode-toolkit/blob/058f4396269476bdf2abf4a6b679a76f501b7e00/NOTICE)：软件 Apache-2.0；数据 CC-BY-4.0；其附带第三方组件各自遵循原许可证 | 无；不 vendor 源码，不复制 license DB、规则、匹配文本或大型上游 fixture |
| [OSS Review Toolkit](https://github.com/oss-review-toolkit/ort) | 仅导入主机 Settings 明确指定的既有 analyzer/scanner JSON；不调用 ORT CLI | 本机 executable 未发现，真实 smoke unavailable；自写合成 JSON 标识 50.0.0，不代表真实工具验证 | [固定 commit LICENSE](https://github.com/oss-review-toolkit/ort/blob/228f06035a647c3c9fb08fe1e50151cba4a9541f/LICENSE)：Apache-2.0 | 无；不复制 ORT 源码、数据、依赖源码或上游 fixture |

审阅 commit：ScanCode `058f4396269476bdf2abf4a6b679a76f501b7e00`；ORT `228f06035a647c3c9fb08fe1e50151cba4a9541f`。本轮只阅读本机已存在的参考仓库，没有 clone、安装、下载二进制、拉取容器或新增运行依赖。

自研边界：Provider contract、执行限额、失败隔离、JSON 子集校验、内部 Evidence 映射、安全 provenance 和去重。许可证识别与依赖分析仍由上游完成。`tests/fixtures/scancode/`、`tests/fixtures/ort/` 的数据和模拟 CLI 均为本项目自写合成内容，版本号和凭据标记只用于测试。后续若分发第三方二进制或数据，应针对实际发行包另行核查 NOTICE 与依赖清单；本轮交付不包含这些资源。

完整实现与验证范围见 [License L1 报告](docs/LICENSE_UPSTREAM_INTEGRATION.md)。

## 前端改版 v4 新增资源（2026-10-02）

| 资源 | 实际版本与来源 | 许可 / 使用方式 | 团队实现与义务 |
| --- | --- | --- | --- |
| Anime.js | 4.5.0；https://github.com/juliangarnier/anime；npm 锁文件 | MIT；构建进本地前端，驱动小船航线进度 | Vue 组件、船图、航线、暂停/恢复与 reduced-motion 为本项目实现；保留 docs/third-party-licenses/animejs-4.5.0-LICENSE.md |
| 小护八状态图集与首页去船背景 | 内置 image_gen；用户参考图引导 | AI 辅助视觉素材；不自动声称排他的原创权属 | 团队检查颜色、状态、透明度与页面表现；图集实际视口由前端配置 |
| 河流水彩参考图 3/4/5 | 本次用户提供 | 页面浅色背景；原文件来源与对外公开授权应由提交方核对 | 不声称这些原图是团队自绘；最终参赛公开前核对原图权利 |
