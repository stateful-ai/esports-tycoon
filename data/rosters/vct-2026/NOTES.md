# VCT 2026 pack — research provenance & caveats

Compiled 2026-07-09 from vlr.gg (primary) and liquipedia.net/valorant
(backup) by four region research agents. Rosters are the STARTING FIVES as
of the Stage 2 window (post June/July transfers) — where a completed
transfer hadn't debuted yet, the registered Stage 2 five was used over the
last-played lineup. Edit the sheets in `src/` and rerun
`scripts\build_roster_pack.py vct-2026` to update (expansion is
deterministic — untouched players keep identical attributes).

## League lists verified (differ from pre-research expectations)

- **Americas**: ENVY ascended in, replacing 2Game (2Game kept as tier-2).
- **EMEA**: Eternal Fire and PCIFIC Esports in; Movistar KOI's slot
  withdrawn (Gentle Mates re-admitted); Apeks out.
- **Pacific**: DRX rebranded **KIWOOM DRX** (tag KRX); TALON out,
  FULL SENSE in; Nongshim RedForce + VARREL added (2025 Ascension);
  Riot removed Ascension for 2026.
- **China**: XLG and DRG entered via Ascension; the rest as expected.

## Known-shaky calls (re-verify before trusting)

- **GiantX (EMEA)** — weakest data in the pack: only
  westside/Flickless/ara confirmed; grubinho (IGL guess) and tomaszy are
  placeholders pending GX's announcements.
- **LOUD** fifth slot was genuinely TBD; kept Virtyy (last match played).
- **Gen.G** rostered the brand-new July 9 five (Efina IGL + RaxcaL) that
  has played zero official matches.
- **Trace (CN)** IGL unknown after Viva moved to coaching; deLb assigned.
- **Team Secret** IGL Sylvan and **VARREL** IGL C1ndeR are guesses.
- **T1**: Munchkin marked IGL per Liquipedia (not stax).
- Most tier-2 IGLs and roles are inferred; several tier-2 real names were
  unavailable (handle used as placeholder or "Unknown").

## Systematic caveats

- **Ages**: only a handful confirmed (f4ngeer 19, RaxcaL 18, xan 19,
  seph1roth 22, Shyy 21, Paincakes 23, zerona 20, forbanz 24, chubizin 18,
  trexx 22, Kicks 20, ExiT 20, grubinho 22, Proxh 23, Zimo 22 + famous
  veterans). Everything else is an informed estimate, treat +/-2 years.
- **Quality** anchors on VCT 2026 Stage 1 VLR ratings + event results:
  85-ish = something (PRX), ZmjjKK (EDG), Wo0t (VIT); LEV won Masters
  London, G2 won Americas Stage 1, EDG won China Stage 1, BBL got a bump
  for their live EWC run. Attributes themselves are ORIGINAL estimates
  expanded by the build script — not scraped statistical profiles.
- **Agents**: real pools mapped onto the game's 13-agent registry
  (neon/waylay/iso->jett/raze/reyna, tejo/fade/gekko->sova/skye,
  astra/harbor/brimstone->omen/viper, kayo->breach,
  vyse/deadlock/sage/veto->killjoy/cypher, yoru->phoenix).
- **China tier-2** is thin (4 orgs, 2 partial); Pacific/EMEA/Americas
  tier-2 orgs are real but their rosters are the least-verified data here.

This pack exists for private play only (see GDD §9's amended non-goal);
if the project were ever published, remove `data/rosters/`.
