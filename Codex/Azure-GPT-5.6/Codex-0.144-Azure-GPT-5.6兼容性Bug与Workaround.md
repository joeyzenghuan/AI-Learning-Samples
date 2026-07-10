# Codex 0.144 使用 Azure OpenAI GPT-5.6 的兼容性 Bug 与 Workaround

## TL;DR：直接使用随附的模型目录

本文已随附修复好的 `models-azure.json`，其中 GPT-5.6 Sol、Terra 和 Luna 均已设置 `use_responses_lite: false` 与 `multi_agent_version: null`。最直接的修复方式是：

1. 将随附文件复制到 Codex 用户目录，并限制文件权限：

  ```bash
  mkdir -p ~/.codex
  cp models-azure.json ~/.codex/models-azure.json
  chmod 600 ~/.codex/models-azure.json
  ```

2. 在 `~/.codex/config.toml` 顶层加入以下配置；路径请替换为当前用户的绝对路径：

  ```toml
  model_catalog_json = "/Users/<username>/.codex/models-azure.json"
  ```

3. 完全退出并重新打开 ChatGPT/Codex App，或重启 Codex CLI 会话，然后新建 thread 验证。不要只关闭窗口，也不要继续使用旧 thread 判断配置是否生效。

> 记录日期：2026-07-10<br>
> 状态：OpenAI Codex 上游已有人报告，本文记录临时绕过方案；后续应优先升级到包含正式修复的版本。

## 1. 问题概述

Codex CLI `0.144.0` 以及新版统一 ChatGPT/Codex App 内置的 `0.144.0-alpha.4`，通过自定义 `model_provider` 调用 Azure OpenAI 的 GPT-5.6 部署时，可能在每次请求开始阶段返回 HTTP 400：

```text
X-OpenAI-Internal-Codex-Responses-Lite only supports function tools,
custom tools, and client-executed tool search.
```

典型错误体：

```json
{
  "error": {
    "message": "X-OpenAI-Internal-Codex-Responses-Lite only supports function tools, custom tools, and client-executed tool search.",
    "type": "invalid_request_error",
    "param": "tools",
    "code": "unsupported_value"
  }
}
```

已知受影响的模型元数据包括：

- `gpt-5.6-sol`
- `gpt-5.6-terra`
- `gpt-5.6-luna`

该问题不是 Azure deployment、API Key 或 endpoint 本身失效。相同 deployment 通过 Azure Responses API 直接发送最小请求可以正常返回结果。

## 2. 根本原因

### 2.1 GPT-5.6 被无条件启用了 Responses Lite

Codex `0.144.0` 内置模型目录中的 GPT-5.6 条目包含类似配置：

```json
{
  "slug": "gpt-5.6-sol",
  "tool_mode": "code_mode_only",
  "multi_agent_version": "v2",
  "use_responses_lite": true
}
```

这些字段按照模型 slug 应用，没有先判断当前 provider 是否是 OpenAI 托管的 ChatGPT/Codex backend。使用 Azure 或其他自定义 provider 时，Codex 因而仍会发送内部请求头：

```http
X-OpenAI-Internal-Codex-Responses-Lite: true
```

Responses Lite 是 Codex 内部使用的精简传输格式，对允许的工具类型有额外限制。Azure OpenAI 当前并不完整支持 Codex 按这种方式组合的工具定义，因此拒绝请求。

### 2.2 关闭 Responses Lite 后还可能遇到 collaboration namespace 错误

仅去掉 Responses-Lite 行为后，Codex 仍可能在 `additional_tools` developer item 中发送：

```json
{
  "type": "namespace",
  "name": "collaboration",
  "description": "Tools for spawning and managing sub-agents."
}
```

Azure 可能继续返回：

```text
Invalid Value: 'tools'. Namespace 'collaboration' is reserved for encrypted tool use by this model.
```

因此完整 workaround 需要同时处理：

1. `use_responses_lite`
2. `multi_agent_version` 或 multi-agent tool namespace

## 3. 推荐 Workaround：自定义模型目录

这是目前最干净的临时方案，不需要在 Azure endpoint 前增加代理。

### 3.1 备份配置

修改前备份 Codex 用户配置：

```bash
cp ~/.codex/config.toml ~/.codex/config.toml.backup.$(date -u +%Y-%m-%dT%H-%M-%SZ)
```

如果已经存在自定义模型目录，也应先备份。

### 3.2 获取完整模型目录

`model_catalog_json` 会替换 Codex 内置模型目录，因此应使用完整目录，不建议只创建一个最小 GPT-5.6 条目，否则模型选择器中可能缺少其他模型。

本次验证使用触发回归的上游模型目录提交 `3380969a29`：

```bash
curl -fsSL \
  https://raw.githubusercontent.com/openai/codex/3380969a29/codex-rs/models-manager/models.json \
  -o /tmp/codex-models.json
```

将三个 GPT-5.6 模型的字段调整为：

```json
"use_responses_lite": false,
"multi_agent_version": null
```

macOS/Linux 可使用：

```bash
jq '
  (.models[] |
    select(
      .slug == "gpt-5.6-sol" or
      .slug == "gpt-5.6-terra" or
      .slug == "gpt-5.6-luna"
    ) |
    .use_responses_lite
  ) = false |
  (.models[] |
    select(
      .slug == "gpt-5.6-sol" or
      .slug == "gpt-5.6-terra" or
      .slug == "gpt-5.6-luna"
    ) |
    .multi_agent_version
  ) = null
' /tmp/codex-models.json > ~/.codex/models-azure.json

chmod 600 ~/.codex/models-azure.json
```

验证修改结果：

```bash
jq -r '
  .models[] |
  select(.slug | startswith("gpt-5.6-")) |
  [.slug, (.use_responses_lite | tostring), (.multi_agent_version | tostring)] |
  @tsv
' ~/.codex/models-azure.json
```

预期结果：

```text
gpt-5.6-sol    false    null
gpt-5.6-terra  false    null
gpt-5.6-luna   false    null
```

### 3.3 修改 Codex 配置

在 `~/.codex/config.toml` 顶层加入 `model_catalog_json`：

```toml
model = "gpt-5.6-sol"
model_provider = "azure"
model_catalog_json = "/Users/<username>/.codex/models-azure.json"
model_reasoning_effort = "high"

[model_providers.azure]
name = "Azure OpenAI"
base_url = "https://<your-resource>.openai.azure.com/openai/v1"
env_key = "AZURE_OPENAI_API_KEY"
wire_api = "responses"
```

注意：

- `model_catalog_json` 建议使用绝对路径，不要依赖 `~` 展开。
- `model` 是 Azure deployment name；如果实际 deployment 名不同，应填写实际名称。
- API Key 通过 `env_key` 指定的环境变量注入，不要写进配置文件。
- 对新版 App、Codex CLI 和 IDE 扩展而言，用户级配置通常是共享的。

### 3.4 完全重启 App

自定义模型目录只在启动时加载。修改后必须：

1. 完全退出 ChatGPT/Codex App，而不只是关闭窗口。
2. 重新打开 App。
3. 新建 thread 进行测试；不要只依赖旧 thread 的缓存状态。

## 4. 验证方法

### 4.1 普通响应

```bash
codex exec \
  --ephemeral \
  --skip-git-repo-check \
  "Reply with exactly: OK"
```

预期返回：

```text
OK
```

### 4.2 本地工具调用

```bash
codex exec \
  --ephemeral \
  --skip-git-repo-check \
  "Use the shell tool to run pwd, then reply with exactly the resulting path."
```

必须确认 Codex 实际产生了 shell/exec tool call，而不仅是输出文本。

### 4.3 验证 App 内置版本

桌面 App 与全局 npm CLI 可能不是同一版本。macOS 新版 ChatGPT App 可检查其内置二进制：

```bash
/Applications/ChatGPT.app/Contents/Resources/codex --version
```

本次实际验证环境：

```text
ChatGPT App: 26.707.31428
Bundled Codex CLI: 0.144.0-alpha.4
Provider: Azure OpenAI
Model: gpt-5.6-sol
Reasoning effort: high
```

普通响应和真实 shell 工具调用均成功。

## 5. 替代 Workaround

### 5.1 临时回退 Codex

有用户报告回退至 Codex CLI `0.142.5` 可以绕开该回归：

```bash
npm install -g @openai/codex@0.142.5
```

注意：

- npm 安装只会改变全局 CLI，不会改变桌面 App 内置的 Codex 二进制。
- 桌面 App 需要安装对应旧版 App 才能回退。
- 旧版和新版 Codex App 可能使用相同 Bundle ID 和数据目录，不建议同时运行。
- 旧版 App 的自动更新可能会再次把它升级为新版；如需长期保留回退版本，应检查自动更新设置。

### 5.2 修改 multi-agent namespace

部分用户验证过以下组合：

- `use_responses_lite = false`
- 将 multi-agent v2 的 namespace 从 `collaboration` 改成其他名称，例如 `agents`

这种方式可能保留更多 multi-agent 能力，但属于实验性兼容方案，行为更依赖具体 Codex 构建。若目标是优先恢复稳定的单 agent、shell 和文件工具调用，建议先使用 `multi_agent_version: null`。

### 5.3 本地代理过滤请求

也可以在 Codex 与 Azure 之间增加本地代理：

1. 删除 Codex 内部 Responses-Lite 请求头。
2. 从 `additional_tools` 中移除 `collaboration` namespace。
3. 将请求转发到 Azure Responses endpoint。

该方案已经有人验证能恢复普通聊天和 shell 调用，但会增加维护成本，而且无法使用被过滤掉的原生 collaboration/subagent 功能。除非无法使用自定义模型目录，否则不推荐。

## 6. 重要注意事项

### 6.1 本地模型目录需要维护

自定义模型目录会覆盖内置目录，不会自动跟随 Codex 后续模型目录更新。升级 Codex 后应检查：

- 上游是否已正式修复 Azure/provider capability gating。
- 新版模型目录是否新增字段或模型。
- 是否还需要保留 `model_catalog_json`。

正式修复发布后，应优先移除 workaround，恢复使用内置目录。

### 6.2 不要只删除请求头

该问题包含 Responses Lite 和 `collaboration` namespace 两层兼容性。只删除请求头可能从第一个 400 变成第二个 400，并不代表修复完成。

### 6.3 multi-agent 能力可能受限

设置 `multi_agent_version: null` 的首要目标是避免 Azure 拒绝内部 collaboration namespace。普通聊天、shell 和文件工具可以正常工作，但原生多智能体协作能力可能被禁用或改变，不应假设其完全可用。

### 6.4 App 和 CLI 可能加载不同二进制

终端中的 `codex --version` 只代表 PATH 中的全局 CLI。桌面 App 使用自己打包的 Codex 二进制。排障时必须分别确认版本。

### 6.5 新旧 App 不建议同时运行

旧版与新版构建可能共享：

- Bundle ID
- `~/.codex/config.toml`
- 会话和缓存目录
- 自动更新偏好

macOS 可能只激活已经运行的那个版本，或者出现缓存、配置和自动更新冲突。切换版本前应完全退出当前版本。

### 6.6 不要泄露凭据

记录日志、提交 issue 或共享配置时，应清理：

- Azure API Key
- 完整资源 endpoint（如组织安全策略要求隐藏）
- tenant、subscription、内部 deployment 信息
- 请求和响应中可能包含的客户数据

## 7. 上游 Issue

截至 2026-07-10，相关公开问题仍处于 Open 状态：

- [openai/codex#31870 — Codex with GPT-5.6-Sol through Azure fails every turn with Responses-Lite](https://github.com/openai/codex/issues/31870)
- [openai/codex#31875 — Azure GPT-5.6-Sol fails due to Codex-specific tools / collaboration namespace](https://github.com/openai/codex/issues/31875)
- [openai/codex#31882 — GPT-5.6 model metadata causes Azure/custom-provider 400s](https://github.com/openai/codex/issues/31882)

## 8. 清理 Workaround

当新版 Codex 已正式修复 Azure GPT-5.6 兼容性后：

1. 备份当前配置。
2. 从 `config.toml` 删除 `model_catalog_json`。
3. 保留本地 JSON 一段时间作为回滚备份。
4. 完全重启 App。
5. 重新执行普通响应和 shell tool-call 验证。
6. 确认无误后再删除旧的本地模型目录和旧版 App。
