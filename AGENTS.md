# EvanFischellConsulting

Evan's post-SSM consulting venture. Brand strategy and identity live in `brand/`
(source of truth: `brand/PITCH.md` + `brand/BRANDING-PLAN.md`); the public
landing site lives in `site/`.

## Brand quick facts (do not drift)

- Voice: executive-plain, **never tech-first**; say "agentic engineering" /
  "embedded agents", minimize/omit "AI". "Rationalize the stack" is internal-only.
- Tagline: **"It shouldn't be hard."** — always with the **amber period** (the
  brand device: wordmark and tagline both end with it).
- Identity: IBM Plex Sans (+ Plex Mono); lockup "Evan Fischell" 600 / "Consulting"
  300 / amber period; tokens Ink `#0F2233` · Slate `#34505F` · Mist `#9FB0BC` ·
  Paper `#F4F7F9` · Amber `#E8912A` (accents only, ≤10%, no second hue).
- Brand HTML pages embed IBM Plex as base64 — no external font dependency.

## Web presence (durable state — verified 2026-07-02)

| Thing | Value |
|---|---|
| Canonical host | `https://evanfischellconsulting.com` |
| Redirects → canonical | `www.evanfischellconsulting.com`, `evanfischell.com`, `www.evanfischell.com` (301 at app layer, host-based) |
| Hosting | GCP Cloud Run service **`efc-site`**, project **`efc-prod`** (business org — see below), region `us-central1` |
| Service URL | `https://efc-site-1037040972707.us-central1.run.app` |
| Source | `site/` (Flask + gunicorn; `/` landing page, `/deck` unlisted pitch deck, `/api/health`, embedded agent below) |
| Embedded agent | Gemini `gemini-3.1-pro-preview` via `google-genai`; **easter-egg entry = the amber periods** (hero tagline + footer wordmark, `.egg` class) opening a chat drawer. Endpoints: `POST /api/agent/chat` (JSON protocol: `{reply, action}`), `POST /api/agent/page` (custom one-page brief), `GET /p/<id>` (serves generated pages, in-memory, noindex). Knowledge base + behavioral contract: **canonical `brand/KNOWLEDGE-BASE.md`** → deploy artifact `site/kb.md` (re-copy each deploy, like the deck) |
| Agent spend posture | **PUBLIC Gemini spend, capped** (Evan-directed 2026-07-02; differs from the personal-project IP-gate pattern): `CHAT_DAILY_CAP=200`, `PAGE_DAILY_CAP=15`, in-memory (reset on cold start), `--max-instances 1 --no-cpu-throttling`, gunicorn `--timeout 180`. Secret: `GEMINI_API_KEY` in **efc-prod Secret Manager** (value mirrored from the personal project's secret), compute SA has accessor. Gemini 3.1 Pro must run with a bounded `thinking_budget` (thoughts eat `max_output_tokens` — truncation shows up as fallback replies) |
| Agent eval | Red-team review (20 probes, evaluations, Evan feedback rows): `reviews/agent-eval-2026-07-02.html`, ReviewPortal asset `2a677ad78adbbffd` |
| Feedback widget | Point-and-comment snippet (`<script id="efc-fb-widget">`) embedded in `site/index.html`, `brand/PITCH-DECK.html` (→ `deck.html` artifact), `brand/ONE-PAGER.html`. Activate with **`?fb=1`** URL param (or Ctrl+Shift+`.`): click an element → comment → "Copy for Claude" copies comment + CSS path + opening tag + text excerpt for pasting into chat. Injector script pattern in session scratchpad; re-inject after any full-file rewrite (marker: `efc-fb-widget`). **Gotcha:** `navigator.clipboard` needs a secure context — the ReviewPortal is plain HTTP, so any copy-to-clipboard feature on portal-hosted pages MUST ship the `fbCopy`/`fbCopyLegacy` (`execCommand`) fallback. |
| Unlisted deck | `evanfischellconsulting.com/deck` — audience-switchable (`?aud=exec\|tech`, `&lock=1`), noindex, no inbound links. **Canonical = `brand/PITCH-DECK.html`** (+ `PITCH-DECK.spec.yaml` as editing source); `site/deck.html` is a deploy artifact — re-copy from canonical before each deploy |
| Deploy | `gcloud --configuration=efc run deploy efc-site --source . --project efc-prod --region us-central1` from `site/` |
| **Business org** | `evanfischellconsulting.com`, org ID `123975604522`, created 2026-07-02; admin `evan@evanfischellconsulting.com` (Workspace). gcloud configuration **`efc`** = that user (headless agent path for this org — no SA key yet; org default `iam.disableServiceAccountKeyCreation` likely applies) |
| Org project | `efc-prod` (number `1037040972707`) — billing: personal "My Billing Account" `01A0BE-3E92C0-0FF763` via `billing.user` grant to evan@ (revoke when business billing lands) |
| Org policy note | Org keeps domain-restricted sharing (secure default); **`efc-prod` has a project-level `iam.allowedPolicyMemberDomains: allowAll` override** (required for the public `allUsers` invoker). Evan applied grant+override himself 2026-07-02. |
| Legacy | `efc-site` also still deployed in `efisch-eternal-storage` — now serves ONLY the `evanfischell.com` (+www) mappings as a 301 redirect host, until that domain is verified for evan@ and moved |
| DNS provider | Cloudflare (authoritative NS `kanye.ns.cloudflare.com` / `lisa.ns.cloudflare.com`), both zones on Evan's account |
| DNS records (each zone) | apex: 4× A `216.239.32.21/34/36/38` + 4× AAAA `2001:4860:4802:32/34/36/38::15`; `www`: CNAME → `ghs.googlehosted.com` |
| Proxy/TLS policy | **DNS-only (gray cloud)** — Google-managed TLS via Cloud Run domain mappings. Do NOT orange-cloud these records. |
| Domain verification | Both domains Google-verified under `edfischell@gmail.com` (`gcloud domains list-user-verified`) |
| Cloudflare changes | via `efisch_mint` minted tokens (Zone Read + DNS Write, short TTL, auto-revoke) — never the account-admin credential directly |
| Email | `evan@evanfischellconsulting.com` shown on the site — **routing NOT yet configured** (Cloudflare Email Routing pending; see open items) |

## Open items

- **Email:** Google Workspace is on the domain (MX `smtp.google.com` already set,
  Workspace "new and mostly unconfigured"). Remaining hygiene: SPF, DKIM, DMARC
  records (none present as of 2026-07-02) + confirm the `evan@` mailbox works.
  Cloudflare Email Routing NOT used — superseded by Workspace.
- **evanfischell.com redirect domain:** mappings still live in the personal
  project (cert was still provisioning as of cutover). To move into `efc-prod`:
  add `evan@` as verified co-owner of the domain in Search Console (Gmail owns
  the verification), then recreate mappings.
- **Agent credential for efc-prod:** currently the `efc` gcloud user config.
  Decide later: SA + key (needs org-policy exception for key creation) vs.
  keeping the user-config path vs. workload identity.
- Monogram is provisional ("EF." plate); M1 "resolve" mark is the upgrade candidate.
- Platform product name, personal visibility level, acquirer framing — undecided
  (see `brand/BRANDING-PLAN.md` §7).
- Pitch deck = separate future conversation (Phase 3).
