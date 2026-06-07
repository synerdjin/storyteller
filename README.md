# Storyteller — a World of Darkness engine

An AI-run tabletop roleplaying game for the **World of Darkness**. Open this project, talk to Claude, and it becomes your **Storyteller**: it builds your character and chronicle with you, then runs an ongoing, improvised story — narrating scenes, voicing characters, rolling the dice fairly, and remembering everything between sessions.

It plays three games on the classic **Storyteller System** (d10 dice pools):

- **Mage: The Ascension 20th (M20)** — belief reshapes reality, at the cost of your certainty.
- **Vampire: The Masquerade 20th (V20)** — the monster you're becoming versus the person you were.
- **Werewolf: The Apocalypse 20th (W20)** — primal warriors in a war against corruption they're losing.

You pick the game (or mix them, in **crossover** play) during Session Zero. No prior tabletop or World of Darkness experience needed — the Storyteller teaches you as you go.

## Get your own copy

This repository is the **engine** — a reusable template. To actually play, make your own copy so your story stays yours:

1. On GitHub, click **"Use this template" → "Create a new repository."**
2. Set it to **Private** and name it for your campaign (e.g. `my-first-campaign`).
3. Clone your new repo and open it in Claude Code.

Your copy is where you play: your character, your world, and your **save points** all commit to *your* private repo — with full history and the ability to revert a bad session — while this public engine stays clean for the next person.

> **Already in your own copy?** Skip to [How to start](#how-to-start).

*When a newer version of the engine ships, you don't have to copy files by hand — you can pull the updated system files into a campaign you've already started without disturbing your story. See [Updating the engine](#updating-the-engine).*

## How to start

Open the project and tell Claude:

> **"Let's start a new game."**

It'll walk you through **Session Zero** — agreeing on tone and any content limits, creating your character, and setting up the world — then drop you into your first scene.

To continue later, open the project and say **"Let's keep playing."** The GM picks up where you left off with a quick recap.

## How play works

- The Storyteller describes a scene and asks what you do. You answer in plain language — *"I search the desk," "I try to talk him down,"* whatever you want.
- When the outcome is uncertain, the Storyteller rolls real dice (`Tools/dice.py`) out in the open — d10 success pools the World of Darkness way — so you always know a result wasn't fudged.
- It runs on a faithful, lightweight **Storyteller System** scaffold so you can play right away. For your game's full rules, drop your own M20/V20/W20 book into `Sourcebooks/` and the Storyteller digests it — those rules then take over.

## What's in here

| Folder | What it's for |
|--------|---------------|
| `Character/` | Your character — sheet, backstory, portraits. |
| `Game/` | The living chronicle — `system.md` (which game is live), world, timeline, current scene, open threads. |
| `Cast/` | Every NPC and companion the Storyteller voices, one folder each. |
| `Sourcebooks/` | Drop your own M20/V20/W20 rulebooks and lore here for the Storyteller to digest. |
| `Tools/` | The dice roller (Storyteller d10 pools + a generic utility roller). |
| `PLAYER-NOTES.md` | Your spoiler-free notebook — what you know, want, and are chasing. The GM keeps it current; you can park your own notes there too. |
| `CLAUDE.md` | The GM's instructions (how it runs the game). |

## A note on spoilers

The GM keeps its secrets in `Game/gm-secrets.md` and each character's `Cast/<name>/secrets.md`. Characters in the story can never see those — that part is enforced. But *you* can open any file on your computer, so keeping the mystery alive for yourself is on the honor system: don't peek. 🙂

## Save points (optional)

If you want undo and the ability to branch alternate timelines, the GM can save your progress with git after each session. It'll ask first.

A gentle word: save points are for *stopping and resuming*, or for deliberately exploring a "what if" timeline — not for reloading the instant a roll goes against you. The stakes are what make a win feel earned; quietly reverting every setback removes them. Play your bad rolls and see where the story takes you. 🎲

## Updating the engine

The engine keeps improving — sharper GM instructions, smarter agents, the occasional new tool. To pull those improvements into a campaign you've already started, just tell the GM:

> **"Update storyteller."**

It saves a restore point, fetches the latest engine, and overwrites **only the system files** (`CLAUDE.md`, the agents, `Tools/`, the docs and templates). Your character, world, timeline, cast, and any rulebooks you've added are left exactly as they were. If a new version changes the *shape* of a file you've filled in, the GM shows you what's new and splices it in with you — it never erases your story. When it's done, it saves a second restore point, so the whole update is something you can roll back like any other save.

> One caveat if you like to tinker: updating **replaces** the engine files, so if you've hand-edited `CLAUDE.md`, the agents, or `Tools/`, commit your changes first and re-apply them after — or contribute them back upstream. The full mechanism (and the exact list of what's touched vs. protected) lives in [`UPDATING.md`](UPDATING.md).

## Models

Each role runs on the model that fits how it's used. The one-time creative builders use Opus; the constantly-running roles use Sonnet (cheaper and faster).

| Role | Model | Set in |
|------|-------|--------|
| campaign-architect | Opus | `.claude/agents/campaign-architect.md` (frontmatter) |
| character-creator | Opus | `.claude/agents/character-creator.md` (frontmatter) |
| Game Master (main session) | Sonnet | `.claude/settings.json` (project default) |
| npc-actor | Sonnet | `.claude/agents/npc-actor.md` (frontmatter) |

To change any of them, edit the `model:` line in that agent's file (`opus` / `sonnet` / `haiku`). The Game Master is the session model — `.claude/settings.json` sets the default when you open the project, and you can switch any time with `/model`.
