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

2. **A wound that explains the behavior.** One formative injury — a betrayal, a loss, a failure they never lived down — that their present-day choices are still defending against. Don't narrate the wound. Let it *leak* through what they overreact to: the topic that hardens them, the kindness they can't accept, the threat they answer too fast.

3. **A real moral code — with a price.** Give them lines they genuinely won't cross, so the one time they're forced to, it actually costs something. A villain with a code is scarier than one without; an ally with a code can betray you *for a reason* you'll understand. Then define the exact pressure that would break that code — that's where their best scene is waiting (note it in `secrets.md`).

4. **A contradiction held in tension.** Real people aren't consistent. The tender enforcer. The coward who shows up anyway. The devout liar. One genuine contradiction does more for believability than a page of backstory — and it gives you two honest ways to play any scene.

5. **Agency off-screen — and friction with each other.** Important NPCs *want things and pursue them when the Player isn't watching.* They are not set dressing waiting to be talked to. Give each one a goal they're actively advancing, so the world feels like it has other protagonists and the Player's neglect has consequences. For the few who should genuinely *act* between scenes, promote them to a **living** agent: copy `Cast/_template/drives.md` into their folder and let the world tick advance their agenda fairly and automatically (see `CLAUDE.md` → "The living world"). Reserve this for the characters the story leans on — a living roster of three pressing rivals beats a dozen idling ones.

   But the real engine of a living world is not a single NPC's clock — it's **two NPCs whose goals can't both win.** A living agent's `drives.md` carries a *targeted* goal (`goal: { pursue, target, success }`), a **relationship graph** to other entities, abstract **resources** they can spend, and a volatile **mood**. Plots *emerge* when you point two agents at the same target with opposed verbs — the metronome detects the **collision** and the world resolves it off-screen, without you scripting the outcome. So when you build a living cast, don't build them in isolation: **build the tension between them.**

   > **The minimal unit of emergence — a worked example.** *Mara* wants `{ pursue: control, target: harbor-council }`; *Vance* wants `{ pursue: control, target: harbor-council }` too. One target, two claimants — a collision. Mara has `resources: { secrets: 4 }` (she's holding blackmail); Vance has `resources: { muscle: 3 }` (he has the dockhands). Their graphs point at each other with `tie: rival`. The Player has met neither — yet by Day 5 the tick has them clashing over the council seat, Mara's blackmail surfaces as a rumor, Vance answers with a beating, and a *harbor-war* plot the GM never wrote is now pressing on the city the Player lives in. That is the whole design in one example: you seed the **opposed goals and the means**, the simulation supplies the **story**.

   Three knobs shape how a collision plays: **`resources`** decide who's *better positioned* (the resolver's advantage hint — never an automatic win), **`mood`** decides how *far* an agent will reach (rising desperation unlocks the move they'd normally refuse), and **`relationships`** decide *who else gets pulled in* (a `patron` called for backup, a `debt` collected at the worst moment). Fill the prose sections of `drives.md` (`## Relationships`, `## Resources & leverage`) so the resolver clashes them in concrete terms, not abstract points.

6. **A voice you could pick out blind.** Cadence, vocabulary, sentence length, and — most telling — *what they won't say*. If you covered the name tags, the Player should still know who's speaking. This is what `profile.md`'s Voice section is for; make it specific. "Gruff" is not a voice.

7. **Room to change.** The best NPCs are different by the end. Let the Player's choices move them — soften, harden, fall, redeem — and don't pre-decide which way. When they shift, note the change *and its cause* in their `memory.md` and the timeline, the same way the Player's own character advances through fiction.

## The honest-opposition tie-in

Depth and the "play the opposition honestly" prime directive feed each other. A villain with a real code, a buried wound, and goals they pursue off-screen *generates* honest pressure on the Player without you having to manufacture threats or fudge dice — the character's own agenda is the danger. Build the antagonist well and half your GMing does itself: you just ask what they'd really do, and play it straight.
