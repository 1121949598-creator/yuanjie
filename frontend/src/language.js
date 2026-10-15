// Presentation-only translations. Evidence excerpts and exported records stay original.
const messages = {
  "Private key material": "疑似私钥材料",
  "AWS access key identifier": "AWS 访问密钥标识",
  "GitHub access token": "GitHub 访问令牌",
  "OpenAI-style API key": "疑似 OpenAI API 密钥",
  "Potential JSON Web Token (not signature-verified)":
    "疑似 JWT 令牌（未验证签名）",
  "Database connection URL with credentials": "数据库连接地址包含凭据",
  "Credential-like variable assigned a literal password or secret":
    "敏感变量中直接写入密码或密钥",
  "Potential API key assigned a literal value": "疑似明文 API 密钥",
  "Potential token assigned a literal value": "疑似明文访问令牌",
  "License terms require manual review": "许可证条款需要人工复核",
  "Alternative license terms require review": "可选许可证条款需要复核",
  "Offline syntax and literal validation": "已进行离线语法与字面值检查",
  "No explicit static safety control was detected": "未发现显式的静态安全控制",
  "Engineering compliance review priority; not legal advice":
    "用于确定工程复核优先级，不构成法律意见",
  missing_expression: "当前提供者未获得许可证表达式，需要补充来源并人工核实。",
  catalog_permissive: "许可证命中当前目录的宽松许可分类。仍需遵守对应条款。",
  unknown_license_review: "当前许可目录尚未覆盖该标识，需要人工复核。",
  alternative_terms_require_review:
    "存在可选许可条款，需要核实实际选择与对应义务。",
  exception_terms_require_review: "存在许可证例外条款，需要结合原文复核。",
  weak_copyleft_review: "属于弱 Copyleft，需结合修改、链接与分发方式核查义务。",
  strong_copyleft_review: "属于强 Copyleft，需结合项目使用与分发方式核查义务。",
  network_copyleft_review:
    "属于网络 Copyleft，需结合网络服务与分发方式核查义务。",
  profile_classification_override:
    "当前管理员策略对该许可分类应用了自定义复核要求。",
  "Rotate or revoke the affected API key with its provider.":
    "在凭据提供方轮换或撤销受影响的 API 密钥。",
  "Remove plaintext credentials from source code and artifacts.":
    "从源代码和构建产物中移除明文凭据。",
  "Inject the replacement through environment configuration or a secret manager.":
    "通过环境配置或密钥管理服务注入替换后的凭据。",
  "Move the value to an environment variable or a dedicated secret manager":
    "将敏感值迁移到环境变量或专用密钥管理服务。",
  "Replace the repository value with a documented placeholder":
    "用带有说明的占位符替换仓库中的敏感值。",
  "Rotate the credential if a real value has already been published":
    "如果真实凭据已经公开，请及时轮换或撤销。",
  "Remove the tool from the agent allowlist if it is not required for the declared task":
    "若声明的任务不需要该工具，请从 Agent 工具允许列表中移除。",
  "Replace general shell execution with a narrow command adapter or sandbox":
    "使用受限命令适配器或沙箱替代通用 Shell 执行能力。",
  "Confirm the applicable license terms and the actual use, modification and distribution context":
    "确认适用的许可证条款，以及实际使用、修改和分发方式。",
  "Review attribution, source availability and other obligations with the responsible compliance reviewer":
    "与负责复核的人员确认署名、源码提供等许可义务。",
  "Confirm any chosen alternative or exception before relying on it":
    "使用可选条款或例外条款前，确认选择及适用条件。",
};

export function localize(value) {
  if (!value) return value;
  if (messages[value]) return messages[value];
  const patterns = [
    [
      /^Potential over-exposed tool: (.+)$/,
      (name) => `工具可能超出任务所需能力：${name}`,
    ],
    [
      /^Maximum capability impact is (.+)$/,
      (number) => `最高能力影响权重为 ${number}`,
    ],
    [
      /^Task-tool necessity signal is (.+)$/,
      (number) => `任务与工具的必要性信号为 ${number}`,
    ],
    [/^Matched rule (.+)$/, (rule) => `命中规则 ${rule}`],
    [/^Candidate entropy is (.+)$/, (number) => `候选值的信息熵为 ${number}`],
  ];
  for (const [pattern, render] of patterns) {
    const match = value.match(pattern);
    if (match) return render(match[1]);
  }
  return value;
}

export const secretTypes = {
  api_key: "API 密钥",
  token: "访问令牌",
  password: "密码",
  private_key: "私钥",
  aws_access_key: "AWS 密钥",
  database_credential: "数据库凭据",
  jwt: "JWT 令牌",
};
