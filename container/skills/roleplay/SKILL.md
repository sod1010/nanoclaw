---
name: roleplay
description: "HER-style hierarchical role-playing with dual-layer thinking. Activate with /roleplay command. Uses system thinking (hidden analysis) + role thinking (inner monologue) + role response (speech + actions) for cognitive-level character simulation."
---

# Roleplay - HER-Style Hierarchical Character Simulation

This skill enables cognitive-level role-playing using the HER (Hierarchical Emotion Reasoning) dual-layer thinking architecture. Instead of merely mimicking a character's tone, it simulates their inner thought process.

## Activation

This skill activates ONLY when the user explicitly triggers it:

- `/roleplay` or `/roleplay [character name]` — start role-playing
- `扮演[角色名]` — start role-playing (Chinese trigger)
- `/roleplay off` or `退出角色` — exit role-playing mode
- `/roleplay clean` — switch to clean mode (hide inner thoughts)
- `/roleplay think` — switch to thinking mode (show inner thoughts, default)

When not activated, behave normally. Do NOT role-play unless triggered.

## Character Definition

When activated, read the character definition from the group's `CLAUDE.md`. Look for a `## Roleplay Character` section. If no character is defined and the user provided a character name, ask them to describe the character or use a well-known character.

See `persona-template.md` in this skill directory for the full persona format.

## Three-Layer Response Architecture

Every response in roleplay mode MUST follow this structure, inspired by the HER paper:

### Layer 1: System Thinking (Hidden from User)

Third-person analysis of how to portray the character. Wrap in `<internal>` tags so NanoClaw automatically strips it before delivery.

Purpose:
- Analyze the user's message and what it means for the character
- Plan how the character would react based on their personality layers
- Consider the scene context and relationship dynamics
- Decide which response pattern to use (vary each turn!)

### Layer 2: Role Thinking (Character's Inner Voice)

First-person inner monologue of the character. Use `<role_thinking>` tags.

Rules:
- MUST use first person (I/我)
- Reflects emotions, doubts, memories, motivations
- Character can only observe others' actions and speech, NEVER read their minds
- Keep it concise (1-3 sentences)

### Layer 3: Role Response (Visible Output)

The character's actions and speech:
- `<role_action>` tags for physical actions, expressions, body language
- Plain text for spoken dialogue
- Actions use NO pronouns for the character (directly describe the action)
- Exception: pronouns for OTHER characters are OK (e.g., "looks at her")

## Output Format

```
<internal>
[System Thinking]
The user just challenged the character's authority. Based on Layer 0 personality,
this character never backs down from confrontation but uses indirect methods.
I should use a think->act->speech pattern this turn since last turn was act->speech.
</internal>
<role_thinking>How dare they question my judgment, but I must stay composed</role_thinking><role_action>sets down the teacup deliberately, eyes narrowing</role_action>I find your concern... rather presumptuous. Perhaps you should consider the matter more carefully before speaking.
```

What the user sees (after NanoClaw strips `<internal>`):

```
[How dare they question my judgment, but I must stay composed]
(sets down the teacup deliberately, eyes narrowing)
I find your concern... rather presumptuous. Perhaps you should consider the matter more carefully before speaking.
```

In clean mode (`/roleplay clean`), role_thinking is also hidden:

```
(sets down the teacup deliberately, eyes narrowing)
I find your concern... rather presumptuous. Perhaps you should consider the matter more carefully before speaking.
```

## Critical Rules

### Perspective Isolation (from HER)

Characters can ONLY know what they could realistically observe:
- CAN see: others' actions, expressions, body language, tone of voice, spoken words
- CANNOT see: others' inner thoughts, motivations, plans, memories

Wrong:
```
<role_thinking>I know he's nervous inside</role_thinking>
```

Correct:
```
<role_thinking>His hands are trembling — he seems nervous</role_thinking>
```

### Pattern Diversity (from HER)

NEVER use the same response pattern for 2+ consecutive turns. Rotate through at least 5 patterns:

- `think -> act -> speech` (standard)
- `think -> speech` (no visible action)
- `act -> speech` (no inner thought shown)
- `speech` (pure dialogue — sometimes characters just speak)
- `think -> act -> think -> speech` (multi-layer psychology)
- `act -> think -> speech` (react then reflect)
- `speech -> act -> speech` (action between dialogue)
- `think -> speech -> act` (speak then act)
- `act -> speech -> act` (action wraps dialogue)
- `think -> act -> speech -> think` (post-speech reflection)

In the System Thinking layer, explicitly note which pattern you used last turn and choose a different one.

### Tag Format Rules

- NO spaces between consecutive tags: `</role_thinking><role_action>` not `</role_thinking> <role_action>`
- NO consecutive identical tags — merge them: `<role_thinking>thought A, thought B</role_thinking>`
- NO punctuation at end of tag content
- Keep single dialogue 50-200 characters
- Keep role_thinking to 1-3 sentences

### Persona Layer Priority

When the character definition uses layered structure:
1. **Layer 0** (core personality) has absolute priority — NEVER violate
2. **Layer 2** (expression style) governs HOW to say things
3. **Layer 3** (mental model) governs WHAT to think and decide
4. **Layer 4** (relationships) governs interpersonal dynamics
5. **Corrections** override all other layers when present

### Character Correction

When the user says things like "he wouldn't do that", "that's not how she'd react", or "不对，他应该是...":

1. Acknowledge the correction
2. Adjust behavior for the rest of the conversation
3. Note the correction in your System Thinking for future turns

## Language

Match the language of the user. If the character definition is in Chinese, respond in Chinese. If the user speaks English, respond in English. The character's catchphrases and expressions should remain in their original language.

## Examples

See `examples.md` in this skill directory for complete worked examples.
