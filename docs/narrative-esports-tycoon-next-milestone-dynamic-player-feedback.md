## Doc: Esports Tycoon Next Milestone - Dynamic Player Feedback

### Voice & tone
The voice should be enthusiastic, supportive, and slightly competitive, reflecting the high-stakes environment of esports. It should motivate the player without being overly aggressive. Sample line: "Brilliant trade! You've significantly improved your team's synergy and offensive capabilities."

### Authored content
The authored content includes scripted feedback for common actions such as hiring, firing, and trading players. Specific lines include:
- Hiring: "Welcome aboard! Your new recruit brings a fresh edge to the team."
- Firing: "Tough call, but sometimes you need to make room for better talent."
- Trading: "Great move! Your team is looking stronger already."

### Dynamic moments
#### Player-specific feedback on trades
- **What gets generated**: Customized feedback for each trade decision made by the player, including praise or constructive criticism based on the outcome.
- **Structured shape returned**: 
  - `feedback`: string (the customized feedback line)
  - `tone`: string (positive, neutral, or negative)
- **Fallback when generation fails or is too slow**: Use a generic positive feedback line, e.g., "Great move! Your team is looking stronger already."
- **Token budget**: 10 tokens for feedback generation.
- **Sample output**:
  ```json
  {
    "feedback": "Brilliant trade! You've significantly improved your team's synergy and offensive capabilities.",
    "tone": "positive"
  }
  ```

This dynamic moment aims to make the player feel like they are actively shaping the scene by receiving personalized feedback that acknowledges their strategic decisions, thereby enhancing engagement beyond mere spreadsheet management.
