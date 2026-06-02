# Cast — NPCs & companions

Every named character the Game Master voices lives in their own folder here, e.g. `Cast/Krista/`. The GM creates them by copying `_template/`.

Each character folder holds:

- **`profile.md`** — who they are, how they talk, what they want, and **what they openly know**. A *public* file: it's handed to the `npc-actor` when the GM voices them, so it must never contain anything the character themselves wouldn't know.
- **`memory.md`** — the running history of this character's dealings with you and the party, in their own eyes. Also handed to the actor (so a recurring ally remembers you), which is why it holds only what the character themselves witnessed or knows — never the GM's private read on them.
- **`secrets.md`** — their hidden agenda, true identity, or the twist they're sitting on. **GM-only.** This is *never* given to the actor voicing them — that's how a traitor can chat with you without giving themselves away.
- **`portraits/`** — optional images.

**Why split `secrets` from `profile` + `memory`?** A character's voice is produced in an isolated context with no file access that only ever receives `profile.md` and `memory.md`, so they literally can't reach or let slip what's in `secrets.md` — even though the GM knows it. And their consistency comes from these files being reloaded every time, not from anyone "remembering."

`_template/` is the blank skeleton the GM copies for each new character. Leave it as-is.
