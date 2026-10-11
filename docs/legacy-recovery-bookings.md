# Legacy recovery booking seasons

Before schema 38, `recovery_booked_by` stored the last booking week per club
and survived season rollover. A week alone cannot establish a booking season.

The schema 37-to-38 migration preserves existing explicit season stamps. For
an unqualified booking it assigns the saved season only when one of these
facts establishes ownership:

- The save is in season one, so there is no previous season to confuse.
- An accepted `recovery` or `book_recovery` ActionRecord has the same club ID,
  saved season, and stored booking week. Manager identity is not club identity;
  records from another manager's club never qualify this club's booking.
- The retained news contains the exact deterministic recovery booking sentence
  stamped with that season and week, and the club name uniquely identifies a
  saved club. This also covers AI bookings, which do not emit human actions.

News retains only 60 entries. Missing evidence is therefore unknown, not proof
of a stale booking. Unknown later-season bookings keep their historical week
without a season stamp and do not block recovery. A fresh paid booking records
both fields immediately and prevents a duplicate in that season and week.
This choice can permit one extra paid recovery for an unverifiable old booking;
it avoids falsely denying recovery based on a prior season's matching week.

The migration and eligibility rules use saved facts only, with no randomness,
wall-clock data, or inferred campaign replay. Save/load round trips retain both
unknown and qualified bookings. MEDIA effect defaults, tier-meta defaults, and
the preceding badge-evidence migration are unchanged.

Regression coverage is authored in `tests/test_recovery.py`. All local tests,
hooks, syntax/lint checks, validators, simulations, and app runs were skipped
for this change at the user's explicit request. The added tests are UNRUN.
