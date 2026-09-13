# Part 8 — Deployment, Security Operations, Testing Strategy & Phases

Tags: `[ERPNext CONFIGURATION]`, `[MANASE CUSTOM]`, `[API]`, `[MOBILE]`.

---

## 1. Deployment Architecture

```
                 HTTPS (TLS, managed reverse proxy / Caddy|Nginx)
        ┌──────────────────────┬───────────────────────────┐
        ▼                      ▼                           ▼
 Desk/Web (admin & branches)  Mobile API (/api/method/…)   callbacks (providers)
        │                      │
        ▼                      ▼
   Frappe/ERPNext v16 bench (gunicorn/web) + socketio
        │  RQ workers: default, short, long, mb (custom queue "mb")
        ├── MariaDB 10.6+ (daily logical + binlog replication)
        ├── Redis: cache, queue, socketio
        Dar es Salaam DC/VM: 4 vCPU / 16 GB (minimum), expandable
   Branches: browser over internet (2FA for staff 2FA recommended)
   Mobile: 4G/5G, token auth; SMS gateway (AT/Beem TZ); FCM; mobile money callbacks
```

- Install: `bench get-app https://github.com/BENETHNGOSWE/FISH-BURTCHER-APP.git` →
  `bench install-app manase_butcher` (runs after_install provisioning) → `bench migrate`.
- Configuration via **Manase Butcher Settings** (accounts/warehouses auto-suggested, OTP/FCM
  secrets set once; secrets stored in site config/standard Password fields).
- Multi-site/multi-company supported; one company initially; expand branches in Branch doctype
  (auto-creates warehouse + cost center) without code changes.
- Backups: `bench backup` schedule + offsite; Redis persistence; monitor via standard logs +
  health; scheduler required (reservation expiry, reminders, FCM retries).

### Hardening
- HTTPS only, HSTS, modern TLS; allowlist mobile money callback paths with provider secrets;
- least-privilege DB user; folders perms per Frappe security docs;
- staff 2FA; Business Owner/GM accounts secured; API tokens (account) never shipped in apps;
- OTP secrets/FCM service account only in Password fields/site config; raw OTP never logged;
- branch staff share-no-accounts (each user scoped via User Permission);
- Rate limiting active; fail2ban for desk; security audit events in Audit Log/OTP Log.

## 2. Security checklist (spec §47)
RBAC matrix deployed; branch User Permissions verified; API unauthenticated surface is only
request/verify OTP + signed callbacks; session tokens hashed, expiring, revocable; input
validation + idempotency; server-side authorization on every mutation; audit for stock/KG/price/
cancel/payment/expense/transfer variance; customers restricted to own profile/orders/payments/
addresses/receipts; no ERPNext creds in Flutter; no direct DB from mobile; signed callbacks &
replay protection.

## 3. Testing Strategy

### Server (Frappe unit/integration, `bench run-tests`):
`manase_butcher/tests/` — FrappeTestCase based:
1. **test_setup**: roles, UOM Kg, warehouse tree, accounts/wallets, modes of payment exist after
   install; branch creation provisions warehouse+cost center.
2. **test_kg_conservation**: 500 KG receiving → PR +500; processing 500→470+30 balances; waste
   issue −30; transfer 100 sent / 98 received with reason mandatory; reconciliation variance
   posts and stock matches physical; KG Movement report closing == SLE closing (difference 0).
3. **test_pricing_pos**: branch-specific Item Price resolution; POS invoice + split Payment
   Entries; branch warehouse stock −KG; credit limit blocks over-limit; cancellation reverses
   properly (amend/cancel ledger evidence).
4. **test_reservation_orders**: mobile order creates SO+SRE; concurrent orders cannot oversell;
   timeout release; cancel release; completion invoices, consumes KG, creates payments; foreign
   customer gets 403; rate limiter trips on OTP flood.
5. **test_closing_profit**: daily closing expected vs actual variance & over-short JE; GP/NP
   profitability numbers vs GL; expense JE allocation to branch cost center.
6. **test_audit**: sensitive actions wrote Audit Log/Price Change Log; Audit Log immutable.

### API contract tests
Requests/responses per Part 6 with Frappe test client: OTP lifecycle, nearby (known coords),
availability isolation (Sinza 0 KG shown Out of Stock), cart validation, idempotent order,
callback signature acceptance/rejection.

### Mobile (Flutter)
Widget tests for cart KG math and status timeline; integration tests against staging API with
test numbers; OTP test mode for CI (fixed OTP via settings in staging); signed release builds.

### Manual/UAT script
Runs the full §42 scenario on staging with Masaki/Mikocheni/Sinza/Kariakoo; reconciliation
physical counts; kill connection mid-transfer/callback and verify idempotency; backup/restore
drill; permission matrix walk-through (log in as each role, attempt cross-branch writes).

## 4. Development Phases & Definition of Done

| Phase | Contents (spec §45) | DoD |
|---|---|---|
| **1 Foundation** | App shell, modules, workspace hub, roles setup, provisioning (UOM/groups/warehouses/CC/accounts/modes), Branch, Fish Species, Item custom fields, Customer/Supplier readiness | App installs clean on fresh v16 site; all master records present; branch creation works; roles matrix enforced |
| **2 Fish Operations** | Fish Receiving (+landed costs/batch), Processing/yield, Waste, two-leg Transfers + variance reasons, Reconciliation posting, KG Movement & related reports | §42 steps 1–9 & 24 pass; conservation invariant; approvals; reports tie to SLE |
| **3 Sales & Finance** | POS page, tenders incl. TZ mobile money, credit enforcement, expenses JE, daily closing over/short, profitability/branch reports | §42 steps 18–25; cash/wallet reconciliation; GP/NP from GL; aging/reminders |
| **4 Customer Mobile** | OTP auth, sessions, nearby branches, branch catalog/availability, KG cart, checkout + reservation, order lifecycle/actions, payments callbacks, profile/addresses | §42 steps 10–21 & 23; oversell impossible; ownership isolation; Flutter app submitted for testing |
| **5 Advanced** | Delivery management, FCM + SMS/WhatsApp, loyalty/promotions (Pricing Rule), advanced analytics, supplier performance scoring, batch traceability UI, BOM-based expected yields | All notifications delivered; traceability supplier→sale; promo accounting correct; performance at 2 years data |

Each phase: migrations reversible-in-effect (standard cancel), tests added, fixtures updated,
changelog; releases tagged; blueprint updated.

## 5. Performance & operations
- Reports use SLE indexes (item, warehouse, posting_datetime); heavy reports run on `long` queue /
  export; daily summary table optional (scheduled) for 2-year dashboards.
- Catalog API uses Bin + branch warehouse index; ETag/304s; image thumbnails via Frappe files.
- Scheduler: release stale reservations (every 5 min), debt reminders (daily), notification
  retries (queue mb), closing reminders to branches (evening), low-stock digest.
- Scale-out: add workers, read-replica reporting; bench update routine documented in README.

## 6. Backups & data governance
Nightly encrypted backups + weekly restore drill; customer phone numbers are PII — access limited,
retention policy; TZ data residency preference; GDPR-style export/delete via standard customer
data tools; audit logs retained per accounting retention requirements.
