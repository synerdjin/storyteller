# Storyteller — an AI World of Darkness game master

An AI-run tabletop roleplaying game for the **World of Darkness**. Open this project, talk to Claude, and it becomes your **Storyteller**: it builds your character and chronicle with you, then runs an ongoing, improvised story — narrating scenes, voicing characters, rolling the dice fairly, and remembering everything between sessions. The whole chronicle can be archived as polished **fan-fiction** — chaptered prose with the dice dissolved into story.

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

It'll walk you through **Session Zero** — agreeing on tone and any content limits, creating your character, and setting up the world (including a small **cast of connected NPCs** with their own goals and rivalries, so the world feels alive from day one) — then drop you into your first scene.

To continue later, open the project and say **"Let's keep playing."** The GM picks up where you left off with a quick recap.

## How play works

- The Storyteller describes a scene and asks what you do. You answer in plain language — *"I search the desk," "I try to talk him down,"* whatever you want.
- When the outcome is uncertain, the Storyteller rolls **real dice** (`Tools/dice.py`) — d10 success pools the World of Darkness way — but keeps the *numbers off the page*: you read a vivid outcome, not a stat block. Ask *"what did I roll?"* any time and it shows you the full result. The dice are never fudged; they're just invisible, so the prose reads like a story.
- You're one protagonist among many. The world's other characters have their own wants and agendas, and the GM moves them with its own judgment — so something you ignore can come back to find you, surfacing as live pressure or an offered hook rather than a hard interruption.
- It runs on a faithful, lightweight **Storyteller System** scaffold so you can play right away. For your game's full rules, drop your own M20/V20/W20 book into `Sourcebooks/` and the Storyteller digests it — those rules then take over.

You're a co-author, not just a lead: you can steer the *kind* of story you want (*"I'd love this to become a betrayal arc," "can we slow down and just talk"*) and the Storyteller adjusts.

---

## How it works (under the hood)

You don't need any of this to play — but if you're curious how the world stays fair and consistent, here's the machine. The guiding principle: **deterministic tools own the numbers; AI owns the prose.** `dice.py` keeps a roll honest off the page, and continuity lives in files rather than only in the AI's memory.

### Fair dice, invisible mechanics

Every uncertain action is resolved with a real roll (`Tools/dice.py`) — a d10 success pool, the difficulty set by the task. The result stands, win or lose, and you can audit any roll on demand (*"what did I roll?"*). But the numbers never reach the page: you read the failed lockpick or the blade that bit deeper than expected, not a stat block. Resources (Willpower, Blood, Rage, Health, Paradox…) are tracked the same way, by `Tools/resources.py`, with an auditable log — never hand-edited.

### The secrecy firewall

A hard line keeps secrets out of characters' mouths. The **`npc-actor`** that voices a character on-screen is *blind* — it's handed only that character's public profile and memories, never any secret file, and it runs in an isolated context with no file access, so it literally cannot leak what it was never given. The GM's secrets live in `Game/gm-secrets.md` and each character's `Cast/<name>/secrets.md`, structurally walled off from anything player-facing. The local memory search enforces the same line (`--scope public` never returns GM files).

### Keeping it all straight

Continuity lives in files, not just in the AI's memory: the current scene, a day-stamped timeline, the cast's individual memories, the world and its factions, and the open threads you're chasing. A simple **campaign-day counter** anchors time so the GM (and the characters it voices) can compute "how long ago" instead of guessing. Your own spoiler-free dashboard lives in `PLAYER-NOTES.md`.

### The fan-fiction layer

Because the mechanics stay off the page, your live play already reads as prose. Periodically — at a scene close, or on request — the **`chapter-renderer`** agent archives the chronicle as polished chapters under `Story/`, retelling what you lived with the dice dissolved into story. `python Tools/story_compile.py` stitches them into a single readable file. (A strict spoiler rule keeps a chapter from ever handing you a secret your character hasn't earned.)

---

## What's in here

| Folder / file | What it's for |
|--------|---------------|
| `Character/` | Your character — sheet, backstory, portraits. |
| `Cast/` | Every NPC and companion the Storyteller voices, one folder each (public profile + memory, plus GM-only secrets and stats). |
| `Game/` | The chronicle's state: `system.md` (which game is live), `world.md`, `timeline.md`, `current-scene.md`, the open `threads.md`, and the GM-only `gm-secrets.md`. |
| `Story/` | The chronicle rendered as **fan-fiction** — chapters, an index, and a compiled export. |
| `Sourcebooks/` | Drop your own M20/V20/W20 rulebooks and lore here for the Storyteller to digest. |
| `Tools/` | The deterministic engine: the dice roller (`dice.py`), resource tracker (`resources.py`), cultural profiles (`cultural_profile.py`), story compiler (`story_compile.py`), the safe actor-briefing assembler (`actor_brief.py`), and the hybrid semantic-memory layer. |
| `.claude/agents/` | The GM's specialist subagents — campaign-architect, character-creator, npc-actor, chapter-renderer. |
| `PLAYER-NOTES.md` | Your spoiler-free notebook — what you know, want, and are chasing. The GM keeps it current; you can park your own notes there too. |
| `CLAUDE.md` | The GM's full operating manual (how it runs the game). |

## A note on spoilers

The GM keeps its secrets in `Game/gm-secrets.md` and each character's `Cast/<name>/secrets.md`. The characters in the story can never see those — that part is enforced by the firewall. But *you* can open any file on your computer, so keeping the mystery alive for yourself is on the honor system: don't peek. 🙂

## Save points (optional)

If you want undo and the ability to branch alternate timelines, the GM can save your progress with git after each session. It'll ask first.

A gentle word: save points are for *stopping and resuming*, or for deliberately exploring a "what if" timeline — not for reloading the instant a roll goes against you. The stakes are what make a win feel earned; quietly reverting every setback removes them. Play your bad rolls and see where the story takes you. 🎲

## The local-compute layer (optional)

The engine can keep more of Claude's budget for live play by grounding facts in the record with a **hybrid semantic memory** instead of re-reading whole files. A small **embedding model** on your own machine powers it, and a side benefit is that your GM secrets never leave your machine.

If you have an NVIDIA GPU (a 12 GB card like an RTX 4070 is plenty), set up the embedder via [Ollama](https://ollama.com) and [`Tools/local-agents/README.md`](Tools/local-agents/README.md). It's **optional and degrades gracefully** — with no embedder present, memory search falls back to a model-free keyword (BM25) mode, and you can always read the markdown directly.

## Updating the engine

The engine keeps improving — sharper GM instructions, smarter agents, new tools. To pull those improvements into a campaign you've already started, just tell the GM:

> **"Update storyteller."**

It saves a restore point, fetches the latest engine, and overwrites **only the system files** (`CLAUDE.md`, the agents, `Tools/`, the docs and templates). Your character, world, timeline, cast, threads, and any rulebooks you've added are left exactly as they were. If a new version changes the *shape* of a file you've filled in, the GM shows you what's new and splices it in with you — it never erases your story. When it's done, it saves a second restore point, so the whole update is something you can roll back like any other save.

> One caveat if you like to tinker: updating **replaces** the engine files, so if you've hand-edited `CLAUDE.md`, the agents, or `Tools/`, commit your changes first and re-apply them after — or contribute them back upstream. The full mechanism (and the exact list of what's touched vs. protected) lives in [`UPDATING.md`](UPDATING.md).

## Models

Each role runs on the model that fits how it's used. The one-time creative builders use Opus; the constantly-running session and on-screen voicing use Sonnet (cheaper and faster); semantic memory runs on a small local embedder.

| Role | Model | Set in |
|------|-------|--------|
| Game Master (main session) | Sonnet | `.claude/settings.json` (project default) |
| campaign-architect | Opus | `.claude/agents/campaign-architect.md` |
| character-creator | Opus | `.claude/agents/character-creator.md` |
| chapter-renderer (fan-fiction) | Opus | `.claude/agents/chapter-renderer.md` |
| npc-actor (voicing a character) | Sonnet | `.claude/agents/npc-actor.md` |
| semantic memory (hybrid retrieval) | *local embedder* | `Game/local-models.json` |

To change any Claude role, edit the `model:` line in that agent's file (`opus` / `sonnet` / `haiku`). The Game Master is the session model — `.claude/settings.json` sets the default when you open the project, and you can switch any time with `/model`.
