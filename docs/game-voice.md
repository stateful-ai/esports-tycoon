# Game voice: competitive, credible, online

## Purpose

This is the copy standard for **ESports Simulator**. It gives the game a recognisable esports voice without making a management sim sound like a stream chat. It applies to deterministic templates, UI copy, news, social posts, player conversations, media decisions, and optional LLM rewrites.

The manager runs a professional club: results, payroll, development, reputation, and people matter. The world around that work is competitive gaming: smart, fast, public, a little petty, and permanently online.

**Core line:** run the club like a pro; let the scene talk like a scene.

## The voice in one pass

| Quality | What it means on the page | What it is not |
| --- | --- | --- |
| Competitive | Precise about form, preparation, pressure, and the result. | Empty hype or macho posturing. |
| Credible | Decisions name a real trade-off and use sports-business language. | Corporate filler. |
| Online | Social copy may be clipped, referential, playful, or lightly meme-aware. | A wall of stale slang. |
| Human | People have a point of view; pressure and pride have consequences. | Melodrama or fake inspiration. |
| Dry when it matters | Bad results and difficult decisions get room to land. | Relentless irony or mockumentary narration. |

The default register is **calm, direct, and observant**. A joke earns its place by revealing the speaker, result, or public mood. It never replaces a fact the manager needs to act on.

## Channel rules

### Product UI, finance, and actions: operator voice

This is the Football Manager / motorsport-team-principal layer. Use plain, specific verbs and name the consequence before the flavour.

- "Renew contract"
- "Registration closes this week. Confirm your six-player pool."
- "Sponsor relation improved; player trust fell."
- "Review the VOD before changing the game plan."

Do not use meme language in buttons, validation, warnings, tooltips, tables, or irreversible choices. "Lock in" is a social post; "Confirm lineup" is an action.

### News, match reports, and analysis: desk voice

Write like a sharp esports desk that watched the match and checked the box score. Lead with what happened, then name the decisive pattern. Use restrained colour, not a canned catchphrase.

- "Nexus closed the series 2-1 after winning four of five retakes on Foundry."
- "The lead disappeared quickly. The review will not."
- "A 1.31 from Raze decided the opener; the rest of the series stayed tight."

Avoid broadcaster hyperbole ("absolute scenes", "legendary", "insane") unless it is genuinely a rare, data-supported achievement. Do not call a routine win "business as usual" or a loss "cooked" from the narrator.

### Social feed: character and community voice

The social feed is where gamer culture and meme culture live. Posts are short, authored, and grounded in the week's actual result, player, patch, or event. The org account is controlled; players vary by personality; outlets are quick and factual; meme accounts are allowed to be a little louder.

- Player after a loss: "gg. review tomorrow. not opening the mentions tonight."
- Org account: "2-1 over Helix. Foundry was the difference. back next week."
- Clip account: "three retakes, one round. Nexus found the door eventually."
- Meme account after an upset: "Helix fans have entered the VOD-review phase of grief."

Use contemporary gaming language sparingly and in-character: `gg`, `VOD`, `eco`, `force`, `retake`, `clutch`, `diff`, `locked in`, `washed`, `copium`. It should be understandable from context and never be the only information in the post. Prefer an enduring phrase over a trend with a one-week shelf life.

### Media decisions, player talks, and board moments: room voice

These are professional conversations under pressure. Let the speaker be warm, cold, evasive, or blunt, but keep the option legible and the outcome grounded.

- "Back the player publicly" - protects trust; invites scrutiny.
- "Set a higher standard for the next block" - clear, but may land badly.
- "Keep this inside the room" - lowers noise; may look evasive.

Avoid therapy-speak, HR euphemism, and performative cruelty. The manager is making a call, not delivering a viral monologue.

## Pacing

Copy should move at the pace of a weekly campaign.

1. **Routine weeks:** brief and useful. One fact, one implication, then get out of the way.
2. **Match day:** build anticipation with the matchup and one concrete stake; do not pre-spend the drama.
3. **After a result:** state the result first. Give a standout or the key failure second. Let silence handle ordinary losses.
4. **Turning points:** only rivalries, eliminations, title races, debuts, significant records, and public commitments earn elevated language.
5. **Feed cadence:** a small number of distinct posts beats a busy timeline. Never stack several variants of the same joke or celebrate minor milestones.

Default lengths: labels 2-5 words; helper text 1 sentence; news 1-3 sentences; social posts 1-2 short lines; decisions under 100 words total.

## Vocabulary guardrails

Use game-native language consistently: **series, map, round, roster, lineup, bench, fixture, form, VOD, scrim, buy, eco, force, entry, lurk, retake, clutch, anti-strat, split, playoffs, sponsor, supporter, and supporter sentiment**.

Use the in-world terms established by active game data and serializers. Do not reintroduce the retired "Vector Strike", "Operatives", or "Chirper" terminology from old prototype material.

Avoid:

- generic announcer hype: "epic", "legendary", "unbelievable";
- stale or over-broad memes: "GG EZ", "sigma", "rizz", "main character energy", "it's giving", "slay";
- slang without a fact: "they're cooked", "fraud watch", "ratio";
- corporate fog: "leverage synergies", "unlock value", "stakeholder alignment";
- real-player, real-org, or real-game references in fictional-world copy.

Normal sentence case is the default. All caps are for a quoted fan reaction or a rare social beat. Emoji belong to an authored social personality, not system or editorial copy.

## Before-and-after calibration

| Avoid | Prefer |
| --- | --- |
| "Business as usual: Helix dealt with, 2-0." | "Helix were handled 2-0. The second map never got loose." |
| "Questions are being asked after three straight defeats." | "Three straight losses have put the call sheet under review." |
| "The timeline is in SHAMBLES." | "The upset has given the timeline plenty to work with." |
| "Say you expect to win." | "Set winning as the public standard." |
| "The player is letting the team down." | "Recent form has made the player the easy target." |
| "New week. Back to work." | "New week. Scrims begin Monday." |

The preferred line may still be sharp. It should feel earned by the situation, not selected from a universal esports-slang list.

## Implementation contract

1. Deterministic templates remain the canonical fact layer. Optional LLM rewrites may change phrasing, never facts, choices, or consequences.
2. Every LLM prompt that writes player-facing prose must receive this channel's register, the grounding rule, and the banned-language list.
3. New text templates need a channel owner: `operator`, `desk`, `social`, or `room`. Do not reuse social copy in product UI.
4. Template review asks: Is the fact clear? Does this speaker earn this slang? Would the line still work after this meme expires? Is it distinct from the last nearby line?
5. Keep the existing ASCII requirement for CLI output. Web copy may use normal punctuation but should not depend on emoji for meaning.

## First cleanup pass

The highest-value follow-up is a focused template audit, not a blind global find-and-replace:

1. **Narrative (`manager/narrative.py`):** replace generic catchphrases and passive pundit phrasing with concrete desk-language variants.
2. **Social (`manager/social.py`):** retain in-character gamer culture, but replace all-caps and broad meme boilerplate with result-specific posts; separate org, player, outlet, and meme-account voices.
3. **Decisions and talks (`manager/media_events.py`, `manager/flavor_events.py`, `manager/talk.py`):** make labels decisive and professional; reserve the more personal language for prompts and replies.
4. **LLM sidecars (`web/llm_social.py`, `web/llm_flavor.py`, `web/llm_talk.py`):** encode the correct channel rule in each system prompt so generated phrasing cannot drift from the deterministic fallback.

This document supersedes `docs/salvage/tone_and_cast_lock.md` as the active voice authority. That file is retained as historical prototype material only.

