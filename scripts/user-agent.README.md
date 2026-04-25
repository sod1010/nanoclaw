# User Agent — 模拟真人用户与 NanoClaw 自动交互

创建一个模拟真实用户的 Agent（User Agent），通过输入 seed query 作为初始话题，自动与 NanoClaw (Andy) 进行多轮对话。

- **语言像人** — 人设定义借鉴 HER 分层思想（Layer 0-3），对话风格、节奏、口语习惯接近真实用户
- **支持文件传输** — 双向：User Agent 可发送文件，也能接收 NanoClaw 创建的文件
- **飞书实时展示** — 对话过程实时转发到飞书群，支持从飞书输入角色设定

### 飞书展示 Demo

<video src="飞书展示视频.mp4" controls width="600">
  您的浏览器不支持视频播放，请下载 <a href="飞书展示视频.mp4">飞书展示视频.mp4</a> 观看。
</video>

---

## 快速开始

### 前置条件

| 依赖 | 安装 | 说明 |
|------|------|------|
| NanoClaw | 本仓库 | 需要先完成 `/setup` |
| Docker / Colima | `brew install colima && colima start` | 容器运行时 |
| Python 3.10+ | 系统自带或 `brew install python` | User Agent 脚本 |
| lark-cli | `npm i -g @nicepkg/lark-cli` | 仅飞书模式需要 |

### 配置 `.env`

```bash
# API 配置（User Agent 和 NanoClaw 共用）
ANTHROPIC_BASE_URL=https://your-api-gateway.com/v1/anthropic
ANTHROPIC_AUTH_TOKEN=your-token-here
ANTHROPIC_MODEL=claude-sonnet-4-20250514

# 飞书配置（仅飞书模式需要）
FEISHU_LARK_CLI_PROFILE=nanoclaw
```

### 三种使用方式

**方式 1：纯命令行**（最简单）

```bash
# 自动对话 5 轮
python3 scripts/user-agent.py "帮我查看最近的邮件" --auto --max-turns 5

# 带文件发送
python3 scripts/user-agent.py "帮我看看这个代码" -f code.py --auto
```

**方式 2：命令行 + 飞书观察**（对话在终端，同时转发到飞书群）

```bash
python3 scripts/user-agent.py "写个周报" --auto --observe
```

**方式 3：飞书展示模式**（从飞书输入角色，对话在飞书群展示）

```bash
# 先停止 NanoClaw 主服务（避免重复处理）
launchctl unload ~/Library/LaunchAgents/com.nanoclaw.plist

# 启动飞书模式，从飞书群接收角色设定
python3 scripts/user-agent.py --feishu --role-from-feishu --auto --max-turns 5
```

---

## 1. User Agent 人设配置

### HER 分层人设思想

借鉴 [HER（Hierarchical Emotion Reasoning）](https://huggingface.co/ChengyuDu0123/HER-32B) 论文的核心思想：**通过模拟认知过程（而非仅模仿语气）来产生更真实的角色扮演**。

User Agent 的人设定义采用 HER 启发的 **Layer 0-3 分层结构**：

| 层级 | 内容 | 作用 |
|------|------|------|
| Layer 0 | 核心行为规则 | 绝对遵守的底线（如不暴露 AI 身份） |
| Layer 1 | 表达风格 | 口头禅、打字习惯、典型回复模式 |
| Layer 2 | 思维模式 | 优先级判断、追问倾向、决策框架 |
| Layer 3 | 对话节奏 | 开场→追问→关联需求→结束的自然节奏 |

> **注意**：User Agent 借鉴的是 HER 的 **分层人设定义思想**，而非其完整的三层响应架构（System Thinking → Role Thinking → Role Response）。User Agent 使用 `thinking` + `message` 的 chain-of-thought 方式生成回复；HER 的完整三层响应架构在 NanoClaw 侧的 [Roleplay Skill](#roleplay-skill) 中实现。

### 人设配置方式

**内置人设**（`--persona`）：

| 人设 | 风格 | 适用场景 |
|------|------|---------|
| `casual`（默认） | 口语化普通用户 | 日常功能测试 |
| `boss` | 急躁老板，话少催进度 | 压力测试 |
| `dev` | 程序员，关注技术细节 | 技术问答测试 |
| `verbose` | 话多，喜欢解释背景 | 长输入测试 |

**自定义角色**（`--role`）：

```bash
# 直接传角色描述
python3 scripts/user-agent.py "讨论技术方案" \
  --role "焦急的外卖客户李明，30岁上班族" --auto

# 从 .md 文件加载（可使用 persona-template.md 格式）
python3 scripts/user-agent.py "讨论技术方案" --role character.md --auto
```

**从飞书实时输入**（`--role-from-feishu`）：

```bash
python3 scripts/user-agent.py --feishu --role-from-feishu --auto
```

运行后会在飞书群发送提示，等待人类用户输入角色设定：

```
格式 1（结构化）：角色：一个人工智能工程师 / 场景：查询强化学习知识
格式 2（自由描述）：焦急的外卖客户李明，30岁上班族...
```

### 模型可替换性

User Agent 的 LLM 调用（`call_claude()`）使用标准 Anthropic Messages API 格式，修改 `.env` 中的三个配置项即可切换模型：

| 模型类型 | 说明 | 示例 |
|---------|------|------|
| **Claude**（默认） | 通过 Anthropic API 或兼容网关 | `ANTHROPIC_MODEL=claude-sonnet-4-20250514` |
| **开源模型** | 通过兼容 API 网关 | DeepSeek、Qwen 等 |
| **HER 微调模型** | 角色扮演数据微调，更好的人设保持 | [HER-32B](https://huggingface.co/ChengyuDu0123/HER-32B)、[CoSER-70B](https://huggingface.co/Neph0s/CoSER-Llama-3.1-70B) |

使用微调模型可降低成本，同时在角色扮演场景获得更稳定的人设表现。

---

## 2. NanoClaw 配置

### 基础配置

NanoClaw 是对话的另一方（AI 助手 Andy），运行在 Docker 容器中。通过 `.env` 和 claw CLI 配置：

| 配置项 | 说明 | 示例值 |
|--------|------|--------|
| `ANTHROPIC_BASE_URL` | API 网关地址 | `https://your-gateway.com/v1/anthropic` |
| `ANTHROPIC_AUTH_TOKEN` | API 认证 Token | Bearer token |
| `ANTHROPIC_MODEL` | NanoClaw 使用的模型 | `claude-sonnet-4-20250514` |
| `FEISHU_LARK_CLI_PROFILE` | 飞书 CLI profile 名 | `nanoclaw` |

NanoClaw 通过 `claw CLI`（`scripts/claw`）启动容器执行 agent：

```bash
python3 scripts/claw "用户消息内容" --timeout 300
# 内部启动 Docker 容器运行 agent-runner，挂载 groups/main/ 目录
```

NanoClaw 的模型同样可替换 — 修改 `.env` 中的 `ANTHROPIC_MODEL` 即可切换为其他 Claude 模型或兼容 API 的开源模型。

### Roleplay Skill

NanoClaw 侧通过 container skill 实现了 HER 论文的**完整三层响应架构**。我们仿照 NanoClaw 项目中已有的 `add-*` skill（如 `add-telegram`、`add-slack`）的结构，编写了 `/add-roleplay` 安装 skill；skill 的具体内容（三层回复架构、分层人设模板等）则基于 HER 论文的思想撰写。

**HER 三层响应架构**（NanoClaw Roleplay Skill 实现）：

```
┌─────────────────────────────────────────────────────────────────┐
│                    HER Response Structure                        │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 🔍 System Thinking (Third-Person Analysis)              │   │
│  │ "Elizabeth should respond with wit but maintain dignity. │   │
│  │  Consider her pride and her evolving feelings..."       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              ↓                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 💭 Role Thinking (First-Person Inner Monologue)         │   │
│  │ "How dare he presume to know my mind? And yet...        │   │
│  │  there is something in his manner that unsettles me."   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              ↓                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 🎭 Role Response (Speech + Action)                      │   │
│  │ (lifts her chin slightly) "Mr. Darcy, I find your       │   │
│  │ sudden interest in conversation rather remarkable."     │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

- **System Thinking**：第三人称分析角色应如何回应当前情境（`<internal>` 标签，自动剥离不展示）
- **Role Thinking**：角色第一人称内心独白（`<role_thinking>` 标签，可选展示）
- **Role Response**：最终输出的动作描写 + 台词，用户可见的部分

**安装 skill**（`.claude/skills/add-roleplay/SKILL.md`）：

负责引导安装流程 — 检查是否已安装、部署 container skill 文件、重建容器、配置角色定义。在 Claude Code 中运行 `/add-roleplay` 即可触发。

**Container skill**（安装后部署到 `container/skills/roleplay/`）：

```
container/skills/roleplay/
├── SKILL.md              # 激活触发（/roleplay）、三层输出格式、模式切换
├── persona-template.md   # 分层人设模板：Layer 0-3
└── examples.md           # 完整示例
```

- **SKILL.md**：定义 `<internal>` → `<role_thinking>` → `<role_action>` + 台词的三层输出格式
- **persona-template.md**：Layer 0 核心人格（绝对遵守）→ Layer 1 表达风格 → Layer 2 思维模式 → Layer 3 关系处理
- 角色定义写入对应 group 的 `CLAUDE.md`，NanoClaw 自动加载

---

## 3. 交互架构

### 飞书 Bot 间无法互相接收消息

飞书平台限制：**Bot 发出的消息只有人类用户能接收，其他 Bot 无法收到**。因此 User Agent Bot 和 NanoClaw Bot 无法在飞书群中直接对话。

### 解决方案：claw CLI 桥接

```
  飞书群（展示层）                    后端（交互层）
┌──────────────────┐            ┌──────────────────┐
│                  │            │                  │
│  useragent bot ◄─┼── 转发 ───┤  User Agent LLM  │
│  (用户侧消息)     │            │  生成用户消息      │
│                  │            │       │          │
│                  │            │       ▼          │
│                  │            │   claw CLI       │
│                  │            │   (容器交互)      │
│                  │            │       │          │
│  nanoclaw bot  ◄──┼── 转发 ───┤  NanoClaw 回复    │
│  (Andy侧回复)    │            │                  │
│                  │            │                  │
└──────────────────┘            └──────────────────┘
```

1. User Agent LLM 生成消息
2. 通过 `claw CLI` 直接调用 NanoClaw 容器，获取回复
3. 将双方消息分别通过对应 Bot 转发到飞书群展示

### 文件传输

```
User Agent                    NanoClaw 容器                飞书群
    │                              │                         │
    │  ── 文件池选择文件 ──→        │                         │
    │     shutil.copy2 →           │                         │
    │     groups/main/uploads/     │                         │
    │                              │                         │
    │  ── claw CLI 发送消息 ──→     │                         │
    │                    容器读取/修改文件                     │
    │  ←── claw CLI 返回回复 ───    │                         │
    │                              │                         │
    │  ── scan_new_files() ──→     │                         │
    │     检测新建/修改的文件        │                         │
    │                              │                         │
    │  ── UA bot 转发用户消息+文件 ─────────────────→  飞书群  │
    │  ── NC bot 转发 Andy 回复+文件 ───────────────→  飞书群  │
```

- **发送**：`--file-pool` 指定文件目录，LLM 根据上下文自动选择；或 `-f` 直接附件
- **接收**：交互前后快照对比 `groups/main/` 目录，自动检测新建/修改的文件
- **飞书转发**：自动识别图片（`--image`）和普通文件（`--file`），使用相对路径调用 lark-cli

---

## 4. 飞书 Channel 接入

NanoClaw 原生不支持飞书。我们自行实现了飞书 channel（`src/channels/feishu.ts`），基于 `lark-cli` WebSocket 长连接监听飞书事件。

### 实现原理

```
registerChannel('feishu', factory)  ← 启动时自注册
        ↓
FeishuChannel.connect()
        ↓
lark-cli event +subscribe --event-types im.message.receive_v1 --compact
        ↓
stdout → NDJSON 事件流 → processEvent() → onMessage()
```

支持 text / image / file / post 四种消息类型。

### 飞书应用配置

需要在[飞书开放平台](https://open.feishu.cn)创建应用：

| 步骤 | 操作 |
|------|------|
| 创建应用 | 开放平台 → 创建企业自建应用 |
| 添加能力 | 添加「机器人」能力 |
| 权限申请 | `im:message`、`im:message:send_as_bot`、`im:resource`、`im:chat` |
| 事件订阅 | WebSocket 模式，订阅 `im.message.receive_v1` |
| CLI 登录 | `lark-cli auth login --app-id <id> --app-secret <secret>` |
| 环境变量 | `.env` 中设置 `FEISHU_LARK_CLI_PROFILE=nanoclaw` |

### 本项目的飞书配置

| 组件 | App ID | 用途 |
|------|--------|------|
| User Agent Bot | `cli_a9609c066a38dcd4` (useragent) | 发送模拟用户消息 |
| NanoClaw Bot | `cli_a960aadc42399cba` (nanoclaw) | NanoClaw 服务 + 发送 Andy 回复 |
| 飞书群 | `oc_c21ae31188a9d673368dab1c1f96ac4d` | 对话展示群 |

> **注意**：飞书展示模式下需先停止 NanoClaw 主服务（`launchctl unload ~/Library/LaunchAgents/com.nanoclaw.plist`），否则转发到飞书的消息会被 NanoClaw 服务再次处理，造成重复回复。

---

## 完整参数

```
positional arguments:
  seed                    初始消息（角色扮演模式下为对话场景，可省略）

options:
  -f, --file              初始附加文件（可多次使用）
  --file-pool DIR         文件池目录（LLM 自动选择文件发送）
  --persona NAME          人设：casual/boss/dev/verbose 或 .md 文件路径
  --role TEXT             角色描述文本或 .md 文件路径
  --role-from-feishu      [飞书模式] 启动后从飞书接收角色设定
  --auto                  全自动模式，不手动确认每条消息
  --max-turns N           最大对话轮数（默认 20）
  --timeout N             等待回复超时秒数（默认 300）
  --feishu                飞书展示模式（claw CLI 交互 + 飞书转发）
  --feishu-chat-id ID     飞书群 chat_id（默认使用内置群）
  --observe               [claw 模式] 同时转发对话到飞书群观察
```
