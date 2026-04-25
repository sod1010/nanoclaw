---
name: add-roleplay
description: "Add HER-style role-playing to NanoClaw agents. Uses dual-layer thinking (system thinking + role thinking) for cognitive-level character simulation. Triggers with /roleplay command in chat."
---

# Add HER-Style Roleplay

This skill adds cognitive-level role-playing capability to NanoClaw, based on the HER (Hierarchical Emotion Reasoning) paper's dual-layer thinking architecture.

## Phase 1: Pre-flight

### Check if already applied

Check if `container/skills/roleplay/SKILL.md` exists. If it does, skip to Phase 2 (Setup). The code changes are already in place.

## Phase 2: Apply Code Changes

### Option A: If the skill branch exists

```bash
git fetch origin skill/roleplay 2>/dev/null
```

If the branch exists, merge it:

```bash
git merge origin/skill/roleplay
```

### Option B: If no branch (local install)

The files should already be in place:
- `container/skills/roleplay/SKILL.md` — core skill instructions
- `container/skills/roleplay/persona-template.md` — character definition template
- `container/skills/roleplay/examples.md` — output format examples

Verify they exist:

```bash
ls container/skills/roleplay/
```

### Rebuild container

```bash
./container/build.sh
```

## Phase 3: Setup — Define a Character

Use `AskUserQuestion` to help the user set up a character:

### Ask which group

AskUserQuestion: Which group should have role-playing? (list registered groups)

### Ask about the character

AskUserQuestion: What character do you want the agent to play?

Options:
1. A character from a book/movie/game (provide name and source)
2. An original character (describe them)
3. Just install — I'll configure the character later

### Write character definition

If the user wants to configure now:

1. Read `container/skills/roleplay/persona-template.md` for the template structure
2. Based on the user's description, generate a character definition following the layered persona format
3. Write it into the target group's `CLAUDE.md` file under a `## Roleplay Character` section

For well-known characters (e.g., Elizabeth Bennet, Sherlock Holmes), use your knowledge to fill in:
- Layer 0: Core personality rules
- Layer 1: Expression style with catchphrases and speech patterns
- Layer 2: Mental model and decision framework
- Layer 3: Relationship patterns
- Current scene (ask the user)

For original characters, ask the user to provide:
- Name and background
- 3-4 core personality rules
- How they talk (catchphrases, tone, patterns)
- How they think and make decisions

### Restart service

```bash
npm run build
launchctl kickstart -k gui/$(id -u)/com.nanoclaw  # macOS
# Linux: systemctl --user restart nanoclaw
```

## Phase 4: Verify

Tell the user:

> Send `/roleplay` in the group chat to activate role-playing mode. The agent will respond as the configured character using layered thinking:
>
> - `[inner thoughts]` — the character's internal monologue
> - `(actions)` — physical actions and expressions
> - Plain text — what the character says
>
> Send `/roleplay off` to return to normal mode.
> Send `/roleplay clean` to hide inner thoughts (only show actions + speech).

## Usage

Once installed, users interact via chat commands:

| Command | Effect |
|---------|--------|
| `/roleplay` | Activate with configured character |
| `/roleplay [name]` | Activate as a specific character |
| `/roleplay off` | Return to normal mode |
| `/roleplay clean` | Hide role_thinking, show only actions + speech |
| `/roleplay think` | Show full output including inner thoughts (default) |

## How It Works

The agent uses three layers of thinking for each response:

1. **System Thinking** (hidden) — Third-person analysis: "How should this character react?" Automatically stripped by NanoClaw's `<internal>` tag filter.
2. **Role Thinking** (visible as `[...]`) — First-person inner monologue: the character's thoughts
3. **Role Response** (visible) — Actions `(...)` and spoken dialogue

This mirrors the HER paper's insight that simulating a character's cognitive process (not just their tone) produces more authentic role-playing.

## Troubleshooting

### Agent doesn't enter roleplay mode

- Verify `container/skills/roleplay/SKILL.md` exists
- Rebuild the container: `./container/build.sh`
- Check that the skill was synced: look in `data/sessions/{group}/.claude/skills/roleplay/`

### System thinking leaks into output

- The `<internal>` tag stripping happens in `src/index.ts`. Verify the agent is wrapping system thinking in `<internal>` tags, not `<system_thinking>`.

### Character feels generic

- Improve the character definition in the group's `CLAUDE.md`
- Add more specific Layer 0 rules and Layer 1 expression examples
- Use the correction mechanism: tell the agent "he wouldn't say that, he would..."

## Removal

To remove roleplay capability:

1. Delete `container/skills/roleplay/` directory
2. Remove the `## Roleplay Character` section from any group CLAUDE.md files
3. Rebuild: `./container/build.sh`
