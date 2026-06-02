# Cast — NPCs & companions

Every named character the Game Master voices lives in their own folder here, e.g. `Cast/Krista/`. The GM creates them by copying `_template/`.

Each character folder holds:

- **`profile.md`** — who they are, how they talk, what they want, and **what they openly know**. This is the *public* file: it's what gets handed to the `npc-actor` when the GM voices them, so it must never contain anything the character themselves wouldn't know.
- **`secrets.md`** — their hidden agenda, true identity, or the twist they're sitting on. **GM-only.** This is *never* given to the actor voicing them — that's how a traitor can chat with you without giving themselves away.
- **`memory.md`** — the running history of this character's dealings with you and the party, so they stay consistent across sessions.
- **`portraits/`** — optional images.

**Why split `profile` and `secrets`?** A character's voice is produced in an isolated context that only ever sees `profile.md`, so they literally can't let slip what's in `secrets.md` — even though the GM knows it. And their consistency comes from these files being reloaded every time, not from anyone "remembering."

`_template/` is the blank skeleton the GM copies for each new character. Leave it as-is.
