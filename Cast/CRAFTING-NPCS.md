# Crafting NPCs — a GM's guide to characters worth caring about

> GM-facing craft notes. This is *how to build* a memorable character; the character's actual content lives in their `Cast/<name>/` files. Consult this when you're promoting an NPC from a face in the crowd to someone the story leans on.

## First: depth is for important NPCs only

A recurring ally, a rival, a faction head, a companion — these earn a full build. The guard at the gate, the merchant you'll never see again — a vibe and a voice is plenty. Spending depth on a walk-on slows play and *buries* the real characters under detail no one will use.

So don't front-load it. Sketch most NPCs in a line (`profile.md`, maybe `secrets.md`) and **promote one to "important" the moment the Player starts caring about them** — not before. When that happens, fill out the fields below across their files, and add a `sheet.md` if they'll ever be rolled against.

Where each piece lives:
- **`profile.md`** (actor-safe) — what the character knows about *themselves*: their code, their stated wants, the background they'd own, their visible contradictions.
- **`secrets.md`** (GM-only) — the depth that drives them *without their seeing it*: the unadmitted need, the wound, the breaking point.
- **`sheet.md`** (GM-only) — the mechanics, if they'll face contested rolls or a fight.

## The seven levers

What makes an important NPC feel like a person rather than a quest-dispenser:

1. **A want and a need that don't match.** The *want* is what they chase on screen — the throne, the cure, revenge. The *need* is what would actually heal them, and it usually contradicts the want — to be forgiven, to stop running, to be seen. Drama lives in that gap. Put the want in `profile.md`; keep the unspoken need in `secrets.md`.

   *Ground the want in a worldview.* A goal feels inevitable when it flows from a value-system, not a whim — and a cast whose members reason from *different* values generates conflict on its own. Seed each recurring NPC's outlook with `python Tools/cultural_profile.py <preset>` (faction archetypes like `camarilla` / `sabbat` / `anarch` / `technocratic` / `garou-tribal`, or the generic `individualist`/`collectivist`/`egalitarian`/`hierarchical`), fold the worldview sentence into their `profile.md`, and let it explain *why* this character wants what they want. The numbers are calibratable — adjust or write your own; the presets are a starting point, not canon.

2. **A wound that explains the behavior.** One formative injury — a betrayal, a loss, a failure they never lived down — that their present-day choices are still defending against. Don't narrate the wound. Let it *leak* through what they overreact to: the topic that hardens them, the kindness they can't accept, the threat they answer too fast.

3. **A real moral code — with a price.** Give them lines they genuinely won't cross, so the one time they're forced to, it actually costs something. A villain with a code is scarier than one without; an ally with a code can betray you *for a reason* you'll understand. Then define the exact pressure that would break that code — that's where their best scene is waiting (note it in `secrets.md`).

4. **A contradiction held in tension.** Real people aren't consistent. The tender enforcer. The coward who shows up anyway. The devout liar. One genuine contradiction does more for believability than a page of backstory — and it gives you two honest ways to play any scene.

5. **Agency off-screen — and friction with each other.** Important NPCs *want things and pursue them when the Player isn't watching.* They are not set dressing waiting to be talked to. Give each one a goal they're actively advancing, so the world feels like it has other protagonists and the Player's neglect has consequences. Note in their `secrets.md` what they're working toward, who can help, and who's in the way — then, between scenes, ask yourself what they'd have done and let it show when the Player next crosses their path.

   The real spark, though, is not a single NPC's plan — it's **two NPCs whose goals can't both win.** When you build a connected cast, don't build them in isolation: **build the tension between them.** Point two of them at the same prize with opposed aims — one would `control` what another would `destroy`, one would `protect` whom another would `expose` — give them rivalries, debts, and the means to actually fight, and you have a proto-plot that writes itself the moment the Player nudges it.

   > **A worked example.** *Mara* wants to control the harbor council; so does *Vance*. One prize, two claimants. Mara holds blackmail; Vance has the dockhands. They're rivals who each have a real lever. The Player has met neither — yet the GM can already feel the shape of it: Mara's blackmail surfacing as a rumor, Vance answering with a beating, a harbor-war pressing on the city the Player lives in. You seeded the **opposed goals and the means**; play supplies the **story**.

   Three things shape how such a clash plays — keep them in mind as you voice it: **resources** decide who's better positioned (an advantage, never an automatic win), **desperation** decides how far an agent will reach (rising pressure unlocks the move they'd normally refuse), and **relationships** decide who else gets pulled in (a patron called for backup, a debt collected at the worst moment).

6. **A voice you could pick out blind.** Cadence, vocabulary, sentence length, and — most telling — *what they won't say*. If you covered the name tags, the Player should still know who's speaking. This is what `profile.md`'s Voice section is for; make it specific. "Gruff" is not a voice.

7. **Room to change.** The best NPCs are different by the end. Let the Player's choices move them — soften, harden, fall, redeem — and don't pre-decide which way. When they shift, note the change *and its cause* in their `memory.md` and the timeline, the same way the Player's own character advances through fiction.

## The honest-opposition tie-in

Depth and the "play the opposition honestly" prime directive feed each other. A villain with a real code, a buried wound, and goals they pursue off-screen *generates* honest pressure on the Player without you having to manufacture threats or fudge dice — the character's own agenda is the danger. Build the antagonist well and half your GMing does itself: you just ask what they'd really do, and play it straight.
