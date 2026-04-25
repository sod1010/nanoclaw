# User Agent — 模拟真人用户与 NanoClaw 自动交互

## 项目目标

创建一个模拟真实用户的 Agent（User Agent），通过输入 seed query 作为初始话题，自动与 NanoClaw (Andy) 进行多轮对话。核心要求：

1. **语言像人** — 对话风格、节奏、口语习惯接近真实用户
2. **支持文件传输** — 双向：User Agent 可发送文件，也能接收 NanoClaw 创建的文件

---

## 1. 飞书 Channel 接入

NanoClaw 原生支持 WhatsApp、Telegram、Slack、Discord 等 channel，**但不支持飞书**。我们自行实现了飞书 channel（`src/channels/feishu.ts`），使 NanoClaw 能通过飞书群接收消息并回复。

### 1.1 飞书 Channel 实现原理

飞书 channel 基于 `lark-cli`（飞书官方 CLI 工具）实现，遵循 NanoClaw 的 channel 自注册机制：

```
src/channels/feishu.ts
        │
        ▼
registerChannel('feishu', factory)    ← NanoClaw 启动时自动注册
        │
        ▼
FeishuChannel.connect()
        │
        ▼
lark-cli event +subscribe            ← WebSocket 长连接监听飞书事件
  --event-types im.message.receive_v1
  --compact --quiet --force
        │
        ▼
stdout → NDJSON 事件流 → processEvent() → onMessage()
```


**消息类型支持**：

- `text` — 文本消息，直接提取 content
- `image` — 图片消息，解析 `[Image: img_key]`（compact 格式）或 `{"image_key":"..."}` JSON，下载后作为附件交给 agent
- `file` — 文件消息，解析 `[File: file_key (filename)]`（compact 格式）或 JSON，下载后交给 agent
- `post` — 富文本消息，提取标题和文本内容

### 1.2 飞书应用配置

需要在[飞书开放平台](https://open.feishu.cn)创建应用并配置：

| 步骤 | 操作 |
|------|------|
| 创建应用 | 开放平台 → 创建企业自建应用 |
| 添加能力 | 添加「机器人」能力 |
| 权限申请 | `im:message`、`im:message:send_as_bot`、`im:resource`、`im:chat` |
| 事件订阅 | 使用 WebSocket 模式，订阅 `im.message.receive_v1` |
| CLI 登录 | `lark-cli auth login --app-id <id> --app-secret <secret>` |
| 环境变量 | `.env` 中设置 `FEISHU_LARK_CLI_PROFILE=nanoclaw` |

### 1.3 本项目的飞书配置

本项目使用两个飞书 Bot 分别代表交互双方：

| 组件 | App ID | 用途 |
|------|--------|------|
| User Agent Bot | `cli_a9609c066a38dcd4` (useragent) | 发送模拟用户消息 |
| NanoClaw Bot | `cli_a960aadc42399cba` (nanoclaw) | NanoClaw 服务 + 发送 Andy 回复 |
| 飞书群 | `oc_c21ae31188a9d673368dab1c1f96ac4d` | 对话展示群 |

### 1.4 飞书作为展示平台

选择飞书群作为 User Agent 项目的交互与展示平台。用户可以在飞书群中：

- **输入角色设定** — 定义 User Agent 的人设和对话场景
- **实时观看对话** — User Agent（useragent bot）和 NanoClaw（nanoclaw bot）各自发消息，模拟真实双方对话
- **查看文件传输** — 双方传输的文件直接在飞书群中展示

### 飞书角色输入流程

```
用户在飞书发送角色设定
        │
        ▼
┌─────────────────────────────┐
│ 格式 1（结构化）：           │
│   角色：一个人工智能工程师    │
│   场景：查询强化学习知识      │
│                             │
│ 格式 2（自由描述）：         │
│   焦急的外卖客户李明...      │
└─────────────────────────────┘
        │
        ▼
  user-agent.py 解析 → 注入 system prompt → 开始对话
```

启动命令：

```bash
python3 scripts/user-agent.py --feishu --role-from-feishu --auto --max-turns 5
```

---

## 2. 交互架构：claw CLI 桥接

### 问题：飞书 Bot 之间无法互相接收消息

飞书平台限制：**Bot 发出的消息只有人类用户能接收，其他 Bot 无法收到**。这意味着 User Agent Bot 和 NanoClaw Bot 无法在飞书群中直接对话。

### 解决方案：claw CLI 作为交互桥梁

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

**工作流程**：

1. User Agent LLM 生成消息
2. 通过 `claw CLI` 直接调用 NanoClaw 容器，获取回复
3. 将双方消息分别通过对应 Bot 转发到飞书群展示

> **注意**：飞书展示模式下需先停止 NanoClaw 主服务（`launchctl unload`），否则转发到飞书的消息会被 NanoClaw 服务再次处理，造成重复回复。

---

## 3. NanoClaw 配置

### API 配置

NanoClaw 和 User Agent 均通过 `.env` 文件配置 API 访问：

| 配置项 | 说明 | 示例值 |
|--------|------|--------|
| `ANTHROPIC_BASE_URL` | API 网关地址 | `https://aigc.sankuai.com/v1/anthropic` |
| `ANTHROPIC_AUTH_TOKEN` | API 认证 Token | Bearer token |
| `ANTHROPIC_MODEL` | 模型标识 | `aws.claude-opus-4.6-b` |

API 调用方式：

```python
# User Agent 侧：直接调用 Claude Messages API
url = f"{ANTHROPIC_BASE_URL}/v1/messages"
payload = {
    "model": ANTHROPIC_MODEL,
    "max_tokens": 1024,
    "system": system_prompt,    # 包含人设 + 角色扮演指令
    "messages": conversation,   # 多轮对话历史
}
# Headers: Authorization: Bearer {token}, anthropic-version: 2023-06-01
```

```bash
# NanoClaw 侧：通过 claw CLI 启动容器
python3 scripts/claw "用户消息内容" --timeout 300
# claw 内部启动 Docker 容器运行 NanoClaw agent-runner
```

### 模型可替换性

User Agent 的 LLM 调用（`call_claude()`）使用标准 Anthropic Messages API 格式。可替换为：

- **开源模型**（通过兼容 API 网关）：DeepSeek、Qwen 等
- **HER 微调模型**：使用一些role playing论文在角色扮演数据上微调的模型，节省成本，比如：
HER: https://huggingface.co/ChengyuDu0123/HER-32B
coser: https://huggingface.co/Neph0s/CoSER-Llama-3.1-70B


只需修改 `.env` 中的三个配置项即可切换模型。

---

## 4. user agent人设配置：HER 分层架构

### HER（Hierarchical Emotion Reasoning）论文核心思想

HER 论文提出分层推理架构，将角色模拟从"模仿语气"提升到"模拟认知过程"。每次回复经过三层处理：

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

- **System Thinking**：第三人称分析角色应如何回应当前情境，考虑人设层级优先级
- **Role Thinking**：角色第一人称内心独白，模拟真实的情绪和思考过程
- **Role Response**：最终输出的动作描写 + 台词，用户可见的部分

### NanoClaw Roleplay Skill

NanoClaw 也可以通过 container skill 实现 HER 风格的角色扮演。该 skill 位于 `container/skills/roleplay/`，结构如下：

```
container/skills/roleplay/
├── SKILL.md              # Skill 定义：激活方式、三层回复规则、标签格式
├── persona-template.md   # 人设模板：Layer 0-3 分层定义
└── examples.md           # 完整示例
```

仿照 著名的同事.skill `container/skills/` 下的结构，结合 HER 论文思想构建：

- **SKILL.md** 定义了激活触发（`/roleplay`）、三层输出格式（`<internal>` → `<role_thinking>` → `<role_action>` + 台词）、模式切换（think/clean）
- **persona-template.md** 提供分层人设模板：Layer 0 核心人格（绝对遵守）→ Layer 1 表达风格 → Layer 2 思维模式 → Layer 3 关系处理
- 角色定义写入对应 group 的 `CLAUDE.md`，NanoClaw 自动加载

### User Agent 人设配置

User Agent 的人设支持多种配置方式：

**1. 内置人设**（`--persona`）：

| 人设 | 风格 | 适用场景 |
|------|------|---------|
| `casual`（默认） | 口语化普通用户 | 日常功能测试 |
| `boss` | 急躁老板，话少催进度 | 压力测试 |
| `dev` | 程序员，关注技术细节 | 技术问答测试 |
| `verbose` | 话多，喜欢解释背景 | 长输入测试 |

**2. 自定义角色**（`--role`）：

```bash
# CLI 直接传角色描述
python3 scripts/user-agent.py "讨论技术方案" \
  --role "焦急的外卖客户李明，30岁上班族" --auto

# 从 .md 文件加载角色（可使用 persona-template.md 格式）
python3 scripts/user-agent.py "讨论技术方案" --role character.md --auto
```

**3. 从飞书实时输入**（`--role-from-feishu`）：

```bash
python3 scripts/user-agent.py --feishu --role-from-feishu --auto
```

运行后会在飞书群发送提示，等待人类用户输入角色设定（格式：`角色：xxx / 场景：xxx`）。适合需要实时调整角色的场景。

---

## 5. 文件传输配置

### 整体流程

```
User Agent                    NanoClaw 容器                飞书群
    │                              │                         │
    │  ── 文件池选择文件 ──→        │                         │
    │     shutil.copy2 →           │                         │
    │     groups/main/uploads/     │                         │
    │                              │                         │
    │  ── claw CLI 发送消息 ──→     │                         │
    │     "[用户上传了文件到        │                         │
    │      uploads/: rssm.py]"     │                         │
    │                              │                         │
    │                    容器读取/修改文件                     │
    │                    写回 uploads/                        │
    │                              │                         │
    │  ←── claw CLI 返回回复 ───    │                         │
    │                              │                         │
    │  ── scan_new_files() ──→     │                         │
    │     检测新建/修改的文件        │                         │
    │                              │                         │
    │  ── UA bot 转发用户消息 ──────────────────→  useragent  │
    │  ── UA bot 转发用户文件 ──────────────────→  [文件]     │
    │  ── NC bot 转发 Andy 回复 ────────────────→  nanoclaw   │
    │  ── NC bot 转发新文件 ────────────────────→  [文件]     │
```

### 发送文件（User Agent → NanoClaw）

**文件池模式**：指定一个目录，LLM 根据对话上下文自动选择要发送的文件。

```bash
python3 scripts/user-agent.py "帮我看看代码" --file-pool ./my-docs/ --auto
```

实现机制：
1. 扫描 `--file-pool` 目录，将文件名列表注入 system prompt
2. LLM 在 JSON 的 `files` 数组中指定要发送的文件名
3. `claw_send()` 将文件 `shutil.copy2` 到 `groups/main/uploads/`
4. 消息中追加 `[用户上传了文件到 uploads/: filename]` 提示

**直接附件模式**：

```bash
python3 scripts/user-agent.py "分析这个报告" -f report.csv -f data.json --auto
```

### 接收文件（NanoClaw → User Agent）

NanoClaw 容器中创建或修改的文件通过 before/after 快照机制检测：

```python
# 1. 交互前快照
before_snap = snapshot_dir(group_dir)  # {相对路径: mtime}

# 2. claw CLI 交互（NanoClaw 可能创建/修改文件）

# 3. 交互后对比
all_new = scan_new_files(group_dir, before_snap)

# 4. 排除 User Agent 自己复制的未修改文件（按文件名 + 大小过滤）
new_files = [f for f in all_new if not (f.name in sent_files 
             and f.stat().st_size == sent_files[f.name])]
```

### 飞书文件转发

`feishu_send_file()` 处理 lark-cli 的路径限制：

```python
# lark-cli 要求相对路径 — 使用 cwd + ./filename
result = subprocess.run(
    ["lark-cli", "im", "+messages-send", "--as", "bot",
     "--profile", profile, "--chat-id", chat_id, flag, f"./{fp.name}"],
    cwd=str(fp.parent),  # 设置工作目录为文件所在目录
)
```

自动识别文件类型：图片（`.png/.jpg/.gif` 等）使用 `--image` 参数，其他文件使用 `--file` 参数。

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

## 复用 / 分发

将以下文件提供给使用者：

```
scripts/user-agent.py         # 主脚本
scripts/user-agent.README.md  # 本文档（技术说明）
```

使用者环境需要：

| 依赖 | 用途 | 必须 |
|------|------|------|
| NanoClaw + claw CLI | 容器交互 | 是 |
| `.env` API 配置 | LLM 调用 | 是 |
| lark-cli + 飞书 Bot | 飞书展示模式 | 仅飞书模式 |
| Docker / Colima | 容器运行时 | 是 |
