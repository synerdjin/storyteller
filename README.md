# Storyteller

An AI-run tabletop roleplaying game. Open this project, talk to Claude, and it becomes your **Game Master**: it builds your character and world with you, then runs an ongoing, improvised adventure — narrating scenes, voicing characters, rolling dice fairly, and remembering everything between sessions.

No prior tabletop experience needed. The GM teaches you as you go.

## How to start

Open the project and tell Claude:

> **"Let's start a new game."**

It'll walk you through **Session Zero** — agreeing on tone and any content limits, creating your character, and setting up the world — then drop you into your first scene.

To continue later, open the project and say **"Let's keep playing."** The GM picks up where you left off with a quick recap.

## How play works

- The GM describes a scene and asks what you do. You answer in plain language — *"I search the desk," "I try to talk him down,"* whatever you want.
- When the outcome is uncertain, the GM rolls real dice (`Tools/dice.py`) out in the open, so you always know a result wasn't fudged.
- It starts with a simple built-in rule system. If you'd rather play a specific system (D&D, etc.), drop its rulebook into `Sourcebooks/` and tell the GM to use it.

## What's in here

| Folder | What it's for |
|--------|---------------|
| `Character/` | Your character — sheet, backstory, portraits. |
| `Game/` | The living campaign — world, timeline, current scene, open threads. |
| `Cast/` | Every NPC and companion the GM voices, one folder each. |
| `Sourcebooks/` | Drop rulebooks and lore here for the GM to use. |
| `Tools/` | The dice roller. |
| `CLAUDE.md` | The GM's instructions (how it runs the game). |

## A note on spoilers

The GM keeps its secrets in `Game/gm-secrets.md` and each character's `Cast/<name>/secrets.md`. Characters in the story can never see those — that part is enforced. But *you* can open any file on your computer, so keeping the mystery alive for yourself is on the honor system: don't peek. 🙂

## Save points (optional)

If you want undo and the ability to branch alternate timelines, the GM can save your progress with git after each session. It'll ask first.

## Models

Each role runs on the model that fits how it's used. The one-time creative builders use Opus; the constantly-running roles use Sonnet (cheaper and faster).

| Role | Model | Set in |
|------|-------|--------|
| campaign-architect | Opus | `.claude/agents/campaign-architect.md` (frontmatter) |
| character-creator | Opus | `.claude/agents/character-creator.md` (frontmatter) |
| Game Master (main session) | Sonnet | `.claude/settings.json` (project default) |
| npc-actor | Sonnet | `.claude/agents/npc-actor.md` (frontmatter) |

To change any of them, edit the `model:` line in that agent's file (`opus` / `sonnet` / `haiku`). The Game Master is the session model — `.claude/settings.json` sets the default when you open the project, and you can switch any time with `/model`.
