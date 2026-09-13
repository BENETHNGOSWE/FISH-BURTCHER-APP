# MANASE BUTCHER — Technical Blueprint Index

The blueprint follows instruction §50 and covers all 35 required sections.

| Part | Document | Required blueprint sections |
|---|---|---|
| 1 | [00-blueprint-overview.md](00-blueprint-overview.md) | System architecture; complete flow; standard vs custom; modules; phases |
| 2 | [01-process-flows.md](01-process-flows.md) | Business process diagrams & flows (receiving → processing → waste → transfer → reconciliation → POS → mobile → closing); end-to-end validation |
| 3 | [02-erpnext-mapping.md](02-erpnext-mapping.md) | Standard DocTypes, custom DocTypes & fields, branch/warehouse architecture, KG tracking, processing/waste/reconciliation/reservation, purchase & accounting, ERD |
| 4 | [03-permissions-workflows.md](03-permissions-workflows.md) | Roles & permission matrix, branch isolation, workflows, audit trail, security |
| 5 | [04-sales-finance.md](04-sales-finance.md) | Sales/POS, credit, expenses, daily closing, profitability, mobile money |
| 6 | [05-mobile-api.md](05-mobile-api.md) | Mobile & API architecture, OTP auth, nearby branches, availability, reservation logic, order workflow, navigation, notifications, rate limiting |
| 7 | [06-reports-dashboards.md](06-reports-dashboards.md) | Reports, dashboards/workspaces, KPI definitions |
| 8 | [07-deployment-testing.md](07-deployment-testing.md) | Deployment, security ops, testing, phased Definition of Done |
| 9 | [08-feature-classification.md](08-feature-classification.md) | Every feature tagged `[ERPNext STANDARD]` / `[CONFIGURATION]` / `[MANASE CUSTOM]` / `[MOBILE]` / `[API]` |

## Ten business rules (§49) — where they are enforced

1. Every fish stock movement has a KG quantity — fish Items stock in **Kg**; custom docs post KG to the Stock Ledger (`stock_utils.make_stock_entry`).
2. Every branch has its own Warehouse — `Branch.validate()` provisions Warehouse + Cost Center.
3. Mobile availability comes from the selected branch warehouse — `fish_mobile/api/products.py`.
4. Customers cannot order more KG than available/reserved — locked availability check + SRE (`Customer Order.price_and_check_availability/reserve_stock`).
5. Processing accounts for input/output/waste KG — conservation validator in `Fish Processing`.
6. Every variance has a reason — transfer & reconciliation validators.
7. Every financial adjustment is auditable — `Audit Log`, `Price Change Log`, Version history.
8. Cancellations never silently rewrite the ledger — standard cancel/amend; reversal documents remain.
9. Branch managers cannot touch other branches — User Permissions + query conditions + server asserts.
10. ERPNext is the final source of truth — reports read Stock/GL ledger; custom docs only create standard documents.
