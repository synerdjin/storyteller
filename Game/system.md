# System — which game we're playing

> Set during Session Zero, **before** the character and campaign. The single source of truth for which World of Darkness game is live, its rules, and its tone. Every agent and the Storyteller read this first. Update it only with the Player's agreement (e.g. adding a sourcebook digest, turning on crossover).

## Game

- **Primary game:** *(Mage: The Ascension 20th (M20) · Vampire: The Masquerade 20th (V20) · Werewolf: The Apocalypse 20th (W20))*
- **Edition / line:** *(e.g. 20th Anniversary Edition)*
- **Core theme to lean on:** *(M20 — ascension horror · V20 — personal horror · W20 — primal/rage horror)*

## Crossover

- **Crossover on?** *(no · yes)*
- **Splats in play (if yes):** *(which games share the table, and which character/NPC belongs to which)*
- **House rule for the seam:** *(how the games' rules meet — default: each character uses their own game's traits, pools, and tone; one splat's rules never silently govern another's)*

## Play mode — the engine's stance

> Which *kind* of game this is, in the Evaluationist/Dramatist/Simulationist sense (the typology from Vezhnevets et al., *Multi-Actor Generative AI as a Game Engine*, 2025). Every agent reads this and weights its choices accordingly. The default suits most World of Darkness chronicles; settle it during Session Zero alongside tone, and change it only with the Player's agreement. See "Play mode" in `CLAUDE.md` for what each setting does.

- **Primary mode:** *(**Dramatist** (default) — the world is aimed at the best story; mechanics stay off the page · **Simulationist** — the world behaves consistently from its tracked state, surprises included, with less narrative override · **Evaluationist** — challenge-forward; stakes, clocks, and costs are felt and more visible)*
- **Leans (optional):** *(nudge the default without switching it, e.g. "Dramatist, with a Simulationist lean — honor the metronome hard" · "Dramatist, Evaluationist lean — let lethality and costs bite")*
- **What it tunes:** how hard the metronome's binding selection is played in fiction, whether any mechanics surface in prose, and how the lethality set in `boundaries.md` is leaned on. It never changes the dice or the tools — only how the GM and the `world-director` interpret them.

## Rules in force

- **Live sourcebook digests:** *(files under `Sourcebooks/_digests/` that override the engine defaults — list them, or "none yet: running on the CLAUDE.md Storyteller defaults")*
- **Dice subcommand(s):** *(`m20` / `v20` / `w20` — what to pass to `Tools/dice.py`)*
- **House rules:** *(any tweaks the Player wants — soak, difficulty conventions, lethality, etc. Keep tone/content limits in `boundaries.md`, not here.)*
