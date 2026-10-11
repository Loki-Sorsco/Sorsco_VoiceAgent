# Arkus — Execution Plan (from Plan of Action v2.0)

> Source: *Arkus Plan of Action v2.0* (2 Oct 2026). That document is the **what and why**.
> This document is the **how and when**: decisions to lock, team tracks, sprint-by-sprint
> tickets with acceptance criteria, the critical path, and the corrections the v2 spec needs
> before engineering starts.
>
> Assumed team (same as the spec): **FE** (frontend-heavy), **PL** (backend / platform),
> **DI** (backend / data + infra), **AI** (analysis + LLM), **PD** (founder: product + design).
> Sprints are 2 weeks. Week numbers are relative to kickoff.

---

## 0. Summary

| Milestone | Spec says | This plan | Why the difference |
|---|---|---|---|
| Walking skeleton (sign up → install App → see 1 repo's endpoints) | — | **Week 4** | De-risk the whole pipeline early, before polishing anything |
| Phase 1 exit: map for 20 real repos, ≥90% recall | Week 8 | Week 8 | — |
| Phase 2 exit: DB + Ask (read) | Week 12 | Week 12 (Postgres only) | MySQL moves to after launch |
| **MVP private beta** | Week 14 | **Week 16** | Adds a 2-week hardening sprint; the spec's phases 2 and 3 overlap with no slack |
| Suggestions + Plans + Hand off (Free write path) | Week 18 | Week 20 | Shifted by the hardening sprint |
| MCP server (read) | Week 19 | Week 20 | — |
| **Pro agent: code PRs** | Week 24 | **Week 26** | — |
| Pro agent: DB migrations + write queries | Week 26 | Week 28 | — |
| Architect (new project) | Week 28 | Week 30 | — |
| Team / Enterprise | 28+ | 30+ | — |

**Fixed order (do not reorder):** read-only first → Free write path (guides) → MCP → Pro agent.
The Pro agent is only safe once RBAC, audit, plans and approvals already work.

---

## 1. Corrections to the v2 spec (fix before Week 1)

These are inconsistencies or risks I found reading the spec end to end.

| # | Spec says | Problem | Decision |
|---|---|---|---|
| C1 | DB proxy in **Go**, SQL guard uses **sqlglot** (Python) | sqlglot can't run inside a Go service without a Python sidecar on the hot path | Guard in Go: **`pg_query_go`** (libpg_query, the real Postgres parser) for Postgres; **TiDB parser** for MySQL later. Keep `packages/sqlguard` as the shared rules + adversarial corpus, run in CI against the Go guard. sqlglot is still used offline for eval tooling only |
| C2 | Audit log in **ClickHouse** from Phase 0 | Adds a datastore before anyone needs one | Phase 0–2: Postgres `audit_events` table, append-only (trigger rejects UPDATE/DELETE) + per-row hash chain. Move to ClickHouse in Phase 3 together with metrics, keeping the same `audit.write()` interface |
| C3 | Phase 2 (wk 8–12) and Phase 3 (wk 11–14) overlap; MVP at wk 14 | No buffer for beta-blocking bugs, security review, or metering | Add a **Hardening sprint (wk 15–16)**; MVP = wk 16 |
| C4 | P0 extractors = Node/TS **and** Python **and** frontend callers **and** OpenAPI in ~5 weeks | Too broad for one AI/analysis engineer to reach 90% recall | P0 = **Next.js, Express, NestJS, Prisma, Drizzle, OpenAPI, fetch/axios/React Query**. P0.5 (wk 7–8, if benchmark is green) = FastAPI + SQLAlchemy. Django, Fastify, Hono, tRPC follow after launch. Choose based on the first 20 beta users' stacks (decision D2) |
| C5 | Phase 2: Postgres **and** MySQL | Two drivers, two parsers, two introspection layers | MVP = Postgres only (covers Supabase, Neon, RDS, Cloud SQL). MySQL/PlanetScale goes in sprint S9 |
| C6 | Health: synthetic + Sentry/Datadog/New Relic/Grafana/CloudWatch/Vercel/... + OTLP by wk 14 | Too many integrations | MVP health = **synthetic checks + Sentry + OTLP ingest**. Other integrations are added one per sprint after launch |
| C7 | Model IDs: `claude-haiku-4-5` for small tasks | Out of date | LLM gateway maps **roles → models** (`planner`, `coder`, `sql`, `summarizer`) so model IDs live only in config. Defaults: `claude-opus-5-5` (planner/coder), `claude-sonnet-5-5` (sql), `claude-haiku-5-5` (summarizer) |
| C8 | Workflows: BullMQ for MVP, Temporal "from Phase 6" | Migrating running workflows is painful | Use BullMQ **only** for stateless jobs (index, introspect, health ticks). Every multi-step, approval-gated flow (plan ship, agent run, migration apply) starts on Temporal from day 1 of Phase 6. Nothing gets migrated |
| C9 | Design builds **Build** path first; plan builds **Import** first | The design has no Import screen (02/06 "not designed yet") | PD designs **02 Start / 06 Import** analysis stream in Week 0–2. It is on the critical path for the wk 4 skeleton |

---

## 2. Decisions to lock in Week 0

Each decision has an owner and a default. If nobody objects by end of Week 0, the default stands.

| ID | Decision | Default (recommended) | Owner |
|---|---|---|---|
| D1 | Primary early customer | Agencies + non-technical founders (spec §17.2) | PD |
| D2 | Exact P0 frameworks | See C4; confirm by surveying 20 beta-list users' repos | PD + AI |
| D3 | Sandbox provider | Managed (**E2B** or Daytona) for Phases 6–7; self-host Firecracker post-PMF | DI |
| D4 | Free plan + production DB | Schema-only for prod on Free | PD |
| D5 | Launch region | One AWS region (e.g. `ap-south-1` or `us-east-1` based on beta users), EU region planned | DI |
| D6 | Cloud | **AWS**: KMS, NAT with static egress IPs for the DB proxy, ECS/Fargate or EKS | DI |
| D7 | Auth provider | **WorkOS AuthKit** (SSO/SCIM come built in for Enterprise later) — or Clerk if faster to ship | PL |
| D8 | API framework | **Fastify + tRPC** (internal UI) + REST (public/MCP); TypeScript everywhere except dbproxy + connector (Go) | PL |
| D9 | Metadata DB ORM / migrations | **Drizzle** + SQL migrations (RLS policies written in raw SQL) | PL |
| D10 | Monorepo tooling | **pnpm workspaces + Turborepo**; Go modules in `services/dbproxy`, `connector/` | DI |
| D11 | Tree-sitter runtime | Node bindings inside the indexer workers (one language for extractors) | AI |
| D12 | Product name / domain / GitHub App name | "Arkus" working name; register GitHub Apps `arkus-read` and `arkus-write` early (names are first-come) | PD |
| D13 | Repo for Arkus | **New repo** `arkus` (not this voice-agent repo) | PD |

---

## 3. Team tracks

Four parallel tracks. Each owner keeps their track's acceptance tests green.

| Track | Owner | Owns (packages/services) |
|---|---|---|
| **Shell & UX** | FE | `apps/web` — shell, map, all screens, ⌘K |
| **Platform** | PL | `apps/api`, `packages/authz`, GitHub App, plans engine, MCP |
| **Data & Infra** | DI | infra (Terraform), CI/CD, `services/dbproxy`, `connector/`, health, ClickHouse, sandboxes |
| **Analysis & AI** | AI | `services/indexer`, `packages/extractors`, `packages/graph`, LLM gateway, NL→SQL, agent |
| **Product & Design** | PD | screens not yet designed, beta recruiting, benchmark repo labelling, pricing |

---

## 4. Repo bootstrap (Sprint 1, Day 1–3)

```
arkus/
  apps/web               Next.js (App Router) + Tailwind + shadcn/ui + React Flow + ELK (worker)
  apps/api               Fastify + tRPC (UI) + REST (public, MCP); authorize() middleware
  services/indexer       BullMQ workers: clone → scrub → detect → extract → resolve → persist → diff
  services/dbproxy       Go: introspection, SQL guard (pg_query_go), execution, SSRF guard
  services/health        synthetic checker (multi-region), OTLP receiver, integration pollers
  services/agent         (Phase 6) Temporal workers, sandbox orchestration, validators
  services/mcp           (Phase 5) MCP server: stdio npm package + remote HTTPS/OAuth
  connector/             (Phase 7) Go, outbound-only mTLS tunnel, open source
  packages/graph         node/edge types, traversal (impact analysis), snapshot diff
  packages/authz         can(), permission matrix, exhaustive matrix tests
  packages/extractors    one folder per framework + fixtures/ + benchmark runner
  packages/sqlguard      rule definitions + adversarial corpus (consumed by Go guard tests)
  packages/llm           gateway client: roles→models, quotas, redaction, cost metering
  packages/db            Drizzle schema, SQL migrations, RLS policies
  packages/ui            shared shadcn components, design tokens from Arkus v3 design
  infra/                 Terraform: VPC, RDS Postgres, Redis, KMS, NAT (static egress IPs), ECS
  .github/workflows      lint, typecheck, unit, authz-matrix, isolation, extractor-benchmark, sqlguard-corpus
```

**CI gates that must exist from Sprint 1** (they get stricter later, never looser):
`lint` · `typecheck` · `unit` · `authz-matrix` (every role × action × env × layer) · `tenant-isolation`
(two orgs, every API route, assert no cross-read) · later: `extractor-benchmark` (S2), `sqlguard-corpus` (S5).

---

## 5. Sprint-by-sprint plan

Ticket format: `ARK-xxx` · **owner** · task — *acceptance criteria*.
Every sprint ends in a demo built on real repos and databases, not mocks.

### Week 0 — Kickoff (before Sprint 1)
- **PD** — Lock decisions D1–D13. *Decision log committed.*
- **PD** — Design **02 Start / 06 Import** analysis stream: progress (repos → frameworks → routes → models → bindings), unresolved ⚠ chips, confidence on each binding. *Figma frames approved.*
- **PD + AI** — Shortlist 50 open-source benchmark repos (Next.js, Express, NestJS, Prisma, Drizzle; plus 10 FastAPI). *Repo list + licence check.*
- **PD** — Beta waitlist page and outreach to 50 agencies/founders. *Target: 20 committed beta teams by wk 12.*

### Phase 0 — Foundations

**Sprint 1 (wk 1–2)**
| ID | Owner | Task | Acceptance |
|---|---|---|---|
| ARK-001 | DI | Monorepo, Turborepo, CI pipelines, preview deploys for `apps/web` | PR → green CI → preview URL |
| ARK-002 | DI | Terraform: VPC, RDS Postgres, Redis, KMS key, NAT with static egress IPs, staging + prod | `terraform apply` from CI; egress IPs documented |
| ARK-003 | PL | Metadata schema (spec §16.2) for orgs, users, memberships, projects, environments, role_defs, role_bindings, sources; RLS `org_id = current_setting('arkus.org_id')` on every table | Migration applies; a query without the org setting returns 0 rows |
| ARK-004 | PL | Auth (WorkOS/Clerk): sign up, login, org create, invites, MFA flag | Two orgs sign up independently |
| ARK-005 | PL | `packages/authz`: `can(user, action, resource)`, built-in roles Owner/Editor/Reviewer/Viewer × Dev/Preview/Prod (spec §11.3), deny by default; `authorize()` Fastify middleware | Generated matrix test covers every role × action × env |
| ARK-006 | PL | `audit.write()` → Postgres append-only table with hash chain (see C2) | UPDATE/DELETE rejected; chain verifies |
| ARK-007 | FE | Shell from design: top bar (project · stack label · env switch Dev/Preview/Prod, striped Prod banner · plan chip · ⌘K), section rail, inspector, bottom edit bar (disabled) | Matches Arkus v3 shell; env switch in URL state |
| ARK-008 | FE | 01 Auth screens + 14 Settings → Members (invite, role change) | Invite → accept → role shows in matrix |
| ARK-009 | AI | `packages/llm` gateway: roles→models config, per-org token metering, secret/PII redaction hook, retries + fallback | Unit tests; cost row written per call |
| ARK-010 | DI | Feature flags + billing stub (plan on org, limits read from config) | Plan limit check callable from API |

**Exit:** Two orgs sign up; `tenant-isolation` and `authz-matrix` suites pass in CI.

### Phase 1 — GitHub + Map (read)

**Sprint 2 (wk 3–4) — walking skeleton**
| ID | Owner | Task | Acceptance |
|---|---|---|---|
| ARK-011 | PL | Register GitHub App `arkus-read` (permissions per spec §4.1 — no workflows, no secrets); install flow; installation-token service (1 h, never persisted) | Install on a test org; token minted per job |
| ARK-012 | PL | Webhook receiver: HMAC `X-Hub-Signature-256`, dedupe by delivery ID, async enqueue; `installation`, `installation_repositories`, `push`, `pull_request` | Replayed or invalid-signature deliveries rejected |
| ARK-013 | PL | `SourceProvider` interface (`listRepos, cloneUrl, getToken, openPR, getCheckStatus`) with GitHub implementation | GitLab can be added without touching callers |
| ARK-014 | DI | Indexer worker: shallow/blobless clone into ephemeral dir, size limits, skip `node_modules`/vendor/build/.gitignore/.arkusignore, **delete the clone in `finally`** | Clone dir gone after success *and* failure |
| ARK-015 | DI | Secret scrub: never read `.env*` or key files; gitleaks rules over anything sent to LLM; committed secrets → security suggestion | Fixture repo with a fake AWS key gets flagged and redacted |
| ARK-016 | AI | Detect: languages, package managers, monorepo layout (pnpm/yarn/nx/turbo), frameworks, ORM | Correct on 10 fixture repos |
| ARK-017 | AI | Extractors v0: **Next.js** (app/ + pages/api), **Express**, **Prisma** `schema.prisma` | Routes + models extracted from fixtures |
| ARK-018 | AI | Benchmark harness: labelled endpoint lists for first 15 repos; precision/recall per extractor; CI job | Runs in CI, posts a table on PRs |
| ARK-019 | PL | Snapshot persistence: `snapshots`, `nodes`, `edges` keyed by (repo, sha); source code never stored | Only paths/symbols/lines/signatures in DB |
| ARK-020 | FE | 13 Connections (repo card) + **06 Import analysis stream** over SSE | Install → pick repo → stream shows live progress |

**Demo (wk 4):** sign up → install App → pick a Next.js+Prisma repo → endpoint list and tables appear.

**Sprint 3 (wk 5–6)**
| ID | Owner | Task | Acceptance |
|---|---|---|---|
| ARK-021 | AI | Extractors: **NestJS** (decorators), **Drizzle**, **OpenAPI/Swagger import** (highest confidence), DTO/validator → request keys (zod, class-validator) | Benchmark recall ≥ 85% on these |
| ARK-022 | AI | Frontend call extractor: `fetch`, axios (instances + baseURL), React Query/SWR; template-literal normalisation | Calls normalised to `METHOD /path/:param` |
| ARK-023 | AI | Resolver: call → endpoint (exact, then fuzzy with score) → handler → ORM call → table; `confidence` + `evidence[]` on each edge | Every edge has a source and a confidence |
| ARK-024 | PL | Graph API: snapshot fetch with server-side aggregation (level of detail), permission-filtered nodes | 5k-node repo returns collapsed view < 500 ms |
| ARK-025 | PL | Snapshot diff (endpoints added/removed, request shape changes, tables) → activity events | Push changes route → diff shows it |
| ARK-026 | FE | Map v1: React Flow + ELK in a Web Worker; System view and Flow view; positions persisted per view | 5k nodes: pan/zoom ≥ 50 fps with LOD collapse (perf spike result recorded) |
| ARK-027 | FE | Node side panel: description, file link (fetched on demand from GitHub, not cached), owners (CODEOWNERS), "report wrong edge" | Code view loads live, nothing persisted |
| ARK-028 | DI | DB proxy skeleton (Go): connection registry, **SSRF guard** (resolve → block private/link-local/metadata ranges → re-check after resolve), TLS `verify-full`, envelope-encrypted creds (KMS data key per tenant) | `169.254.169.254`, `localhost`, DNS-rebind tests all blocked |

**Sprint 4 (wk 7–8)**
| ID | Owner | Task | Acceptance |
|---|---|---|---|
| ARK-029 | AI | P0.5 (if benchmark green): **FastAPI + Pydantic**, **SQLAlchemy** | Recall ≥ 85% on Python fixtures |
| ARK-030 | AI | Enrich: one-line plain-English description per endpoint/table (summarizer model), cached by content hash | Re-index of unchanged code costs 0 tokens |
| ARK-031 | AI | LLM fallback extractor for unsupported routing → nodes labelled `inferred · low confidence` | Shown dashed; user can confirm |
| ARK-032 | PL | Overrides: manual corrections stored in `overrides`, re-applied after every re-index; unresolved chips on Import resolve into overrides | Override survives re-index |
| ARK-033 | PL | Re-index on push < 2 min; "indexed at commit X, N min ago" badge | Measured on 20 benchmark repos |
| ARK-034 | FE | 07 Pages (read-only trace rows Field → Key → Column), 08 APIs Overview (steps + request/response tables), endpoint catalog, OpenAPI export | Data comes from real snapshot |
| ARK-035 | FE | ⌘K search (Postgres trigram/FTS over graph, permission-filtered) + live map updates via websocket/Redis pubsub | Push → map updates without reload |
| ARK-036 | DI | Postgres introspection: structure, row estimates (`reltuples`, never `COUNT(*)`), `pg_stat_*`, scheduled every 15 min, schema versions | 10 real DBs introspected |

**Exit Phase 1 (wk 8):** map for 20 real repos; ≥ 90% endpoint recall on P0 benchmark; re-index on push < 2 min.

### Phase 2 — DB connect + Ask (read)

**Sprint 5 (wk 9–10)**
| ID | Owner | Task | Acceptance |
|---|---|---|---|
| ARK-037 | DI | **SQL read guard** (Go, `pg_query_go`): exactly one statement, SELECT/WITH only, function denylist, table/column allowlist per user, PII masking rewrite, LIMIT inject (1000), byte cap, EXPLAIN cost gate, `BEGIN READ ONLY` + `statement_timeout=15s` + `lock_timeout=2s` as `arkus_ro` | — |
| ARK-038 | DI | **Adversarial corpus** in `packages/sqlguard` (stacked queries, comment tricks, Unicode, `pg_sleep`, `dblink`, `lo_*`, `COPY`, `SET`, `SELECT INTO`, `FOR UPDATE`, CTE with DML…) ≥ 300 cases | **100% blocked** — CI gate |
| ARK-039 | DI | Connection methods: direct + IP allowlist, SSH tunnel (keypair per connection); staged tester DNS → TCP → Auth → Introspect; "schema-only" mode; copy-paste role SQL (spec §5.3) | 13 Connections DB card works end to end |
| ARK-040 | PL | Code ↔ table linking (ORM model → table; handler → reads/writes), schema drift (code vs live DB, env vs env) → suggestions source | Drift detected on fixture |
| ARK-041 | PL | PII auto-tagging (column names + value regex sampling) → owner confirms; `db.pii.view` permission; `secret` columns never returned to anyone | Masked for Viewer, hidden for all if secret |
| ARK-042 | AI | NL→SQL v1: schema slice retrieval (embeddings over table/column descriptions + FK neighbourhood, filtered by permissions), dialect-aware generation, "clarify instead of guess" | — |
| ARK-043 | AI | Eval set: 3 demo schemas × 100+ question → expected **result** pairs; runner compares results, not SQL | CI job with accuracy number |
| ARK-044 | FE | 09 Database → Data (grid, sort, filter, FK jump, PII masked) and Schema (ERD pan/zoom, PK/FK/index, "used by") | Real DB renders |

**Sprint 6 (wk 11–12)**
| ID | Owner | Task | Acceptance |
|---|---|---|---|
| ARK-045 | AI | Glossary/semantic layer (admin-defined terms → SQL snippets); few-shot memory from ✓ answers; English explanation of each answer | Eval accuracy target met (set target in S5 from baseline, e.g. ≥ 80% on demo schemas) |
| ARK-046 | FE | 09 Query: NL ✦ → SQL, read-only lock, EXPLAIN, CSV/JSON export (streamed), saved queries, history, 👍/👎 | Results streamed, not stored |
| ARK-047 | FE | 12 Activity: When · Who · Env · Kind · What · Rows; filters; PII tagging panel | Every query appears with SQL hash, rows, ms |
| ARK-048 | PL | `queries` table + audit for every query; per-org Ask quotas (Free 50/mo) | Quota enforced server-side |
| ARK-049 | DI | 10 Safe mutation preview — **preview env only** in MVP (no prod writes yet) | — |
| ARK-050 | PD | Recruit/onboard first 5 design-partner teams on staging | 5 teams indexed |

**Exit Phase 2 (wk 12):** adversarial corpus 100% blocked; eval accuracy target met; ERD for 10 real DBs.

### Phase 3 — Health

**Sprint 7 (wk 13–14)**
| ID | Owner | Task | Acceptance |
|---|---|---|---|
| ARK-051 | DI | Synthetic checks: **domain verification first** (DNS TXT or `/.well-known/arkus-verify`), GET/HEAD only, 2–3 regions, 1–5 min, per-domain rate cap; TLS expiry | Unverified domain cannot be checked |
| ARK-052 | DI | ClickHouse: metrics + migrate audit sink (C2); OTLP ingest endpoint with per-project ingest key, sampling, per-plan quotas, retention 14/30 days | Spans map to endpoints |
| ARK-053 | PL | Sentry integration: errors per route → endpoint nodes; deploy markers | Errors show on map |
| ARK-054 | PL | Alerts: thresholds, de-dup, maintenance windows; email + Slack | Alert fires < 2 min after outage |
| ARK-055 | FE | Health overlay on map, health dots on API/page rows, **APIs → Health tab** (rate, errors, p95, last 5xx), **Overview** screen (Pages → APIs → Tables + uptime + DB health), alert settings | — |
| ARK-056 | AI | DB health from connection (connections vs max, slow queries, locks, cache hit, bloat) | Shown on Database + Overview |

### Hardening (new)

**Sprint 8 (wk 15–16) — MVP launch**
| ID | Owner | Task | Acceptance |
|---|---|---|---|
| ARK-057 | All | Appendix B checklists: "Before connecting GitHub", "Before connecting DB", "RBAC release gate", "Launch readiness" | Every box checked, evidence linked |
| ARK-058 | DI | Metering for LLM, ingest, storage per org; cost caps + alerts; captcha on signup | Dashboard per org |
| ARK-059 | PL | Uninstall webhook → revoke + delete snapshots/creds in N days; self-serve "delete all data" | Tested on staging org |
| ARK-060 | PD | Security page, DPA template, sub-processor list, responsible disclosure; status page + incident runbook for Arkus itself | Published |
| ARK-061 | All | External pen-test of auth, tenant isolation, SSRF, SQL guard (book in wk 10) | Highs fixed before launch |
| ARK-062 | PD | Onboard 20–50 beta teams; activation metric: % that see a map in 10 min | Tracked |

**🚀 MVP private beta (wk 16):** Free + Pro-read features.

### Phase 4 — Suggestions + Design mode + Plans (Free write path)

**Sprints 9–10 (wk 17–20)**
- **AI** — Rule engine: missing index (incl. FK without index), unused endpoint, unauthenticated route, schema drift, committed secrets, N+1 → `suggestions`.
- **PL** — Plans engine: `drafts` → `plans` with pipeline `draft → previewing → checks passing → approved → shipped | failed`; changes by layer (PAGE/API/DB); **approval bound to SHA-256 of plan content**; self-approval blocked for prod; impact analysis (graph traversal + traffic → risk score).
- **PL** — Checks with evidence (spec §8.1): form field → key, key → column, existing-data compatibility, reverse migration on preview, scope check, lock-risk (Squawk-style linter).
- **DI** — Preview environments: Neon/Supabase branch or nightly **masked** snapshot restored into a disposable DB; destroyed on ship/close.
- **AI** — Change Guide (Hand off): exact file + line locations from graph, suggested diff, migration in the repo's tool format, **"Copy as AI prompt"**; auto-verify after push ("3 of 3 steps complete ✓").
- **FE** — 07 Pages ＋ Add field (cascade planner PAGE+API+DB), Database add column, bottom edit bar → Save to plan, **11 Plans** screen, Hand-off panel, Suggestions list.
- **DI** — MySQL/PlanetScale driver + guard (deferred from C5).
- **Exit:** a user goes from "add phone to users" to verified-done using only the guide.

### Phase 5 — Arkus MCP server (read)

**Sprint 10 (wk 19–20), parallel with Phase 4 end**
- **PL** — `@arkus/mcp` (stdio npm) + remote HTTPS with OAuth; per-user hashed API keys scoped to project + role + layer; tools: `get_architecture`, `find_endpoint`, `impact_of`, `describe_table`, `query_db_readonly`, `get_health`, `get_spec`, `get_bindings`. **Every tool call goes through `authorize()` and the same SQL guard.**
- **FE** — 14 Settings → MCP server, API keys (create/revoke).
- **Exit:** Claude Code answers "what tables does POST /orders write?" through Arkus.

### Phase 6 — Pro Agent (code)

**Sprints 11–13 (wk 21–26)**
- **DI** — Temporal cluster; sandbox provider (D3): microVM per run, **no secrets**, egress allowlist (package registries + Git remote only), budgets (steps, tokens, wall-clock).
- **PL** — GitHub App `arkus-write` (contents/PR/checks write; **never workflows**); scoped 1-hour token on a single repo.
- **AI** — Agent: locate (graph → symbols → conventions → semantic search over summaries) → file plan → human approval → edit → run typecheck/lint/tests (`arkus.yaml`) → push `arkus/plan-N-slug` → open PR with plan + impact + results; `@arkus fix the failing test` loop. Content-as-data framing and injection flagging (spec §9.2).
- **PL** — Deterministic validators: **diff-scope** (paths ⊆ requester scope ∩ approver scope ∩ plan), forbidden paths (`.github/workflows`, infra, `postinstall`), dependency diff (new deps need approval; typosquat check), secret scan on diff.
- **AI** — BYO LLM key; attach customer MCP servers with risk classes (write-class needs per-call confirmation). `draft_plan` MCP tool (creates drafts only, can never approve/ship).
- **FE** — 11 Plans → Ship (Branch · PR · CI · typed confirm), agent run log, BYO key / attached MCPs settings.
- **Benchmark:** 50 typical plans (add field, add endpoint, add index …).
- **Exit:** ≥ 70% of benchmark plans produce passing PRs; **zero scope violations**.

### Phase 7 — Pro Agent (DB)

**Sprints 13–14 (wk 25–28)**
- **AI** — Migration generation per ORM (Prisma, Drizzle, Alembic, raw SQL); expand → migrate → contract for renames/drops.
- **DI** — Migration linter + size-aware risk; shadow-DB / branch dry-run; staged apply (staging first) with `db.migrate.apply`, backup/PITR confirmation, generated rollback.
- **DI** — Write queries: INSERT/UPDATE/DELETE with mandatory WHERE; preview via SELECT; row cap (≤ 50); transaction rolls back if affected rows ≠ preview; **optimistic concurrency** (`WHERE id=$1 AND col=$old`); undo log; separate `arkus_rw` creds; approval by SQL hash.
- **FE** — 10 Safe mutation preview on prod (typed confirm), 12 Activity → Revert, 08 APIs Try it on prod.
- **DI** — Arkus Connector v1 (Go, outbound-only mTLS, local statement allowlist, creds stay customer-side).
- **Exit:** safe migration staging → prod demo; write-query undo works.

### Phase 8 — Architect (new projects)

**Sprints 14–15 (wk 27–30)** — 03 Idea → Blueprint (structured JSON output validated against graph schema, assumption toggles, refine as diff), 04 Infrastructure (provider OAuth into **customer's own** accounts), 05 Build (Temporal workflow; repo created in the **user's** org), design review checks, exports (OpenAPI, DDL, Prisma, task breakdown), design-vs-implementation drift.
**Exit:** a non-technical tester designs and scaffolds an app without help.

### Phase 9 — Team / Enterprise (wk 30+)
Layer scopes UI + custom role editor (migrate `can()` to Cerbos — path globs favour it — keeping the interface), SSO/SCIM, audit export/SIEM, GitLab/Bitbucket providers, Go/Java extractors, SOC 2 Type I → II, VPC data plane, public status pages.

---

## 6. Critical path

```
Import screen design (wk0) ─┐
GitHub App + webhooks (S2) ──┼─► Indexer + P0 extractors (S2–S3) ─► Resolver (S3) ─► Map + Catalog (S3–S4) ─► Phase 1 exit (wk8)
Authz can() + RLS (S1) ──────┘                                                                                   │
DB proxy + SSRF (S3) ─► Introspection (S4) ─► SQL guard + corpus (S5) ─► NL→SQL eval (S5–S6) ─► Phase 2 exit (wk12)
                                                                                                                 │
Health (S7) ─► Hardening + pen-test (S8) ─► MVP (wk16) ─► Plans + approvals by hash (S9–10) ─► Agent + validators (S11–13) ─► Pro (wk26)
```

Slip rules: if the **extractor benchmark** is below target at wk 6, drop P0.5 (Python) rather than move Phase 1 exit. If the **SQL guard** corpus isn't 100% at wk 12, Ask ships **disabled**; never relaxed.

---

## 7. Non-negotiables (Definition of Done for every PR)

From spec Appendix A. A PR that breaks one is not merged.
1. Every table has `org_id` + RLS; tenant from auth context only.
2. Every route goes through `authorize()`; new actions are added to the matrix test.
3. Read-only by default; writes need plan permission + role permission + env enablement.
4. All changes go through plans; approvals bind to a SHA-256 of the exact plan/diff/SQL.
5. Arkus never pushes to the default branch, never auto-merges, never runs DDL directly.
6. LLM output and customer content are untrusted; deterministic validators decide.
7. No customer source code is persisted.
8. Credentials: KMS envelope encryption, decrypted only in dbproxy, never logged or returned.
9. SSRF: resolve, block private/link-local/metadata, re-check after DNS.
10. Every privileged action writes an audit event.

---

## 8. Metrics and targets

| Area | Metric | Target |
|---|---|---|
| Activation | Signups who see a map within 10 min | ≥ 60% |
| Accuracy | P0 endpoint recall / precision (benchmark) | ≥ 90% at Phase 1 exit, ≥ 95% at public launch |
| Ask | Execution accuracy on eval; 👍 rate | set from S5 baseline; ≥ 80% 👍 |
| Safety | Adversarial SQL corpus blocked | 100% (hard gate) |
| Pro | Agent PR merge rate · scope violations · migration incidents | ≥ 50% · 0 · 0 |
| Business | Free → Pro conversion · LLM cost per active org · gross margin | tracked from beta |

---

## 9. Risk register (owners)

| Risk | Owner | Early signal | Response |
|---|---|---|---|
| Map accuracy too low | AI | Benchmark < 85% at wk 6 | Narrow frameworks, LLM fallback with confirm, runtime traces |
| Customers won't grant DB access | PD | < 50% of beta connect a DB | Schema-only mode, Connector, security page |
| Agent PR quality | AI | Merge rate < 40% | Fewer plan types, better locate step, more validators |
| LLM cost > revenue | DI | Cost/org above plan price | Content-hash caching, haiku-class models for summaries, BYO key, quotas |
| Scope creep | PD | Sprint goals missed twice | Cut to the phase exit criterion; nothing from later phases |
| Security incident | DI | Any isolation/guard test flake | Stop-ship; fix before features |

---

## 10. How to run each phase with an AI coding assistant

Start each task with spec Appendix A + this prompt:

```
Context: [Appendix A]. Current phase: N. Task: ARK-xxx — <title + acceptance criteria from BUILD_PLAN.md>.
Constraints: follow the non-negotiables (§7). Write tests first (authz + guards especially).
Deliver: code + tests + a short note on any security implication.
Do not implement features from later phases.
```
