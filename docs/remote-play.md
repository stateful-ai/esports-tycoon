# Remote play: hosting for friends outside your LAN

Goal: friends anywhere can open a browser and join your campaign lobby,
while your PC stays unreachable from the open internet.

## Security model (why this is safe)

The FastAPI app has **no authentication** — lobby join codes are the only
in-game gate — so the raw port must never face the internet. This setup
never exposes it:

- The game binds **127.0.0.1 only** (`serve.ps1 -Local`); no firewall rule,
  no port forwarding, no inbound connections. Nothing on your PC listens
  externally.
- A **Cloudflare Tunnel** (`cloudflared`) makes an *outbound* connection to
  Cloudflare's edge and relays visitor traffic to `127.0.0.1:8420`.
- **Cloudflare Zero Trust Access** sits in front of the public hostname
  (`esports.stateful-ai.com`): only emails on your allow-list can get
  through, verified by a 6-digit one-time PIN sent to that email. Everyone
  else is blocked at Cloudflare's edge and never touches the tunnel.
- The tunnel ingress serves only the one hostname; any other request through
  the tunnel gets a 404.
- DDoS/bot filtering comes free with Cloudflare's proxy.

Attack surface that remains: your allow-listed friends (post-PIN) and
Cloudflare itself. The app still applies its lobby-code flow on top.

## One-time setup

1. **Enable Zero Trust** (once per Cloudflare account, free plan):
   open <https://one.dash.cloudflare.com>, pick any team name.
2. **API token permissions** — the `CLOUDFLARE_API_TOKEN` in `.env` needs:
   - Account | **Cloudflare Tunnel | Edit**
   - Account | **Access: Apps and Policies | Edit**
   - Account | **Access: Organizations, Identity Providers, and Groups | Edit**
   - Zone (stateful-ai.com) | **DNS | Edit**

   Edit the token at <https://dash.cloudflare.com/profile/api-tokens> (or
   Manage Account -> Account API Tokens if it is an account token).
3. **Install cloudflared** (once): `winget install --id Cloudflare.cloudflared`
4. **Provision everything** (idempotent; re-run any time):

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\setup_remote_play.ps1 `
       -AllowedEmails you@example.com,friend1@example.com,friend2@example.com
   ```

   This creates/updates: the `esports-sim` tunnel, its ingress
   (`esports.stateful-ai.com -> http://127.0.0.1:8420`), the proxied DNS
   CNAME, the One-Time PIN login method, the Access app, and the
   `friends allow-list` policy.

   Tip: put the list in `.env` instead so re-runs pick it up automatically:

   ```
   REMOTE_PLAY_ALLOWED_EMAILS="you@example.com,friend1@example.com"
   ```

## Hosting a session

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\serve_tunnel.ps1
```

This starts `cloudflared` (connector token fetched fresh from the API, never
written to disk) and the game server bound to `127.0.0.1:8420`, and stops the
tunnel again when the server exits. Then:

1. You create the campaign/lobby as usual at `http://127.0.0.1:8420`.
2. Friends open **https://esports.stateful-ai.com**, enter their email,
   type the 6-digit PIN Cloudflare mails them (session lasts 24h), and join
   with your lobby code.

For LAN-only play, keep using `scripts\serve.ps1` as before — the two modes
are independent.

## Managing the allow-list

Re-run `setup_remote_play.ps1` with the new **full** email list (it replaces
the policy contents), or edit `REMOTE_PLAY_ALLOWED_EMAILS` in `.env` and
re-run with no arguments. Removing an email revokes new logins immediately;
to kill an existing session too, revoke it in the Zero Trust dashboard
(Access -> Applications -> esports-sim).

## Troubleshooting

- `HTTP 403` from the setup script: the API token is missing one of the
  permissions listed above.
- `access.api.error.not_enabled`: Zero Trust was never enabled — do step 1.
- Friends see Cloudflare error 1033: the tunnel is not running — start
  `serve_tunnel.ps1` (the site only works while you are hosting).
- Friends see a 502: tunnel is up but the game server is not — check the
  `serve.ps1` console window.
- PIN mail not arriving: check spam; the sender is Cloudflare
  (`noreply@notify.cloudflare.com`).

## Future hardening (optional, not yet implemented)

- Verify the `Cf-Access-Jwt-Assertion` header inside the FastAPI app
  (defense-in-depth if the server is ever mis-bound to `0.0.0.0`).
- Map the Access-authenticated email to a lobby seat automatically.
- Phase 2 (always-on hosting without your PC): small GCE VM + cloudflared,
  per the plan in the project notes.
