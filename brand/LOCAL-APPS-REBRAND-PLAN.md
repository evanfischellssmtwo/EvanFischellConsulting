# Local Apps → Evan Fischell Consulting Rebrand Plan

**Status:** PLAN — awaiting Evan's go
**Date:** 2026-07-02
**Executor:** Sonnet swarm (Workflow orchestration; one agent per service repo in the fan-out phase)
**Scope:** All EfischServer local apps' HTML/CSS chrome + all HTML pages across Projects

---

## 1. Goal

Replace the current house chrome look (warm cream surfaces + terracotta accent, serif titles)
with the locked Evan Fischell Consulting identity, gently — same layout, same components,
same class names, new skin:

- **Palette:** "Ink & Ember" — Ink 900 `#0B1926`, Ink 800 `#0F2233` (primary), Slate 600
  `#34505F`, Mist 300 `#9FB0BC`, Paper 50 `#F4F7F9`, Amber 500 `#E8912A` (signature accent),
  Amber 600 `#C1731A` (amber-on-light / hover), Amber 50 `#FBEEDC` (warm tint).
- **Typography:** IBM Plex Sans (300/400/500/600) + IBM Plex Mono for technical callouts.
  Replaces the current serif `.ef-title`.
- **Brand device:** the amber period. EF· monogram in the header logo slot; "Evan Fischell"
  600 / "Consulting" 300 lockup available for footers/about surfaces. All typographic —
  no image assets exist or are needed.
- **Rules to honor:** amber ≤10% of any surface; no second hue (desaturated slate/sage if a
  diagram truly needs one — never teal); colorblind-safe (accent separated by lightness);
  voice stays "agentic engineering", never "AI-powered".

Source of truth for tokens/voice: `EvanFischellConsulting/brand/BRANDING-PLAN.md`,
`COMPETITIVE-PALETTE-SCAN.md`, and the live `site/index.html` CSS variables.

## 2. Current architecture (what the swarm touches)

| Layer | Location | Distribution |
|---|---|---|
| Canonical chrome | `templates/efisch-frontend-template/static/chrome.css` (+ `chrome.js`) | **Vendored (copied)** into each service repo |
| Shared banner | `services/AppDirectory/banner/banner.css` + `banner.js` | Centrally served at `http://efisch.taild9c06b.ts.net/banner.css` |
| Per-app CSS | `claude.css` (WorkApps, HatchControl), `styles.css` (LocalLLM), `shows.css`/`quick.css`/`pc.css` (HatchControl) | Per-repo |
| Chrome contract tests | `services/{Svc}/tests/integration/test_*_smoke.py` | Per-repo — **currently assert the terracotta token `--accent:#d97757`** |

Vendored chrome copies (9): ApiObservatory, FreshbooksIntegration, HatchControl
(`src/home_control/static/`), LocalLLM, LogViewer, PayrollCalculator, SecretVault
(`src/secret_vault_portal/static/`), SkillsTopology, WorkApps (`src/work_apps/static/`).
AppDirectory generates its own chrome'd HTML and serves the banner.

**Deploy constraint (non-negotiable, per efisch-cicd):** every change lands on each repo's
`dev` branch → CI (unit + integration smoke) → auto dev-sync to the dev plane → human
acceptance → PR `dev`→`main` → merge triggers `Deploy-Service.ps1` to prod. No prod
worktree hand-edits. Swarm agents commit + push to `dev` only; PRs to `main` are opened
but merged by Evan (or explicitly authorized batch-merge).

**Isolation:** each service is its own repo in the Evan-Fischell org, so one swarm agent
per repo has zero file-collision risk. Only Phase 0 touches shared files (template +
AppDirectory) and runs as a single agent.

## 3. Design decisions baked into this plan

1. **Token remap, not a rewrite.** chrome.css keeps every selector and custom-property
   name (`--paper`, `--panel`, `--ink`, `--accent`, …); only values change. App-level CSS
   that reads the tokens inherits the rebrand for free.

   Light mode: Paper 50 surfaces, Ink 800 text, Slate 600 soft text, Amber 600 accent
   (contrast-safe on light), Amber 50 tints, Mist-derived hairlines.
   Dark mode: Ink 900/800 surfaces, Paper 50/Mist 300 text, Amber 500 accent.
   Semantic ok/warn/err hues: keep desaturated, re-tuned to sit on the new surfaces
   (no bright teal/green; warn may lean amber-adjacent but must stay distinct from the
   signature amber).

2. **Fonts served centrally from the hub**, like the banner: AppDirectory serves
   `fonts.css` + IBM Plex woff2 files at `http://efisch.taild9c06b.ts.net/fonts/`.
   Apps add one `<link>`. Rationale: base64-embedding Plex in 10 vendored chrome.css
   copies would bloat every repo; tailnet apps always have the hub. `chrome.css` declares
   the font stacks with system-sans fallback so nothing breaks if the hub is briefly down.

3. **Header brand component:** `.ef-logo` (currently an emoji tile) becomes the EF·
   monogram — ink plate, Plex 600 "EF", Amber 500 period — rendered in type via a new
   `.ef-mark` style in chrome.css. Apps may keep their emoji as a secondary glyph inside
   `.ef-titles` if identity-per-app matters; default is monogram-only. Hub button keeps
   `⌂ Hub`. Optional footer lockup class `.ef-lockup` ("Evan Fischell" 600 + "Consulting"
   300 + amber period) for app footers/about panes.

4. **Banner restyle, not rebuild:** `banner.css` is scoped under `.efbanner` with raw RGBA —
   restyle to Ink 900 strip, Mist text, amber accents for live-usage highlights and the
   favorites bar. `banner.js` behavior unchanged.

5. **Contract tests updated in the same commit as the vendored chrome** in each repo:
   the terracotta assertion (`--accent:#d97757`) becomes an amber assertion
   (`#C1731A`/`#E8912A` present in chrome.css). Template's smoke test updated in Phase 0
   so future apps inherit the right contract.

6. **HatchControl/home-control caution:** the hatch-control→home-control rename cutover is
   staged for that repo's next dev→main merge. The rebrand commit for this repo lands on
   `dev` *on top of* the staged rename — the swarm agent must not touch the rename files,
   and its PR notes both changes ship together.

7. **"Claude Edition" reskins:** `claude.css` (WorkApps) and `claude/claude.css` +
   `app.css` (HatchControl) redefine accent tokens to terracotta. These get re-pointed to
   the EFC tokens (or their overrides deleted where chrome.css now provides the value).
   `app.css` in HatchControl is likely dead — agent verifies and reports, doesn't delete
   unilaterally.

### Phase 0 review-pass addenda (Fable, 2026-07-02 — binding on Phase 1 agents)

- **Primary buttons** use the new `--btn-primary-bg/-bg-hover/-ink` tokens: darker
  amber + white text on light (AA ~4.9:1), Amber 500 + **ink** text on dark (~7:1).
  White-on-amber is banned (failed contrast both themes). App CSS that styles its
  own primary-ish buttons must adopt these tokens.
- **`.ef-logo` is now an ink plate** (matches `.ef-mark`), not an amber gradient —
  amber is never a fill.
- **Default `.ef-chip` is neutral**; the amber chip is opt-in via `.ef-chip.accent`.
  Phase 1 agents: where an app's UI relied on the old accent-tinted default chip
  as a deliberate highlight, add `.accent`; otherwise leave chips neutral.
- `.ef-btn` has a `:focus-visible` outline; keep it when overriding buttons.

## 4. Phases

### Phase 0 — Foundation (single agent, sequential; ~1 agent)
Repo scope: `templates/efisch-frontend-template` + `services/AppDirectory`.

1. Build the EFC chrome: rewrite token values in canonical `chrome.css` (light + dark),
   swap serif title to Plex Sans 600, add `.ef-mark` (EF· monogram) and `.ef-lockup`,
   update the template's example `index.html` and smoke-test contract assertion.
2. Add Plex font serving to AppDirectory (`/fonts/fonts.css` + woff2; download from
   Google Fonts / IBM's GitHub release — open license). Restyle `banner.css`.
   Restyle AppDirectory's own generated hub pages (cards, deploy widget) with the new chrome.
3. Produce a **preview artifact**: a single self-contained HTML page showing the new
   chrome — header + monogram, cards, chips, table, buttons, banner strip — in light and
   dark, side-by-side with amber-usage callouts. Publish to ReviewPortal for phone review.
4. Push AppDirectory + template changes to their `dev` branches; CI green.

**GATE → Evan reviews the preview and the hub on the dev plane. No fan-out until approved.**
(This is the one aesthetic judgment call; everything after is mechanical propagation.)

### Phase 1 — Service fan-out (sonnet swarm, one agent per repo; 9 parallel agents)
Repos: ApiObservatory, FreshbooksIntegration, HatchControl, LocalLLM, LogViewer,
PayrollCalculator, SecretVault, SkillsTopology, WorkApps.

Each agent, in its own repo, on `dev`:
1. Vendor the approved `chrome.css` + `chrome.js` from the template into the app's
   `static/` dir.
2. Add the hub `fonts.css` `<link>` next to the existing banner link in the app's HTML
   head (inline-Python HTML for most; static `index.html` for WorkApps).
3. Update the header block: `.ef-logo` emoji → `.ef-mark` monogram (keep app emoji in
   `.ef-sub`/title area if it aids recognition).
4. Reconcile app-level CSS (`claude.css`, `styles.css`, `shows.css`, `quick.css`,
   `pc.css`): re-point terracotta/cream overrides to EFC tokens; delete overrides now
   redundant with chrome.css; flag suspected-dead files in the report instead of deleting.
5. Update the smoke-test chrome assertion (terracotta → amber).
6. Run the repo's unit + integration tests locally; fix regressions within scope.
7. Commit ("Rebrand chrome to Evan Fischell Consulting theme"), push `dev`, confirm CI
   green and dev-sync fired.
8. Return a structured report: files changed, overrides removed, dead-code flags,
   screenshots-worthy pages, CI run URL, dev-plane URL.

Structured-output schema per agent: `{repo, branch, ci_green, files_changed[],
overrides_removed[], flags[], dev_url, notes}`.

### Phase 2 — Verify swarm (sonnet, one verifier per service; runs pipelined behind Phase 1)
For each service on the dev plane: load the page, assert (a) Plex fonts active,
(b) amber accent present and ≤ tasteful usage, (c) dark-mode toggle works, (d) banner
renders, (e) favorite/hub buttons work, (f) no console errors, (g) no leftover terracotta
(`#c96442`/`#d97757`/`#8f4226` greps across served CSS). Verifier returns pass/fail +
defect list; failures loop back to the repo agent (max 2 repair rounds).

### Phase 3 — Long-tail HTML (sonnet swarm, small; 2–4 agents)
"All HTML pages across all projects," gently:
- **ReviewPortal** document chrome (generated briefing/report pages): restyle wrapper to
  EFC tokens + lockup footer.
- **Experiments** with HTML frontends (AiForMom, CsioBriefing, DataLakeBriefing/lakehouse
  briefing, StaffHoursPortal): apply tokens + monogram header where a header exists; these
  are not registered services, so direct dev-branch commits with lighter testing. Note:
  DataLakeBriefing is going public at lakehouse.efisch.dev — flag for Evan whether public
  pages should carry EFC branding or stay unbranded.
- **Skip:** SSM-branded work (ssm-brand governs those), the EFC site/deck themselves
  (already branded), design-history artifacts (palettes.html etc.).

### Phase 4 — Promotion (human-gated)
0. **Deploy AppDirectory FIRST.** Apps link fonts from the prod hub origin
   (`/fonts/fonts.css`), which 404s until AppDirectory's dev branch (fonts routes +
   banner restyle) reaches main/prod. Until then every rebranded page falls back to
   system fonts (graceful — Plex stacks have fallbacks). Phase 1/2 verifiers flagged
   this on LogViewer/WorkApps/SecretVault; it is NOT a repo defect.
   **Same for the banner:** the prod hub still serves the pre-rebrand terracotta
   `banner.css`/`banner.js` (favorites-pill hover `rgba(201,100,66)`/`rgba(218,119,86)`)
   until AppDirectory promotes. The dev banner is already amber-clean; the
   Phase 1b control-sweep verifiers flagged the *prod* banner on every app — resolves
   with the AppDirectory deploy, not a per-app fix.
1. Evan does acceptance on the dev plane (hub link tour).
2. Swarm opens PRs `dev`→`main` across all touched repos with a uniform description
   (before/after, contract-test change, rollback = revert PR).
3. Evan merges (or authorizes batch-merge); `Deploy-Service.ps1` handles prod rollout
   repo-by-repo; verify `/health` + spot-check prod pages.
4. Post-deploy: update `app-templates` skill notes if the contract text mentions
   terracotta; record the rebrand in memory.

## 5. Swarm execution notes

- Phase 1 agents: `model: sonnet`, isolated by repo (no worktree isolation needed — repos
  don't overlap). Effort: default; Phase 0 agent may run higher.
- Pipeline Phase 1→2 per-repo (verify each repo as soon as its CI is green) rather than
  barriering on all nine.
- Budget guess: Phase 0 ~1 agent-run + preview; Phase 1 ~9; Phase 2 ~9 (+ repairs);
  Phase 3 ~3–4. Roughly 25 sonnet agent-runs end to end.
- Every agent prompt embeds: the token table (§1), the amber ≤10% rule, "token remap not
  rewrite", the contract-test change, and the dev-branch-only rule. Agents never merge to
  `main`, never touch prod worktrees, never edit another repo.

## 6. Risks

| Risk | Mitigation |
|---|---|
| New palette looks wrong in practice | Phase 0 gate: preview + hub-only before 9-repo fan-out |
| CI contract tests block on terracotta assertion | Test updated in the same commit as the vendored chrome, per repo |
| HatchControl rename collision | Rebrand lands on top of staged rename on `dev`; PR ships both; agent forbidden from touching rename files |
| Hub-served fonts as single point of failure | System-sans fallback stacks in chrome.css |
| App-specific CSS fights new tokens (contrast bugs) | Phase 2 verifier checks every page in light + dark; repair loop |
| Amber overuse (brand rule violation) | Explicit ≤10% rule in every prompt; verifier checks accent usage |
| SkillsTopology has no GitHub repo / CI (discovered in Phase 1) | Rebrand committed on local dev; terracotta-in-decimal-RGB fixed in repair; CI/CD onboarding backlogged as a separate decision — it CANNOT ship via Phase 4's PR flow until onboarded |
