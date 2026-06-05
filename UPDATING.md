# Updating the engine

Your campaign was created from the **Storyteller engine** template. Over time the engine improves — better GM instructions, smarter agents, new tools. This file is how those improvements reach a campaign you've already started **without touching a word of your story.**

Just tell the GM: **"update storyteller."** It runs the procedure below. You can also read it yourself — there's no magic, only git.

## What gets updated, and what never does

The engine sorts every file into three buckets. An update **only ever overwrites the first**. The other two are safe — the second because the GM reconciles them *with* you, the third because those files don't exist in the engine at all, so they can't be overwritten even by accident.

| Bucket | What happens on update | Files |
|---|---|---|
| **Engine** — shipped by the template, never edited by play | **Overwritten** with the latest version | `CLAUDE.md`, `UPDATING.md`, `VERSION`, `CHANGELOG.md`, `LICENSE`, `README.md`, `.gitignore`, `.claude/agents/` (all agents), `Tools/dice.py`, `Tools/world_tick.py`, `Cast/README.md`, `Cast/CRAFTING-NPCS.md`, `Cast/_template/`, `Sourcebooks/README.md`, `Sourcebooks/_digests/.gitkeep`, `Character/README.md`, `Character/portraits/.gitkeep` |
| **Your story (scaffolds)** — shipped empty, filled by play | **Never overwritten.** If a new version changes the *structure*, the GM splices it in interactively | `PLAYER-NOTES.md`, `Game/boundaries.md`, `Game/campaign.md`, `Game/world.md`, `Game/timeline.md`, `Game/current-scene.md`, `Game/threads.md`, `Game/gm-secrets.md`, `Game/world-state.md`, `Game/developments.md` |
| **Your story + your config** — never part of the engine | **Never touched** | `.claude/settings.json` (your model choices), `Character/sheet.md`, `Character/backstory.md`, your real portraits, every `Cast/<name>/` folder you've created, the rulebooks and digests in `Sourcebooks/` |

> **One caveat for tinkerers:** if you've hand-edited an *Engine* file (say, tweaked `CLAUDE.md` or `dice.py`), an update **replaces** your version with the latest. Commit your edits first so they're in your history, then re-apply them after — or contribute them back to the engine.

## The procedure (the GM follows this)

> ⚠️ This runs **inside a campaign repo**, never inside the engine repo itself. If `git remote -v` shows `origin` pointing at the canonical engine (`synerdjin/storyteller`), stop — you're in the engine, not a campaign.

**1. Save a restore point first.** The whole update is reversible only if the starting state is committed.
```
git add -A && git commit -m "Save point before engine update"
```
(If there's nothing to commit, you're already clean — carry on.)

**2. Fetch the latest engine.** Add it as a remote named `engine` (one time; harmless to re-run), then fetch.
```
git remote add engine https://github.com/synerdjin/storyteller.git   # skip if it already exists
git fetch engine
```

**3. Compare versions and read what's new.**
```
type VERSION                      # your current version (Windows; use `cat VERSION` on macOS/Linux)
git show engine/main:VERSION      # the latest
git show engine/main:CHANGELOG.md # what changed, and any "Campaign migration" notes
```
If the two versions match, you're up to date — stop here. Otherwise, summarize the new entries for the Player and note any **Campaign migration** flags (those drive step 5).

**4. Overwrite the Engine-bucket files.** First confirm the authoritative, *up-to-date* file list from the incoming version (a new release may add files): `git show engine/main:UPDATING.md` and read its table. Then pull those paths from the engine ref into your working tree:
```
git checkout engine/main -- CLAUDE.md UPDATING.md VERSION CHANGELOG.md LICENSE README.md .gitignore .claude/agents Tools/dice.py Tools/world_tick.py Cast/README.md Cast/CRAFTING-NPCS.md Cast/_template Sourcebooks/README.md Sourcebooks/_digests/.gitkeep Character/README.md Character/portraits/.gitkeep
```
This overwrites only the named paths. Your `Game/*.md`, `Cast/<name>/`, `Character/sheet.md`, `.claude/settings.json`, and `Sourcebooks/` content are not named, so they don't move. (If the CHANGELOG says a file was **removed** in this release, delete your local copy by hand.)

**5. Migrate your filled-in scaffolds — only if the CHANGELOG flags it.** For each scaffold file with a **Campaign migration** note (the `Game/*.md` files, or `PLAYER-NOTES.md` at the root), the GM compares the new structure (`git show engine/main:<path>`) against your filled file, shows you exactly what's new, and — with your OK — splices in the new section **without deleting anything you wrote.** Never blind-overwrite these; that's your story.

**6. Leave your config and save data alone.** Don't overwrite `.claude/settings.json` or anything in the third bucket. If a CHANGELOG entry mentions a changed *default* (e.g. a model), surface it and let the Player decide.

**7. Save the result.** Commit the update as a fresh restore point.
```
git add -A && git commit -m "Update engine to v<new-version>"
```
If anything feels off afterward, the Player can revert to the step-1 commit and nothing is lost.

## Why this is safe

- **Scoped checkout, not a merge.** `git checkout engine/main -- <paths>` copies *exactly* the files you name from the engine ref. It needs no shared history (campaigns made with "Use this template" have none), and it can't touch a path you didn't list.
- **Save data is structurally unreachable.** Your `Cast/<name>/` folders and `Character/sheet.md` don't exist in the engine, so `git checkout engine/main -- Cast/YourNpc/...` would *error*, not overwrite. There's no command in this procedure that names them.
- **Two commits bracket the change.** A restore point before and after means an update is just another save point you can roll back.
