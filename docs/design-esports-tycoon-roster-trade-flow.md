## Doc: Esports Tycoon Roster Trade Flow

### Core loop
The core loop revolves around evaluating the performance and potential of roster members, deciding whether to keep them based on their stats, team synergy, and budget constraints, and trading them if necessary to improve the overall team composition. The loop is driven by the need to balance the team's strengths and weaknesses while staying within budget limits.

### Vertical slice
A vertical slice for this core loop would involve a single trade decision. The player receives a trade offer from another team, evaluates the offer against their current roster using specific synergy indicators, makes a decision, and sees the immediate impact on their team's stats, budget, and synergy. This slice can be completed in under an hour, fitting easily into a weekend test.

### Mechanics
- **Trade Trigger**: A notification appears indicating an incoming trade offer from another team. The player clicks to view the details.
- **Key Information Surfaced**:
  - Current roster member's stats (e.g., skill level, experience, morale).
  - Incoming player's stats.
  - Team synergy indicators showing compatibility scores between the new player and existing members based on skills and personalities.
  - Budget impact of accepting the trade.
- **Deciding Click**: The player clicks either "Accept" or "Decline" based on the evaluation of the trade offer.
- **After-State**: Upon acceptance, the new player joins the team, and the old player leaves. The player sees updated team stats, budget changes, and any adjustments in team synergy scores. If declined, the player receives a message confirming the trade was rejected, and the roster remains unchanged.
