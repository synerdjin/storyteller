# Storyteller — a living-world World of Darkness engine

An AI-run tabletop roleplaying game for the **World of Darkness**. Open this project, talk to Claude, and it becomes your **Storyteller**: it builds your character and chronicle with you, then runs an ongoing, improvised story — narrating scenes, voicing characters, rolling the dice fairly, and remembering everything between sessions.

What sets it apart is the **living world**. You are not the only protagonist. The world is full of other characters who want things and pursue them whether or not you're watching — and when their goals cross, **plots emerge on their own**, with or without you. You can join them, ignore them (and watch them resolve without you), or be blindsided by them. And the whole chronicle can be archived as polished **fan-fiction** — chaptered prose with the dice dissolved into story.

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

It'll walk you through **Session Zero** — agreeing on tone, any content limits, and the **play mode** (story-first, world-simulation, or challenge-forward — see below), creating your character, and setting up the world (including a small **cast of NPCs whose goals already collide**, so the world starts moving from day one) — then drop you into your first scene.

To continue later, open the project and say **"Let's keep playing."** The GM picks up where you left off with a quick recap.

## How play works

- The Storyteller describes a scene and asks what you do. You answer in plain language — *"I search the desk," "I try to talk him down,"* whatever you want.
- When the outcome is uncertain, the Storyteller rolls **real dice** (`Tools/dice.py`) — d10 success pools the World of Darkness way — but keeps the *numbers off the page*: you read a vivid outcome, not a stat block. Ask *"what did I roll?"* any time and it shows you the full result. The dice are never fudged; they're just invisible, so the prose reads like a story.
- **After every move you make, the world takes a beat too.** Off-screen, other characters advance their own schemes, clash with each other, and react to you. Anything you'd plausibly notice surfaces as live pressure or an offered hook — never a hard interruption.
- It runs on a faithful, lightweight **Storyteller System** scaffold so you can play right away. For your game's full rules, drop your own M20/V20/W20 book into `Sourcebooks/` and the Storyteller digests it — those rules then take over.

You're a co-author, not just a lead: you can steer the *kind* of story you want (*"I'd love this to become a betrayal arc," "can we slow down and just talk"*) and the Storyteller adjusts.

---

## How it works (under the hood)

You don't need any of this to play — but if you're curious how the world stays alive and fair, here's the machine. The guiding principle throughout: **deterministic tools own the numbers; AI owns the prose.** The same way `dice.py` keeps a roll honest, a set of small, auditable Python tools decide *what is structurally true* in the world, and Claude only ever decides *what it means*.

### The play mode — what kind of game this is

Multi-character stories tend toward one of three flavors, and you pick one at Session Zero: **Dramatist** (story-first — the default, where the world is aimed at the best honest story), **Simulationist** (a world that behaves consistently and indifferently, surprises and all), or **Evaluationist** (challenge-forward, where stakes and costs bite harder). It's only an *interpretation* dial — it never changes the dice or the tools, just how the Storyteller and the world read the same honest outcomes. World of Darkness suits *Dramatist-on-a-simulation-substrate*, so that's the default; the others are leans you can ask for. Whatever content limits you set in `boundaries.md` always win over the mode.

### The living world, and its heartbeat

The world is a cast of **living agents** — NPCs and factions that carry their own goals. After **each in-character post you make**, the engine ticks the world one beat. That tick is a deliberate three-layer split, so the world can't quietly advance only the convenient threats:

1. **The metronome — `Tools/world_tick.py`** (deterministic, no AI). It reads every living agent's state, advances their clocks by fixed rules, fires their state-machine transitions, and — the important part — **detects collisions**: two agents reaching for the same thing, a rivalry boiling over, someone moving on you. It writes a queue of who moved and where they clashed. It finds the conflict; it never decides who wins.
2. **The scribe — `Tools/world_scribe.py`** (a small **local** model on your own GPU, run every post). For each mover and each collision it writes what happened, promotes a hardened collision into a real plot, and triages — flagging the pivotal beats for Claude.
3. **The director — the `world-director` agent** (Claude, only for the flagged pivots). It resolves planned reveals, major faction turns, and anything turning on a hidden secret — honestly, using the dice or an oracle for genuinely uncertain outcomes.

Everything the world does is staged in `Game/developments.md` with a *surface* timing (now / soon / hidden); the Storyteller weaves the "now" items into your next scene.

### What a living agent is

Each living character carries a small **agent model** (in their GM-only `Cast/<name>/drives.md`):

- a **targeted goal** — *what* they're reaching for and *which* entity (`{ pursue: control, target: harbor-council }`). **Two agents aiming at the same target is the seed of a plot.**
- a **relationship graph** — typed, weighted ties to other characters (ally, rival, debt, grudge, patron…).
- **resources** (influence, muscle, coin, secrets…) and a volatile **mood** (confidence, desperation…) that makes them reach further as pressure mounts.
- optionally a **group** (their faction) and a **worldview** seeded from real value frameworks (`Tools/cultural_profile.py`), so a Camarilla elder and an Anarch firebrand genuinely *reason differently* rather than just sounding different.

### How plots emerge

Plots aren't scripted — they **emerge** from those agents colliding. When two non-allied agents reach for the same target, the metronome opens a **control ledger** for it (`Game/ledgers.md`): a pool of leverage points that shifts, every tick, toward whoever is better positioned (a fixed formula of resources + mood + standing — never an AI guess). So a rival who's been losing for five beats visibly sits at 1/10 while the holder entrenches at 8/10, and the ledger's *phase* (forming → rising → climax) drives the plot's arc. It's the dice-fairness principle applied to politics: the contest has memory, and the result is a number you could audit, not a vibe. The scribe only narrates what that number *means*.

Every plot — yours and the world's — lives in the master registry `Game/plots.md`, each tagged with how involved you are (unaware → aware → participating). The slice you actually know about is mirrored into `Game/threads.md`.

### How news travels

The world doesn't let everyone magically know everything. The relationship graph *is* a social network, and `Tools/social.py` spreads information along it: when something observable happens, only the characters within a couple of hops of it come to hear — and it's written into their memory as something *they* learned (never the hidden cause). A well-connected NPC hears everything; a loner hears nothing. Faction-mates hear their own news further and travel. A character's standing (**reputation**) is derived from the ledgers, so it always matches what's actually happened.

### How agents change their minds

Living agents run a full loop — **observe → retrieve → reflect → plan**:

- they **observe** (events land in their memory) and **retrieve** the relevant bits before they act;
- when they finish a phase of a scheme, they **reflect** — the local model distills their recent memory into a belief or two ("the council won't fall to patience alone"), written into their drives;
- and on a new belief or a hard swing in a contest, the director lets them **re-plan** — retargeting a goal, resetting a clock, flipping a friend into an enemy. So rivals *adapt* instead of looping forever.

### The fan-fiction layer

Because the mechanics stay off the page, your live play already reads as prose. Periodically — at a scene close, or on request — the **`chapter-renderer`** agent archives the chronicle as polished chapters under `Story/`: *player-POV* chapters retelling what you lived, and *"meanwhile"* chapters following the world's other protagonists, including arcs you never touched. `python Tools/story_compile.py` stitches them into a single readable file. (A strict spoiler rule keeps a "meanwhile" chapter from ever handing you a secret your character hasn't earned.)

### The secrecy firewall

A hard line runs through the whole engine. Two kinds of AI role exist, and they're never blurred:

- the **`world-director`** is GM-side and *secret-aware* — it reads hidden agendas because its job is to advance them;
- the **`npc-actor`** that voices a character on-screen is *blind* — it's handed only that character's public profile and memories, never any secret file, and it runs in an isolated context with no file access, so it literally cannot leak what it was never given.

The local memory search enforces the same line (`--scope public` never returns GM files), and GM-only state — secrets, drives, plots, ledgers, the world's backstage — is structurally walled off from anything player-facing.

### Keeping it all straight

Continuity lives in files, not just in the AI's memory: the current scene, a day-stamped timeline, the cast's individual memories, the world and its factions. A simple **campaign-day counter** anchors time so the GM (and the characters it voices) can compute "how long ago" instead of guessing. Your own spoiler-free dashboard lives in `PLAYER-NOTES.md`. And because a solo world can quietly drift, a deterministic **health check** (`Tools/world_health.py`) audits it at save points — flagging a thread left dangling, an NPC who's gone still, or a beat the GM forgot to surface — so nothing important silently stalls.

---

## What's in here

| Folder / file | What it's for |
|--------|---------------|
| `Character/` | Your character — sheet, backstory, portraits. |
| `Cast/` | Every NPC and companion the Storyteller voices, one folder each (public profile + memory, plus GM-only secrets, stats, and the `drives.md` agent model). |
| `Game/` | The living chronicle: `system.md` (which game is live), `world.md`, `timeline.md`, `current-scene.md`, the player-known `threads.md`, and the GM-only `plots.md`, `developments.md`, `ledgers.md`, `world-state.md`, `gm-secrets.md`. |
| `Story/` | The chronicle rendered as **fan-fiction** — chapters, an index, and a compiled export. |
| `Sourcebooks/` | Drop your own M20/V20/W20 rulebooks and lore here for the Storyteller to digest. |
| `Tools/` | The deterministic engine: the dice roller, the world metronome (`world_tick.py`), the local scribe (`world_scribe.py`), control ledgers (`ledger.py`), social propagation (`social.py`), the world-health drift audit (`world_health.py`), cultural profiles (`cultural_profile.py`), story compiler (`story_compile.py`), and the semantic-memory + local-compute layer. |
| `.claude/agents/` | The GM's specialist subagents — campaign-architect, character-creator, world-director, npc-actor, chapter-renderer. |
| `PLAYER-NOTES.md` | Your spoiler-free notebook — what you know, want, and are chasing. The GM keeps it current; you can park your own notes there too. |
| `CLAUDE.md` | The GM's full operating manual (how it runs the game). |

## A note on spoilers

The GM keeps its secrets in `Game/gm-secrets.md`, each character's `Cast/<name>/secrets.md`, and the other GM-only files (`plots.md`, `ledgers.md`, `drives.md`, `developments.md`, `world-state.md`). The characters in the story can never see those — that part is enforced by the firewall. But *you* can open any file on your computer, so keeping the mystery alive for yourself is on the honor system: don't peek. 🙂

## Save points (optional)

If you want undo and the ability to branch alternate timelines, the GM can save your progress with git after each session. It'll ask first.

A gentle word: save points are for *stopping and resuming*, or for deliberately exploring a "what if" timeline — not for reloading the instant a roll goes against you. The stakes are what make a win feel earned; quietly reverting every setback removes them. Play your bad rolls and see where the story takes you. 🎲

## The local-compute layer (recommended)

Because the world ticks on **every** post, the engine leans on a small model running on your own machine to do the high-frequency bookkeeping — semantic memory search, scribing off-screen moves, resolving routine collisions, propagating news, reflecting agents — so Claude's budget goes to live play and the prose you actually read. A side benefit: your GM secrets never leave your machine.

If you have an NVIDIA GPU (a 12 GB card like an RTX 4070 is plenty), set it up via [Ollama](https://ollama.com) and [`Tools/local-agents/README.md`](Tools/local-agents/README.md). It's **optional and degrades gracefully** — with no local model present, the world simply ticks at scene cuts instead of every post and the `world-director` handles the whole queue. Correct, just costlier — so a local model is strongly recommended for this engine.

## Updating the engine

The engine keeps improving — sharper GM instructions, smarter agents, new tools. To pull those improvements into a campaign you've already started, just tell the GM:

> **"Update storyteller."**

It saves a restore point, fetches the latest engine, and overwrites **only the system files** (`CLAUDE.md`, the agents, `Tools/`, the docs and templates). Your character, world, timeline, cast, plots, and any rulebooks you've added are left exactly as they were. If a new version changes the *shape* of a file you've filled in, the GM shows you what's new and splices it in with you — it never erases your story. When it's done, it saves a second restore point, so the whole update is something you can roll back like any other save.

> One caveat if you like to tinker: updating **replaces** the engine files, so if you've hand-edited `CLAUDE.md`, the agents, or `Tools/`, commit your changes first and re-apply them after — or contribute them back upstream. The full mechanism (and the exact list of what's touched vs. protected) lives in [`UPDATING.md`](UPDATING.md).

## Models

Each role runs on the model that fits how it's used. The one-time creative builders and the secret-aware world director use Opus; the constantly-running session and on-screen voicing use Sonnet (cheaper and faster); the per-post bookkeeping runs on your local model, not Claude at all.

| Role | Model | Set in |
|------|-------|--------|
| Game Master (main session) | Sonnet | `.claude/settings.json` (project default) |
| campaign-architect | Opus | `.claude/agents/campaign-architect.md` |
| character-creator | Opus | `.claude/agents/character-creator.md` |
| world-director (off-screen pivots) | Opus | `.claude/agents/world-director.md` |
| chapter-renderer (fan-fiction) | Opus | `.claude/agents/chapter-renderer.md` |
| npc-actor (voicing a character) | Sonnet | `.claude/agents/npc-actor.md` |
| the world scribe + memory (per post) | *local* | `Game/local-models.json` |

To change any Claude role, edit the `model:` line in that agent's file (`opus` / `sonnet` / `haiku`). The Game Master is the session model — `.claude/settings.json` sets the default when you open the project, and you can switch any time with `/model`.
