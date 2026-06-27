# Digest: Mage: The Ascension — 20th Anniversary Edition (M20) core rulebook

> Scan-fast rules summary the Storyteller consults mid-scene **instead of** re-reading the PDF. When live, note it in `Game/system.md`. Its rules **override** the matching CLAUDE.md defaults — see **Overrides** at the end.

## System & source
- **Game & line:** Mage: The Ascension 20th Anniversary (M20)
- **Source:** *Mage: The Ascension 20th Anniversary Edition* (Final Download PDF). Drawn from: Ch6 Creating the Character (pp. 245–339), Ch8 The Book of Rules (pp. 384–395), Ch9 Dramatic Systems / Health & Combat (pp. 406–413), Ch10 The Book of Magick (pp. 499–527). Page cites inline below.
- **Dice subcommand:** `m20` (pass to `Tools/dice.py`)

## Core resolution (Ch8, pp. 385–395)
- **Pool = Attribute + Ability** (+ splat dice where they apply — e.g. Arete for magick). One d10 per dot. Decent pool ≈ 4+ dice.
- **Difficulty:** default **6**. Range **3–9** (3 trivial, 4 easy, 5 straightforward, 6 standard, 7 challenging, 8 difficult, 9 extreme). ST may shift ±1 to ±3 for circumstances. A die **≥ difficulty = a success**. A **10 is always a success** (but can't do the impossible).
- **Degrees:** 1 = marginal, 2 = moderate, 3 = complete, 4 = exceptional, 5+ = phenomenal.
- **Botches & the Rule of One:** each **1 cancels one success**. Zero successes **and** at least one 1 = **botch** (catastrophic, active failure). Zero successes with no 1 = plain failure. (Botches on *magick* always count — no free-botch option for spells; p. 393.)
- **Specialty** (Trait at 4+ dots): a rolled **10 counts as two successes** (p. 274).
- **Willpower spend:** **+1 automatic success**, and **cannot botch** that roll. Max **1 WP/turn** (several across an extended action). (p. 395)
- **Automatic success:** if pool ≥ difficulty and stakes are low, skip the roll. Doesn't apply to combat, extended, or resisted rolls.
- **Action types (p. 388–391):**
  - *Reflexive* — no roll (spend WP, soak, brief speech).
  - *Simple* — one roll, one success needed.
  - *Multiple* — split the **lowest** dice pool among the actions that turn.
  - *Extended* — accumulate **N successes** across multiple rolls (rituals, research). Failed roll = no progress; **botch = whole effort fails** (often lose accumulated successes).
  - *Resisted* — both roll; **opponent's successes subtract from yours**, most net wins.
  - *Extended & resisted* — sustained contest of the above.
  - *Teamwork* — combine successes; one helper's **botch ruins all** unless they separate their effort.
- **Trying again:** each repeat after a failure adds **+1 difficulty** (p. 391).
- **Thresholds (optional, p. 387):** near-impossible tasks set a minimum-successes floor *before* 1s are subtracted (threshold N removes N successes).
- **The oracle (engine device, not in book):** keep the CLAUDE.md d6 oracle for *world facts*.

## Magick resolution (Ch10, pp. 500–510)
- **Cast = roll Arete** (one die per Arete dot) vs. difficulty set by **coincidental vs. vulgar** (p. 501):
  | Effect is… | Difficulty |
  |---|---|
  | **Coincidental** (could plausibly be mundane) | **highest Sphere + 3** |
  | **Vulgar, no witnesses** | **highest Sphere + 4** |
  | **Vulgar, with witnesses** (Sleepers watching) | **highest Sphere + 5** |
  - Min difficulty 3, **max 10**. Net modifiers capped at **±3**. (If a modifier pushes difficulty over 10, each +1 past 9 instead demands an extra success.)
- **Sphere rating caps the Effect.** When combining Spheres, the limiting factor is the mage's rank **in the Sphere doing the work** (e.g. Corr 2 / Forces 3 fire-at-a-distance is held to *Corr 2's* range).
- **Successes needed = the feat** (Magickal Feats, p. 502): 1 simple, 2 standard, 3 difficult, 4 impressive, 5–10 mighty, 10–20 outlandish, 20+ godlike. Personal Effects ≈ 1 success; affecting others ≥ 2; world-altering ≥ 5. **Successes set Damage *or* Duration** (Base Damage/Duration chart, p. 504), not both.
- **Paradox accrual (p. 501–502):**
  | | On success | On botch |
  |---|---|---|
  | **Coincidental** | none | **1 per dot** in highest Sphere |
  | **Vulgar, no witnesses** | **1 point** | **1 + 1 per dot** in highest Sphere |
  | **Vulgar, with witnesses** | **1 point** | **2 + 2 per dot** in highest Sphere |
  - Backlash check: ST may roll for backlash once Paradox passes ~5; mandatory danger zone higher (see Backlash table below).
- **Quintessence (p. 332, 503):** spend to **lower casting difficulty by 1 per point, max −3**. Points spendable per turn = **Avatar rating**. Also fuels Prime Effects / countermagick. Stored in Avatar (max = Avatar Background); refill via Node meditation, Tass, or Prime.
- **Tools / foci (p. 503):** personalized instrument −1; unique −1; unique+specialized −2 total; sympathetic item from target −1 to −3; near a Node −1 to −3; researched the subject first −1 to −3. Working **without usual instruments +3**; unfamiliar instruments +2/+1; fast-casting +1; turning time backwards +3.
- **At Arete 1–2 a mage MUST use focus** (paradigm + practice + ≥7 instruments). From Arete 3 a mystic may discard one instrument per dot of Arete above 2; by Arete 9 needs none. Technocrats can't discard until Arete 6. (p. 329)
- **Spheres can't exceed Arete.** If *permanent Willpower* drops below Arete, Spheres & casting are limited to Willpower, not Arete (p. 329).

## The nine Spheres (Ch10 pp. 511–527)
Generic rank ladder (p. 511): **1 Perception · 2 Manipulation (small/self) · 3 Control (alter reality, deals damage) · 4 Command (alter others' Patterns) · 5 Mastery (godlike).** Pattern Spheres = Forces/Life/Matter (+Prime to make "real"). Per Sphere:

- **Correspondence** — space, distance, connections. 1 sense/measure local space · 2 sense & reach through space, scrying · 3 open small gates / co-locality perceptions / move objects at range (w/ Pattern Sphere) · 4 permanent gates, wards, co-locate self · 5 spatial mutation, full co-location, stretch/compress space. (Range by successes, p. 504.)
- **Entropy** — fate, probability, decay, mortality, necromancy. 1 sense flaws/fate/truth · 2 control probability (luck) · 3 affect predictable patterns (induce decay/failure) · 4 affect living things (disease, curses; **damage = aggravated**) · 5 affect thought/memes, bind oaths. *No damage until Rank 4* (p. 514).
- **Forces** — energies: fire, motion, gravity, light, sound, electricity, weather. 1 perceive forces (IR/UV, electron, radio) · 2 manipulate existing forces (human-sized) · 3 transmute minor forces / conjure (w/ Prime) / telekinesis · 4 control major forces (weather, large area) · 5 transmute major forces (firestorms). **Forces attacks add +1 automatic damage success** (p. 504).
- **Life** — organic Patterns, healing, shapeshifting. 1 sense life (health/age/sex) · 2 alter simple life-forms / heal self · 3 transform simple life / **heal or harm others** (alter own form) · 4 alter complex life / transform self into other forms · 5 transform & create complex life. *(Healing rank in parens = on others.)* Damage via Life = **aggravated**; Pattern-altered creatures suffer **Pattern bleeding** (1 lethal/day) until Prime refills.
- **Matter** — inert materials. 1 perceive material properties · 2 basic transmutation (same shape/state) · 3 alter form / change state · 4 complex transmutation (build devices) · 5 alter properties (impossible substances).
- **Mind** — consciousness, illusion, telepathy, astral. 1 sense thoughts/emotions, shield mind, empower self · 2 read surface thoughts, empathic bond · 3 mind link, mental illusions, dreamwalk, **psychic blast** · 4 control conscious mind, astral projection, posthypnotic commands · 5 control subconscious, rewrite minds, forge new psyche. Offensive Mind vs. **target's Willpower** (min diff 4). **Mind damage = bashing** unless noted.
- **Prime** — Quintessence, the energy that makes Patterns "real." 1 etheric senses, consecrate, infuse personal Quint · 2 fuel/enchant Patterns, Body of Light, infuse weapons (→ harm spirits / agg damage) · 3 channel Quint, energy weapon, craft periapts/temp wonders · 4 craft Tass & permanent Wonders, drain energy · 5 infuse/withdraw life force, create Nodes, **nullify Paradox**.
- **Spirit** — the Umbra, spirits, the Gauntlet. 1 spirit sight/sense · 2 touch spirit, manipulate Gauntlet (±1 per success) · 3 pierce Gauntlet / step sideways / rouse & lull spirits · 4 rend Gauntlet, bind spirits, seal breaches · 5 forge ephemera, Gilgul, break the Dreamshell. Difficulty often uses **Gauntlet Ratings** (p. 505: Node 3 / wilderness 5 / rural 6 / urban 7 / downtown 8 / Tech lab 9).
- **Time** — temporal perception & manipulation. 1 time sense · 2 past/future sight, thicken the walls of time · 3 time contraction/dilation ("bullet time"), rewind small spans · 4 time determinism, triggers, time bubbles, anchor points · 5 temporal travel, time immunity. **Rewinding time +3 difficulty, always vulgar.** Time & Correspondence inflict no damage alone.

*(Optional Technocratic alternates: Data ≈ Correspondence, Dimensional Science ≈ Spirit, Primal Utility ≈ Prime — Technocrats only.)*

## Character rules (Ch6)

### Sheet shape (p. 252 sheet)
Nature/Demeanor/**Essence** (Dynamic/Static/Primordial/Questing) · Affiliation/Sect/Concept · **Attributes** (Physical: Str/Dex/Sta · Social: Cha/Man/App · Mental: Per/Int/Wits) · **Abilities** (Talents/Skills/Knowledges, incl. secondary) · **Spheres** (the nine) · **Backgrounds** · **Arete** · **Willpower** · **Quintessence/Paradox** wheel · **Health** · Experience.

### Creation — five steps (p. 250)
1. **Concept:** identity, Affiliation, Essence, Nature & Demeanor archetypes.
2. **Attributes** — prioritize **7 / 5 / 3** across Physical/Social/Mental (each starts at 1 dot free).
3. **Abilities** — prioritize **13 / 9 / 5** across Talents/Skills/Knowledges. **No Ability above 3** at this stage.
4. **Advantages** — **7 Backgrounds**; define focus (≥1 paradigm, ≥1 practice, ≥7 instruments).
5. **Finishing touches** — **6 Sphere dots** (first dot must go in the group's **Affinity Sphere**; Spheres ≤ Arete). Starting **Arete 1**, **Willpower 5**, **Quintessence = Avatar rating**, **Paradox 0**. Then **15 freebie points**.

**Affinity Sphere** is mandatory (one dot minimum), set by sect (p. 251), e.g. Order of Hermes → Forces; Verbena → Life or Forces; Akashayana → Mind or Life; Virtual Adepts → Correspondence/Data or Forces; NWO → Mind or Correspondence/Data. Every mage needs **≥1 dot Avatar**.

### Freebie point costs (p. 253)
| Trait | Cost |
|---|---|
| Attribute | 5 / dot |
| Ability | 2 / dot |
| Background | 1 / dot |
| Sphere | 7 / dot |
| Arete | **4 / dot (max total Arete 3 at creation)** |
| Willpower | 1 / dot |
| Quintessence | 1 per 4 dots |
| Merit | as Merit |
| Flaw | grants points (**max +7**) |

### Avatar Background (p. 254, 338)
The inner mentor/Genius. Rating sets **max stored Quintessence** and Quint-per-turn. High Avatar (4–5) drives the mage hard and triggers **Seekings** (vision-quests required to raise Arete).

## Key tables

### Health levels & wound penalties (p. 406)
| Level | Penalty | Movement |
|---|---|---|
| Bruised | 0 | banged up, fine |
| Hurt | −1 | minor, can act |
| Injured | −1 | half movement |
| Wounded | −2 | can't run |
| Mauled | −2 | hobble (3 yds/turn) |
| Crippled | −5 | crawl (1 yd/turn) |
| Incapacitated | — | unconscious |
| Dead | — | — |
Penalties **don't affect Avatar, soak, or Arete rolls** (mage can still cast while Incapacitated if WP remains). 8 health levels total.

### Damage types & soak (p. 409–412)
- **Bashing** (`/`) — fists, falls, psychic, knockout. **Soak with Stamina** (everyone). Heals fast.
- **Lethal** (`X`) — blades, bullets. **Mages CANNOT soak lethal** without armor / Life or Prime magick. (Optional *Cinematic Damage*: humans soak lethal at diff 8.)
- **Aggravated** (`*`) — fire, acid, vampire fangs, werewolf claws, Life/Entropy/Prime Pattern attacks. **No one soaks agg without magick or special armor.** Slow to heal; needs Life magick + 1 Quint/level to heal.
- **Soak roll:** Stamina vs. difficulty 6 (bashing/lethal). **Damage roll:** attacker rolls pool vs. diff 6, each success = 1 level; +1 damage die per *extra* attack success. Dodges/blocks subtract successes.

### Healing times (p. 406)
- *Bashing:* Bruised→Wounded 1 hr · Mauled 3 hr · Crippled 6 hr · Incap 12 hr.
- *Lethal/Agg:* Bruised 1 day · Hurt 3 days · Injured 1 wk · Wounded 1 mo · Mauled 2 mo · Crippled 3 mo · Incap 5 mo (cumulative). Untreated lethal/agg **worsens 1 level/day** below Hurt until stabilized (Int+Medicine).

### Paradox backlash (p. 506) — ST rolls 1 die per current Paradox point vs. diff 6
| Successes | Effect |
|---|---|
| Botch | all Paradox discharges harmlessly |
| 0 | nothing, no discharge |
| 1–5 | 1 Paradox/success discharged + 1 bashing/success + trivial Paradox Flaw |
| 6–10 | discharge + bashing Burn + minor Paradox Flaw |
| 11–15 | discharge + lethal Burn or (significant Flaw / Paradox Spirit / mild Quiet) |
| 16–20 | discharge + lethal Burn + 1 permanent Paradox or two of (severe Flaw / Spirit / moderate Quiet / Paradox Realm) |
| 21+ | discharge + agg Burn + two of (perm Paradox / drastic Flaw / Spirit / severe Quiet / Paradox Realm) |
- **20+ Paradox with no backlash:** mage may drop into Quiet, vanish, or explode (p. 333). Avoid magick a while to **shed** Paradox (p. 549). **Quiet** escalates by Paradox discharged: L1 (1–3) minor delusions → L6 (21+) goes Marauder/NPC.

### Experience costs (p. 253, 336)
| Trait | Cost |
|---|---|
| New Ability | **3** |
| New Sphere | **10** |
| **Affinity** Sphere | current × **7** |
| Other Sphere | current × **8** |
| Arete | current × **8** |
| Attribute | current × **4** |
| Ability | current × **2** |
| Background* | current × **3** |
| Willpower | current × **1** |
*Backgrounds raisable by XP only at ST option; double-cost Backgrounds = current × 6.
- **Raising Arete requires a Seeking** (p. 329). **New Spheres need a teacher** of matching focus; raise one dot at a time, grounded in fiction.

## Overrides (what this digest replaces in CLAUDE.md)
This digest is the **live rules** when present. It replaces:
- **Core resolution nuances** — same d10 pool / diff 6 / botch logic as the engine default, but adds M20-specifics: 10 always succeeds, **Willpower = +1 auto success & no botch (1/turn)**, specialty = 10 counts twice, formal action types (reflexive/simple/multiple/extended/resisted/teamwork), thresholds, and **+1 difficulty per retry**.
- **Magick & Paradox handling** — replaces the engine's lightweight "vulgar +1" sketch with the exact M20 scheme: **Arete roll**, difficulty = **highest Sphere + 3/4/5** (coincidental / vulgar / vulgar-witnessed), the Paradox accrual table (incl. botch math), Quintessence −1/pt (max −3, Avatar-capped/turn), focus/tool modifiers, and the **Paradox backlash + Quiet** tables. Spheres capped by Arete; casting capped by permanent Willpower if it drops below Arete. Use this in place of CLAUDE.md "Resolution & dice" magick notes.
- **Condition track / soak** — replaces the engine's 7-step track with M20's **8-level** track and exact penalties (note Crippled = **−5**, and penalties don't touch Avatar/soak/Arete). Soak rules: **mages can't soak lethal** (no armor/magick) and **no one soaks aggravated** unaided — stricter than the generic default.
- **Advancement / XP costs** — replaces the engine's "costs more at higher rating" scaffold with the **exact M20 XP table** above (current-rating multipliers; new Ability 3 / new Sphere 10; Arete needs a Seeking). Keep the engine's triggered-milestone *awards*, but spend at these costs.
- **Keep from the engine:** the d6 **oracle** for world facts, **progress clocks**, the campaign-day clock, and the "resolve-then-narrate / mechanics off the page" presentation — none are overridden.
