# Sourcebooks

This engine plays the **World of Darkness** (Mage M20, Vampire V20, Werewolf W20) on the Storyteller System. It ships with a faithful but deliberately light rules **scaffold** (in `CLAUDE.md`) so you can start playing immediately. To run the *full* rules of your game, drop your own books here.

**Bring your own books.** Drop the rulebooks, setting guides, or bestiaries you legally own into this folder — PDFs, markdown, plain text, whatever you have (e.g. the M20 / V20 / W20 corebook for your game). Nothing is included here for you, by design: the rules are White Wolf / Paradox's, and they're yours to provide.

**You don't have to convert anything.** When the Storyteller first needs a book during play, it reads the relevant parts and saves a compact summary into `_digests/` (use `_digests/_TEMPLATE.md` as the shape). From then on it consults that lightweight digest instead of re-reading the whole file every time — faster, and it keeps the GM focused on your story.

**A digest overrides the defaults.** Once a digest for your game exists, **its** rules — character creation, dice nuances, Health/soak, advancement costs — replace the matching defaults in `CLAUDE.md`. Note the live digest(s) in `Game/system.md` so the GM and the subagents all play by the same book.

`_digests/` is created and maintained by the GM. You're welcome to read the digests, but you don't need to touch them.
