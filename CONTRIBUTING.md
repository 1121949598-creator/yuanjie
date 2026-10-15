# Contributing

欢迎贡献新的静态适配器、规则、完全合成测试样例和误报案例。提交前请运行 `pytest`，并说明测试对象、预期 Finding 和不执行第三方代码的依据。

不要在 Issue、测试、截图或数据集中提交真实 Token、密钥、个人数据或无权再分发的第三方源码。Secret 测试值必须明显属于合成数据。新增第三方依赖或借鉴内容时同步更新 `THIRD_PARTY_RESOURCES.md`。

动态绑定不能可靠恢复时应返回 `unresolved`，不能为了提高覆盖率而导入模块、运行安装脚本或启动 MCP Server。
