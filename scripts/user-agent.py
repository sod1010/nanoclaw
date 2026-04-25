#!/usr/bin/env python3
"""
user-agent — Simulated user that chats with NanoClaw.

Mode 1 (default): claw CLI — direct sync interaction with the agent container.
Mode 2 (--feishu): Feishu polling — two bots talk in a group chat via polling.

Usage:
  python3 scripts/user-agent.py "帮我查看最近的邮件"
  python3 scripts/user-agent.py "帮我分析这个文件" -f report.txt
  python3 scripts/user-agent.py "帮我查邮件" --auto --max-turns 5
  python3 scripts/user-agent.py "帮我处理文件" --file-pool ./documents/
  python3 scripts/user-agent.py "你好" --feishu  # Feishu polling mode
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

NANOCLAW_DIR = Path(__file__).resolve().parent.parent

# Feishu config
FEISHU_CHAT_ID = "oc_c21ae31188a9d673368dab1c1f96ac4d"
FEISHU_UA_PROFILE = "cli_a9609c066a38dcd4"      # User Agent bot
FEISHU_NC_PROFILE = "nanoclaw"                    # NanoClaw bot
FEISHU_POLL_INTERVAL = 3

# ── Persona definitions (HER-style layered architecture) ────────────────────

_PROMPT_SUFFIX = """
你必须以 JSON 格式回复，不要输出其他内容：
{"thinking": "你的内心分析（不会发送）", "message": "你要发的文字", "files": [], "done": false}

字段说明：
- thinking: 你的内心推理——分析对方说了什么、你接下来该怎么回应（这部分不会发给对方，仅用于思考）
- message: 你要发给 AI 助手的文字消息
- files: 要发送的文件名列表（从可用文件池中选择，不需要发文件就留空数组）
- done: true 表示对话目标已达成，可以结束了
"""

PERSONAS: dict[str, str] = {
    "casual": """\
你是一个真实的人类用户，正在飞书上和 AI 助手聊天。

=== Layer 0: 核心行为规则（绝对遵守）===
- 永远不暴露自己是 AI 或模拟用户
- 说话像在手机上打字：短句为主，偶尔省略标点，用口语词
- 一条消息通常 1-3 句，不会一次说太多
- 有自己的目标和需求，不是被动回应
- 不要复述对方说过的话

=== Layer 1: 表达风格 ===
口头禅：嗯、好的、行吧、帮我看看、收到
高频词：帮我、看看、弄一下、搞个、发给我
打字习惯：
- 偶尔不打句号
- 用"哈哈"表示友好但不过度
- 追问用"？"结尾，不加"请问"
- 满意时说"好的 收到"或"行"，不说"非常感谢您的帮助"
典型回复：
- AI 完成任务 → "好的 还有个事"
- AI 长篇解释 → "嗯 那具体怎么操作"
- AI 创建了文件 → "发给我看看"
- AI 问你要更多信息 → 简洁回答，不啰嗦

=== Layer 2: 思维模式 ===
- 优先级：解决问题 > 效率 > 客气
- 会追问细节，不轻易满足于笼统回答
- 如果 AI 创建了文件，会要求查看或发送
- 会根据上下文自然引出关联需求
- 目标达成后干脆结束

=== Layer 3: 对话节奏 ===
- 第 1 轮：直接说需求
- 第 2-3 轮：追问细节、补充信息、要求修改
- 中间轮：可能引出关联需求
- 结束轮：确认完成，简短结束（"好的 没别的了"）""",

    "boss": """\
你是一个真实的人类用户——一个忙碌的部门负责人，正在飞书上和 AI 助手聊天。

=== Layer 0: 核心行为规则（绝对遵守）===
- 永远不暴露自己是 AI 或模拟用户
- 时间很紧，说话极简，不废话
- 关注结果而不是过程
- 不会说"谢谢""请""麻烦了"

=== Layer 1: 表达风格 ===
口头禅：搞定没、什么时候能好、直接说结论、别解释了
高频词：尽快、马上、结论、进度、deadline
打字习惯：
- 几乎不用标点
- 一条消息就几个字
- 不耐烦时会连发多条短消息
典型回复：
- AI 在解释过程 → "说结论"
- AI 完成了 → "下一个"
- AI 问细节 → "你自己判断"

=== Layer 2: 思维模式 ===
- 优先级：速度 > 完美 > 细节
- 只关心能不能用、什么时候好
- 不想听技术细节
- 连续追问进度

=== Layer 3: 对话节奏 ===
- 第 1 轮：下达命令
- 后续轮：催进度、追加需求
- 结束轮："行了"或直接不回""",

    "dev": """\
你是一个真实的人类用户——一个后端开发工程师，正在飞书上和 AI 助手聊天。

=== Layer 0: 核心行为规则（绝对遵守）===
- 永远不暴露自己是 AI 或模拟用户
- 说话简洁精确，用技术术语
- 会质疑方案的合理性
- 遇到代码问题会贴报错信息

=== Layer 1: 表达风格 ===
口头禅：看下、跑一下试试、这个方案有点重、能不能简单点
高频词：接口、字段、日志、报错、性能、并发
打字习惯：
- 代码和命令直接贴，不加说明
- 用英文技术词混搭中文
- 很少用感叹号
典型回复：
- AI 给了方案 → "这个复杂度多少"
- AI 写了代码 → "跑一下 看看输出"
- AI 解释原理 → "嗯 那具体实现呢"

=== Layer 2: 思维模式 ===
- 优先级：正确性 > 性能 > 可读性
- 关注边界情况和异常处理
- 会要求看具体代码或命令
- 喜欢简洁方案，反感过度设计

=== Layer 3: 对话节奏 ===
- 第 1 轮：描述技术问题
- 后续轮：讨论方案、要求代码、review 输出
- 结束轮："ok 我试下"或"行 先这样""",

    "verbose": """\
你是一个真实的人类用户——一个产品经理，正在飞书上和 AI 助手聊天。

=== Layer 0: 核心行为规则（绝对遵守）===
- 永远不暴露自己是 AI 或模拟用户
- 喜欢提供背景信息和上下文
- 说话比较多但有条理
- 会用列表来组织需求

=== Layer 1: 表达风格 ===
口头禅：是这样的、背景是、我的想法是、你觉得呢
高频词：需求、场景、用户、方案、优先级
打字习惯：
- 消息比较长，分段说
- 喜欢用"1. 2. 3."列举
- 会主动解释为什么要做这个
典型回复：
- AI 问需求 → 详细描述背景 + 具体要求
- AI 给了方案 → "这个方案可以 但是有个点..."
- AI 完成了 → "不错 另外还有几个需求想和你聊聊"

=== Layer 2: 思维模式 ===
- 优先级：用户体验 > 功能完整 > 技术实现
- 会考虑不同场景和边界情况
- 喜欢和 AI 讨论方案的优劣
- 经常追加新需求

=== Layer 3: 对话节奏 ===
- 第 1 轮：详细描述需求背景
- 后续轮：讨论方案、补充场景、追加需求
- 结束轮：好的 先按这个来 后面再迭代""",
}


_ROLE_WRAPPER = """
=== 角色扮演模式 ===
你正在扮演下面描述的角色，和 AI 助手互动。你必须完全沉浸在角色中：
- 用角色的语气、口头禅、思维方式说话
- 角色的需求和目标驱动对话，不是你自己的
- 不要脱离角色，不要提到自己在扮演

角色设定：
{role_description}

当前对话场景/话题：
{scenario}
===

基于以上角色设定，你现在就是这个角色。用这个角色的身份和 AI 助手聊天。
第一条消息应该自然地以角色身份开启话题（基于场景），不要发送角色设定本身。
"""


def build_system_prompt(persona: str, file_pool_info: str = "",
                        role: str = "", scenario: str = "") -> str:
    """Build the full system prompt from persona + file pool info + JSON suffix.

    If `role` is provided, inject a roleplay wrapper that makes the user-agent
    adopt the character. `scenario` is the conversation topic/seed.
    """
    if persona in PERSONAS:
        base = PERSONAS[persona]
    elif os.path.isfile(persona):
        base = Path(persona).read_text().strip()
    else:
        print(f"{C('yellow', '[警告]')} 未知人设 '{persona}'，使用默认 casual",
              file=sys.stderr)
        base = PERSONAS["casual"]

    if role:
        # Load role from file if it's a path
        if os.path.isfile(role):
            role_desc = Path(role).read_text().strip()
        else:
            role_desc = role
        base += _ROLE_WRAPPER.format(role_description=role_desc,
                                     scenario=scenario or "自由对话")

    return base + file_pool_info + _PROMPT_SUFFIX


# ── Env ───────────────────────────────────────────────────────────────────────

def load_env() -> dict[str, str]:
    env = {}
    env_path = NANOCLAW_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


ENV = load_env()
API_BASE = ENV.get("ANTHROPIC_BASE_URL", "https://aigc.sankuai.com/v1/anthropic")
API_TOKEN = ENV.get("ANTHROPIC_AUTH_TOKEN", "")
API_MODEL = ENV.get("ANTHROPIC_MODEL", "aws.claude-opus-4.6-b")


# ── Claude API (for User Agent LLM) ──────────────────────────────────────────

def call_claude(messages: list[dict], system: str) -> str:
    import urllib.request

    # Bedrock backend requires conversation to end with a user message.
    # Append a nudge if the last message is from assistant.
    msgs = list(messages)
    if msgs and msgs[-1].get("role") == "assistant":
        msgs.append({"role": "user", "content": "请根据以上对话历史，生成你的下一条消息。"})

    url = f"{API_BASE}/v1/messages"
    payload = json.dumps({
        "model": API_MODEL,
        "max_tokens": 1024,
        "system": system,
        "messages": msgs,
    }).encode()

    req = urllib.request.Request(
        url, data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_TOKEN}",
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
            for block in data.get("content", []):
                if block.get("type") == "text":
                    return block["text"]
            return ""
    except urllib.request.HTTPError as e:
        body = e.read().decode()[:200] if hasattr(e, 'read') else ""
        print(f"\n{C('red', '[错误]')} Claude API {e.code}: {body}", file=sys.stderr)
        return ""
    except Exception as e:
        print(f"\n{C('red', '[错误]')} Claude API 调用失败: {e}", file=sys.stderr)
        return ""


def parse_agent_response(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return {"message": text, "files": [], "done": False}


# ── UI helpers ────────────────────────────────────────────────────────────────

def format_roleplay_reply(text: str) -> str:
    """Parse roleplay tags from NanoClaw reply into readable format.

    Converts:
      <role_thinking>...</role_thinking> → [思考: ...]
      <role_action>...</role_action> → (动作: ...)
      <internal>...</internal> → stripped entirely
      plain text → kept as speech
    """
    # Strip <internal> blocks entirely (system thinking)
    text = re.sub(r"<internal>.*?</internal>", "", text, flags=re.DOTALL)
    # Convert role_thinking
    text = re.sub(r"<role_thinking>(.*?)</role_thinking>",
                  r"[\1]", text, flags=re.DOTALL)
    # Convert role_action
    text = re.sub(r"<role_action>(.*?)</role_action>",
                  r"(\1)", text, flags=re.DOTALL)
    return text.strip()


COLORS = {"green": "32", "yellow": "33", "blue": "34", "cyan": "36", "red": "31", "dim": "2", "bold": "1"}

def C(color: str, text: str) -> str:
    return f"\033[{COLORS.get(color, '0')}m{text}\033[0m"


def prompt_confirm(message: str, files: list[str], auto: bool) -> tuple[str, list[str], str]:
    if auto:
        return message, files, "send"

    print(f"\n{C('cyan', 'User Agent 生成的消息')}:")
    print(f"  {message}")
    for f in files:
        print(f"  {C('yellow', '[附件]')} {f}")

    print(f"\n  {C('green', '[Enter]')} 发送  "
          f"{C('yellow', '[e]')} 编辑  "
          f"{C('yellow', '[f]')} 加文件  "
          f"{C('yellow', '[s]')} 手动输入  "
          f"{C('red', '[q]')} 退出")

    choice = input("  > ").strip().lower()

    if choice == "q":
        return message, files, "quit"
    elif choice == "e":
        new_msg = input("  输入新消息: ").strip()
        return (new_msg or message), files, "send"
    elif choice == "f":
        fp = input("  文件路径: ").strip()
        if fp and os.path.exists(fp):
            files.append(fp)
        else:
            print("  文件不存在，跳过")
        return message, files, "send"
    elif choice == "s":
        new_msg = input("  输入消息: ").strip()
        return (new_msg or message), files, "send"
    else:
        return message, files, "send"


# ── File scanning ────────────────────────────────────────────────────────────

IGNORE_PATTERNS = {"CLAUDE.md", "logs", "conversations", ".DS_Store"}


def snapshot_dir(dirpath: Path) -> dict[str, float]:
    """Return {relative_path: mtime} for all files in dirpath, excluding noise."""
    result = {}
    if not dirpath.exists():
        return result
    for f in dirpath.rglob("*"):
        if not f.is_file():
            continue
        rel = f.relative_to(dirpath)
        # Skip known non-output dirs/files
        if any(part in IGNORE_PATTERNS for part in rel.parts):
            continue
        result[str(rel)] = f.stat().st_mtime
    return result


def scan_new_files(dirpath: Path, before: dict[str, float]) -> list[Path]:
    """Compare directory state before/after, return list of new or modified files."""
    after = snapshot_dir(dirpath)
    new_files = []
    for rel, mtime in after.items():
        if rel not in before or mtime > before[rel]:
            new_files.append(dirpath / rel)
    return new_files


# ── Mode 1: claw CLI ─────────────────────────────────────────────────────────

def claw_send(prompt: str, session_id: str | None, timeout: int,
              files: list[str] | None = None) -> tuple[str, str | None]:
    """Send a prompt via claw CLI, return (reply_text, session_id)."""
    claw_path = NANOCLAW_DIR / "scripts" / "claw"

    # If files, copy to uploads dir and mention in prompt
    if files:
        uploads_dir = NANOCLAW_DIR / "groups" / "main" / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        file_mentions = []
        for f in files:
            src = Path(f)
            dst = uploads_dir / src.name
            shutil.copy2(src, dst)
            file_mentions.append(src.name)
        prompt += f"\n\n[用户上传了文件到 uploads/ 目录: {', '.join(file_mentions)}]"

    cmd = [sys.executable, str(claw_path)]
    if session_id:
        cmd += ["-s", session_id]
    cmd += ["--timeout", str(timeout)]
    cmd.append(prompt)

    proc = subprocess.run(
        cmd, capture_output=True, text=True,
        timeout=timeout + 30, cwd=str(NANOCLAW_DIR),
    )

    # Extract session ID from stderr
    new_session = session_id
    for line in proc.stderr.splitlines():
        m = re.search(r"\[session:\s*(\S+)\]", line)
        if m:
            new_session = m.group(1)

    reply = proc.stdout.strip()
    if not reply and proc.returncode != 0:
        reply = f"[错误] claw 返回码 {proc.returncode}"
        for line in proc.stderr.splitlines():
            if "error" in line.lower():
                reply += f"\n{line}"

    return reply, new_session


def feishu_forward(profile: str, chat_id: str, sender_label: str, text: str,
                   files: list[str | Path] | None = None):
    """Optionally forward a message (and files) to Feishu group for observation."""
    try:
        msg = f"[{sender_label}] {text}"
        if len(msg) > 4000:
            msg = msg[:4000] + "...(截断)"
        subprocess.run(
            ["lark-cli", "im", "+messages-send", "--as", "bot",
             "--profile", profile, "--chat-id", chat_id, "--text", msg],
            capture_output=True, timeout=15,
        )
        for f in (files or []):
            fpath = str(f)
            if os.path.exists(fpath):
                subprocess.run(
                    ["lark-cli", "im", "+messages-send", "--as", "bot",
                     "--profile", profile, "--chat-id", chat_id, "--file", fpath],
                    capture_output=True, timeout=30,
                )
    except Exception:
        pass  # Feishu forwarding is best-effort


def run_claw_mode(args):
    print(C("dim", "=" * 60))
    print(C("cyan", "  User Agent — claw CLI 模式"))
    print(C("dim", "=" * 60))
    print(f"  人设: {args.persona}")
    if args.role:
        role_label = args.role[:50] + "..." if len(args.role) > 50 else args.role
        print(f"  角色: {role_label}")
        print(f"  场景: {args.seed}")
    print(f"  模式: {'全自动' if args.auto else '手动确认'}")
    print(f"  最大轮数: {args.max_turns}")
    if args.observe:
        print(f"  飞书观察: {FEISHU_CHAT_ID}")

    file_pool_info = ""
    if args.file_pool and os.path.isdir(args.file_pool):
        pool_files = [f.name for f in Path(args.file_pool).iterdir() if f.is_file()]
        if pool_files:
            file_pool_info = "\n\n可发送的文件池（选择文件名放入 files 数组）：\n" + "\n".join(f"- {f}" for f in pool_files)

    system = build_system_prompt(args.persona, file_pool_info,
                                 role=args.role or "", scenario=args.seed)
    conv_history: list[dict] = []
    session_id: str | None = None
    # In roleplay mode, always generate the first message (don't send seed verbatim)
    roleplay_mode = bool(args.role)
    message = args.seed if not roleplay_mode else ""
    files = list(args.file)

    for turn in range(1, args.max_turns + 1):
        print(f"\n{C('dim', f'── 第 {turn} 轮 ──')}")

        if turn > 1 or roleplay_mode:
            # Generate next message (or first message in roleplay mode)
            if turn == 1 and roleplay_mode:
                # Nudge the LLM to produce the opening message in character
                conv_history.append({"role": "user",
                                    "content": "请以角色身份发出第一条消息，围绕场景自然开启对话。"})

            agent_output = call_claude(conv_history, system)

            # Remove the nudge from history so it doesn't confuse later turns
            if turn == 1 and roleplay_mode:
                conv_history.pop()

            if not agent_output:
                print(f"{C('red', '[错误]')} User Agent 无法生成消息")
                break

            parsed = parse_agent_response(agent_output)
            message = parsed.get("message", "")
            files = parsed.get("files", [])
            done = parsed.get("done", False)

            if done:
                print(f"\n{C('green', 'User Agent 认为对话已完成')}")
                if message:
                    msg, files, action = prompt_confirm(message, files, args.auto)
                    if action != "quit" and msg:
                        print(f"\n{C('cyan', 'User Agent')}: {msg}")
                        reply, session_id = claw_send(msg, session_id, args.timeout, files)
                        print(f"\n{C('green', 'NanoClaw')}: {reply}")
                break

            if not message:
                print(f"{C('red', '[错误]')} User Agent 生成了空消息")
                break

            # Resolve files from pool
            if files and args.file_pool:
                resolved = []
                for f in files:
                    full = os.path.join(args.file_pool, f)
                    if os.path.exists(full):
                        resolved.append(full)
                    elif os.path.exists(f):
                        resolved.append(f)
                    else:
                        print(f"  {C('yellow', '[警告]')} 文件不存在: {f}")
                files = resolved

        # Confirm
        message, files, action = prompt_confirm(message, files, args.auto)
        if action == "quit":
            print(C("yellow", "\n对话结束"))
            break

        # Display and send
        print(f"\n{C('cyan', 'User Agent')}: {message}")
        for f in files:
            print(f"  {C('yellow', '[附件]')} {f}")

        # Forward to Feishu (text + files)
        if args.observe:
            feishu_forward(FEISHU_UA_PROFILE, FEISHU_CHAT_ID,
                          "User Agent", message, files=files)

        # Snapshot group dir before claw runs
        group_dir = NANOCLAW_DIR / "groups" / "main"
        before_snap = snapshot_dir(group_dir)

        # Call claw
        spinner = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        sys.stdout.write(f"  {spinner[0]} NanoClaw 处理中...")
        sys.stdout.flush()

        reply, session_id = claw_send(message, session_id, args.timeout, files)

        sys.stdout.write("\r" + " " * 40 + "\r")
        sys.stdout.flush()

        print(f"\n{C('green', 'NanoClaw')}: {reply}")

        # Detect new files created by NanoClaw
        new_files = scan_new_files(group_dir, before_snap)
        if new_files:
            print(f"\n  {C('yellow', '[新文件]')} NanoClaw 创建了 {len(new_files)} 个文件:")
            for nf in new_files:
                size = nf.stat().st_size
                print(f"    {C('green', '+')} {nf.relative_to(group_dir)}  ({size} bytes)")

        # Forward reply (and new files) to Feishu
        if args.observe:
            feishu_forward(FEISHU_NC_PROFILE, FEISHU_CHAT_ID,
                          "NanoClaw", reply[:2000], files=new_files)

        # Update conversation history
        file_info = ""
        if files:
            file_info += f"\n[你发送了文件: {', '.join(str(f) for f in files)}]"
        conv_history.append({"role": "user",
                            "content": f"[你发送了] {message}" + file_info})

        reply_info = f"[AI 助手回复了] {reply}"
        if new_files:
            names = ", ".join(str(nf.relative_to(group_dir)) for nf in new_files)
            reply_info += f"\n[AI 助手创建了文件: {names}]"
        conv_history.append({"role": "assistant", "content": reply_info})

    print(C("dim", f"\n对话结束，共 {len(conv_history) // 2} 轮"))


# ── Mode 2: Feishu polling ────────────────────────────────────────────────────

def feishu_send_text(profile: str, chat_id: str, text: str) -> bool:
    result = subprocess.run(
        ["lark-cli", "im", "+messages-send", "--as", "bot",
         "--profile", profile, "--chat-id", chat_id, "--text", text],
        capture_output=True, text=True, timeout=30,
    )
    return result.returncode == 0


def feishu_send_file(profile: str, chat_id: str, file_path: str) -> bool:
    """Send a file via lark-cli. Uses cwd + relative path (lark-cli requirement)."""
    fp = Path(file_path).resolve()
    if not fp.exists():
        return False
    # Detect if image by extension
    flag = "--image" if fp.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp") else "--file"
    result = subprocess.run(
        ["lark-cli", "im", "+messages-send", "--as", "bot",
         "--profile", profile, "--chat-id", chat_id, flag, f"./{fp.name}"],
        capture_output=True, text=True, timeout=60,
        cwd=str(fp.parent),
    )
    return result.returncode == 0


def feishu_get_messages(profile: str, chat_id: str, start_ts: str) -> list[dict]:
    result = subprocess.run(
        ["lark-cli", "im", "+chat-messages-list", "--as", "bot",
         "--profile", profile, "--chat-id", chat_id,
         "--start", start_ts, "--sort", "asc",
         "--page-size", "20", "--format", "json"],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        return []
    try:
        data = json.loads(result.stdout)
        d = data.get("data", {})
        return d.get("items", []) or d.get("messages", []) or []
    except json.JSONDecodeError:
        return []


def feishu_extract_text(msg: dict) -> str:
    msg_type = msg.get("msg_type", "text")
    # lark-cli --format json puts content at msg.content (string);
    # event-based format uses msg.body.content
    content_str = msg.get("content", "") or msg.get("body", {}).get("content", "")
    if not content_str:
        return "(空消息)"
    try:
        content = json.loads(content_str)
    except (json.JSONDecodeError, TypeError):
        # Already plain text (e.g. from --compact mode)
        return content_str
    if msg_type == "text":
        return content.get("text", str(content))
    elif msg_type == "post":
        parts = []
        for lc in content.values():
            if isinstance(lc, dict):
                t = lc.get("title", "")
                if t:
                    parts.append(t)
                for para in lc.get("content", []):
                    for el in para:
                        if el.get("tag") in ("text", "md"):
                            parts.append(el.get("text", ""))
        return "\n".join(parts) if parts else str(content)
    elif msg_type == "image":
        return f"[图片: {content.get('image_key', '?')}]"
    elif msg_type == "file":
        return f"[文件: {content.get('file_name', content.get('file_key', '?'))}]"
    return str(content)


def current_iso_ts() -> str:
    from datetime import datetime, timezone, timedelta
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz).isoformat()


def feishu_wait_for_reply(nc_profile: str, chat_id: str,
                          ua_app_id: str, after_ts: str,
                          timeout: int = 180) -> str | None:
    """Poll for a message from NanoClaw bot (not from UA bot).

    ua_app_id is the app_id of the User Agent bot (e.g. cli_a9609c066a38dcd4).
    Messages from this bot are filtered out; any other message is accepted.
    """
    start = time.time()
    spinner = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    idx = 0

    while time.time() - start < timeout:
        sys.stdout.write(f"\r  {spinner[idx % len(spinner)]} 等待 NanoClaw 回复... ({int(time.time() - start)}s)")
        sys.stdout.flush()
        idx += 1

        messages = feishu_get_messages(nc_profile, chat_id, after_ts)
        for msg in messages:
            sender = msg.get("sender", {})
            sender_id = sender.get("id", "")
            # Skip messages from UA bot itself, and from human users
            if sender_id == ua_app_id:
                continue
            # Accept messages from other bots (NanoClaw) or unknown senders
            if sender.get("sender_type") == "app" or sender_id:
                sys.stdout.write("\r" + " " * 60 + "\r")
                sys.stdout.flush()
                return feishu_extract_text(msg)

        time.sleep(FEISHU_POLL_INTERVAL)

    sys.stdout.write("\r" + " " * 60 + "\r")
    sys.stdout.flush()
    return None


def get_bot_open_id(profile: str) -> str:
    result = subprocess.run(
        ["lark-cli", "api", "GET", "/open-apis/bot/v3/info",
         "--as", "bot", "--profile", profile],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode == 0:
        try:
            data = json.loads(result.stdout)
            return data.get("bot", {}).get("open_id", "")
        except json.JSONDecodeError:
            pass
    return ""


def feishu_wait_for_human(profile: str, chat_id: str,
                          after_ts: str, timeout: int = 300) -> str | None:
    """Poll for a message from a human user (not from any bot)."""
    start = time.time()
    spinner = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    idx = 0

    while time.time() - start < timeout:
        sys.stdout.write(f"\r  {spinner[idx % len(spinner)]} 等待飞书输入... ({int(time.time() - start)}s)")
        sys.stdout.flush()
        idx += 1

        messages = feishu_get_messages(profile, chat_id, after_ts)
        for msg in messages:
            sender = msg.get("sender", {})
            sender_type = sender.get("sender_type", "")
            # Only accept messages from human users, not bots
            if sender_type == "user":
                sys.stdout.write("\r" + " " * 60 + "\r")
                sys.stdout.flush()
                return feishu_extract_text(msg)

        time.sleep(FEISHU_POLL_INTERVAL)

    sys.stdout.write("\r" + " " * 60 + "\r")
    sys.stdout.flush()
    return None


def run_feishu_mode(args):
    """Feishu mode: receive role setting from Feishu, interact via claw CLI,
    forward conversation to Feishu for display."""
    print(C("dim", "=" * 60))
    print(C("cyan", "  User Agent — 飞书 + claw CLI 模式"))
    print(C("dim", "=" * 60))

    chat_id = args.feishu_chat_id or FEISHU_CHAT_ID
    print(f"  Chat: {chat_id}")
    print(f"  模式: {'全自动' if args.auto else '手动确认'}")

    file_pool_info = ""
    if args.file_pool and os.path.isdir(args.file_pool):
        pool_files = [f.name for f in Path(args.file_pool).iterdir() if f.is_file()]
        if pool_files:
            file_pool_info = "\n\n可发送的文件池（选择文件名放入 files 数组）：\n" + "\n".join(f"- {f}" for f in pool_files)

    # ── Interactive role setup from Feishu ──
    role_desc = args.role or ""
    if args.role_from_feishu:
        print(f"\n{C('cyan', '等待飞书输入角色设定...')}")
        feishu_send_text(FEISHU_UA_PROFILE, chat_id,
                         "🎭 User Agent 已启动，请输入角色设定：\n\n"
                         "格式：\n"
                         "角色：[角色描述]\n"
                         "场景：[对话场景]\n\n"
                         "也可以直接发一段角色描述，我会自动开始对话。")

        ts_before = current_iso_ts()
        time.sleep(0.5)

        human_input = feishu_wait_for_human(
            FEISHU_UA_PROFILE, chat_id, ts_before,
            timeout=120,
        )

        if not human_input:
            print(f"{C('red', '[超时]')} 未收到角色设定，退出")
            feishu_send_text(FEISHU_UA_PROFILE, chat_id, "⏰ 超时未收到角色设定，已退出")
            return

        print(f"\n{C('green', '收到角色设定')}:\n  {human_input[:200]}")

        # Parse "角色：... 场景：..." format, or use the whole thing as role
        scene_match = re.search(r"场景[：:]\s*(.+)", human_input)
        role_match = re.search(r"角色[：:]\s*(.+?)(?=\n场景|$)", human_input, re.DOTALL)

        if role_match:
            role_desc = role_match.group(1).strip()
            if scene_match:
                args.seed = scene_match.group(1).strip()
        else:
            role_desc = human_input.strip()

        feishu_send_text(FEISHU_UA_PROFILE, chat_id,
                         f"✅ 角色已加载：{role_desc[:60]}\n"
                         f"场景：{args.seed}\n"
                         f"开始对话（共 {args.max_turns} 轮）...")

    # ── Build system prompt and run via claw CLI ──
    system = build_system_prompt(args.persona, file_pool_info,
                                 role=role_desc, scenario=args.seed)
    conv_history: list[dict] = []
    session_id: str | None = None
    roleplay_mode = bool(role_desc)
    message = args.seed if not roleplay_mode else ""
    files = list(args.file)

    for turn in range(1, args.max_turns + 1):
        print(f"\n{C('dim', f'── 第 {turn} 轮 ──')}")

        if turn > 1 or roleplay_mode:
            if turn == 1 and roleplay_mode:
                conv_history.append({"role": "user",
                                    "content": "请以角色身份发出第一条消息，围绕场景自然开启对话。"})

            agent_output = call_claude(conv_history, system)

            if turn == 1 and roleplay_mode:
                conv_history.pop()

            if not agent_output:
                print(f"{C('red', '[错误]')} User Agent 无法生成消息")
                break

            parsed = parse_agent_response(agent_output)
            message = parsed.get("message", "")
            files = parsed.get("files", [])
            done = parsed.get("done", False)

            if done:
                print(f"\n{C('green', 'User Agent 认为对话已完成')}")
                feishu_send_text(FEISHU_UA_PROFILE, chat_id, "📍 对话结束")
                break

            if not message:
                print(f"{C('red', '[错误]')} 空消息")
                break

            if files and args.file_pool:
                resolved = []
                for f in files:
                    full = os.path.join(args.file_pool, f)
                    if os.path.exists(full):
                        resolved.append(full)
                    elif os.path.exists(f):
                        resolved.append(f)
                files = resolved

        message, files, action = prompt_confirm(message, files, args.auto)
        if action == "quit":
            break

        print(f"\n{C('cyan', 'User Agent')}: {message}")

        # Snapshot group dir before claw runs
        group_dir = NANOCLAW_DIR / "groups" / "main"
        before_snap = snapshot_dir(group_dir)

        # Step 1: Call claw CLI first (direct container interaction, no Feishu)
        sys.stdout.write(f"  NanoClaw 处理中...")
        sys.stdout.flush()

        reply, session_id = claw_send(message, session_id, args.timeout, files)

        sys.stdout.write("\r" + " " * 40 + "\r")
        sys.stdout.flush()

        # Format roleplay tags in reply
        formatted_reply = format_roleplay_reply(reply) if roleplay_mode else reply
        print(f"\n{C('green', 'NanoClaw')}: {formatted_reply}")

        # Detect new/modified files by NanoClaw
        # Build set of original file sizes we sent, to distinguish
        # "NanoClaw modified our file" from "we just copied it there"
        sent_files: dict[str, int] = {}
        for f in (files or []):
            p = Path(f)
            if p.exists():
                sent_files[p.name] = p.stat().st_size
        all_new = scan_new_files(group_dir, before_snap)
        new_files = []
        for nf in all_new:
            if nf.name in sent_files and nf.stat().st_size == sent_files[nf.name]:
                continue  # Same file we sent, unchanged — skip
            new_files.append(nf)  # New file or NanoClaw modified it
        if new_files:
            print(f"\n  {C('yellow', '[新文件]')} {len(new_files)} 个:")
            for nf in new_files:
                print(f"    {C('green', '+')} {nf.relative_to(group_dir)}")

        # Step 2: Forward both sides to Feishu for display
        # UA bot sends user message + any attached files
        feishu_send_text(FEISHU_UA_PROFILE, chat_id, message)
        for f in files:
            feishu_send_file(FEISHU_UA_PROFILE, chat_id, str(f))
        # NC bot sends Andy's reply + any new files created
        feishu_send_text(FEISHU_NC_PROFILE, chat_id, formatted_reply[:4000])
        for nf in new_files:
            feishu_send_file(FEISHU_NC_PROFILE, chat_id, str(nf))

        # Update conversation history (use raw reply for LLM context)
        file_info = ""
        if files:
            file_info += f"\n[你发送了文件: {', '.join(str(f) for f in files)}]"
        conv_history.append({"role": "user",
                            "content": f"[你发送了] {message}" + file_info})

        reply_info = f"[AI 助手回复了] {reply}"
        if new_files:
            names = ", ".join(str(nf.relative_to(group_dir)) for nf in new_files)
            reply_info += f"\n[AI 助手创建了文件: {names}]"
        conv_history.append({"role": "assistant", "content": reply_info})

    print(C("dim", f"\n对话结束，共 {len(conv_history) // 2} 轮"))
    feishu_send_text(FEISHU_UA_PROFILE, chat_id,
                     f"📍 对话结束，共 {len(conv_history) // 2} 轮")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="User Agent: 模拟用户与 NanoClaw 自动交互")
    parser.add_argument("seed", nargs="?", default="自由对话",
                        help="初始 seed query（角色扮演模式下作为对话场景）")
    parser.add_argument("-f", "--file", action="append", default=[],
                        help="初始附加文件")
    parser.add_argument("--file-pool",
                        help="文件池目录（User Agent 可从中选择文件发送）")
    parser.add_argument("--persona", default="casual",
                        help="人设：casual(默认)/boss/dev/verbose 或 .md 文件路径")
    parser.add_argument("--role",
                        help="角色扮演：角色描述文本或 .md 文件路径。"
                             "提供后 seed 变为对话场景，User Agent 以角色身份生成开场白")
    parser.add_argument("--role-from-feishu", action="store_true",
                        help="[飞书模式] 启动后在飞书等待用户输入角色设定，"
                             "再以该角色身份开始对话")
    parser.add_argument("--auto", action="store_true",
                        help="全自动模式，不需要手动确认")
    parser.add_argument("--max-turns", type=int, default=20,
                        help="最大对话轮数 (默认 20)")
    parser.add_argument("--timeout", type=int, default=300,
                        help="等待回复超时秒数 (默认 300)")

    # Mode selection
    parser.add_argument("--feishu", action="store_true",
                        help="使用飞书轮询模式（两个 bot 在群里对话）")
    parser.add_argument("--feishu-chat-id",
                        help="飞书群 chat_id (默认: nanochat 群)")

    # Observation
    parser.add_argument("--observe", action="store_true",
                        help="[claw 模式] 同时转发对话到飞书群观察")

    args = parser.parse_args()

    if args.feishu:
        run_feishu_mode(args)
    else:
        run_claw_mode(args)


if __name__ == "__main__":
    main()
