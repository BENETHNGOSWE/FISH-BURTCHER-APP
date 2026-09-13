# Part 9 — Feature Classification Matrix (every spec feature)

Legend: **[S]** ERPNext STANDARD · **[C]** ERPNext CONFIGURATION · **[X]** MANASE CUSTOM ·
**[M]** MOBILE · **[A]** API. This matrix is authoritative for scope ownership.

## Master data & structure
| Feature | Classification | Implementation |
|---|---|---|
| App in launcher, workspaces, modules | [X] | App `manase_butcher`, 9 Workspace JSON, 4 modules |
| Company / branches / cost centers | [C] | Branch custom DocType provisions Warehouse + Cost Center |
| Branch = real Warehouse | [S][X] | Warehouse tree with `custom_mb_branch`; Bin/SLE standard |
| Fish product master (species, grade, size, fresh/frozen, cut) | [S][C] | Item + Item Attributes/Groups + custom fields |
| Prices (retail/wholesale/restaurant/hotel/special/branch) | [S][X] | Price Lists + Item Price custom `mb_price_type`,`mb_branch`; resolution helper |
| Price change audit | [X] | Price Change Log + Audit Log (Version on Item Price) |
| Min/max stock | [S] | Item Reorder per warehouse → Low Stock report |
| Customers / suppliers | [S] | Customer, Supplier (+kind custom fields), Address, Contact |
| Employees / users / roles | [S][C][X] | Employee/User/User Permission + 12 MANASE roles |
| KG as primary UOM | [C] | UOM Kg stock/selling; Piece conversion standard |

## Receiving, processing, KG tracking
| Feature | Classification | Implementation |
|---|---|---|
| Fish Receiving + weighing (gross/tare/net) | [X] | Fish Receiving (+child rows) |
| Purchase cost / landed cost | [S][X] | Purchase Receipt valuation taxes; Landed Cost Voucher; totals on custom doc |
| Purchase invoice & supplier payment | [S] | Purchase Invoice, Payment Entry, payables reports |
| Payment status at receiving | [X][S] | Field on receiving; standard invoice status source |
| KG movement history | [S][X] | Stock Ledger Entry in Kg + stage/link custom fields; KG Movement report |
| Fish Processing (input/output/waste, cost, approval) | [X] | Fish Processing → Stock Entry Manufacture |
| Yield % / Waste % | [X][S] | Computed + Processing Yield report (BOM expected yield optional) |
| Yield by fish/supplier/processor/branch/batch | [X] | Processing Yield report filters/group-by |
| Waste transaction + reasons + approval | [X][S] | Fish Waste Record → Material Issue; workflow thresholds |
| Fish Batch / traceability | [S][X] | Batch (standard) + Fish Batch + Batch Traceability report |

## Warehousing & transfers
| Feature | Classification | Implementation |
|---|---|---|
| Central & branch stock | [S] | Warehouses + Bin; standard Stock Balance |
| Two-leg branch transfer, sent/received/variance + reason | [X][S] | Fish Stock Transfer workflow → 2 Stock Entries via Transit |
| Branch inventory view | [S][X] | Stock Balance filtered; Branch Stock workspace/report |
| Branch stock reconciliation | [X][S] | Branch Stock Reconciliation → standard Stock Reconciliation |
| "Where did the KG go?" | [X] | kg_movement script report from SLE |
| Returns / adjustments | [S][X] | Sales Return; Stock Reconciliation; reasons & audit |

## Sales, orders, payments
| Feature | Classification | Implementation |
|---|---|---|
| Branch POS (simple KG flow) | [X][S] | Custom fish_pos page → Sales Invoice POS + Payment Entries |
| Tenders: cash + M-Pesa/Tigo/Airtel/Halo/bank/card/credit | [C][S] | Modes of Payment + wallet accounts; references |
| Mobile money callbacks | [A][X] | Signed webhook endpoints → Payment Entry |
| Discounts/authority limits | [S][C] | POS Profile / Pricing Rule; server checks; audit |
| Receipts/print | [S][X] | Fish Print Format |
| Credit limit, partial payment, aging, reminders | [S][X] | Credit Limit, Payment Entry, aging report, SMS job |
| Customer mobile orders | [M][A][X] | Flutter; Customer Order doc → Sales Order/SRE → SI/PE |
| Stock reservation / no oversell | [S][X][A] | Stock Reservation Entry (+custom fallback), locked checks |
| Order status timelines pickup/delivery | [M][A][X] | Status state machine + FCM/SMS |
| Nearby branch geolocation/manual choice | [M][A][X] | Branch lat/lng + Haversine endpoint |
| Branch-specific availability | [A][S] | Projected qty from branch Bin only |
| Delivery | [X][S] | Sales Order delivery / delivery staff actions; phase 5 routing |

## Finance
| Feature | Classification | Implementation |
|---|---|---|
| Branch expenses + cost center + approval | [X][S] | Fish Expense → Journal Entry workflow |
| Actual cost / COGS / GP / NP | [S][X] | Valuation (landed+processing), GL; Profitability report |
| Daily branch closing + cash variance | [X] | Daily Branch Closing + Cash Over/Short JE |
| Branch performance | [X] | Report + dashboard cards/charts |
| Consolidated head-office reports | [S][X] | GL/cost-center reports + custom dashboards |
| Supplier balances | [S] | Accounts Payable standard |

## Platform, security, mobile
| Feature | Classification | Implementation |
|---|---|---|
| Phone+OTP login, sessions, refresh, logout | [A][X][M] | OTP Log/Mobile Session, hashed tokens, gateway abstraction |
| No desk access for customers | [X][A] | Whitelist-only API; no Frappe user per customer |
| Rate limiting / validation / idempotency | [A][X] | Redis counters, server validation, idempotency keys |
| RBAC + branch isolation | [S][X] | Roles, User Permissions, query/has_permission hooks |
| Audit trail | [S][X] | Version + Audit Log/Price Change Log |
| Notifications (FCM/SMS/WhatsApp) | [X][S][C] | fcm.py, otp/SMS gateway, Notification standard, Notification Log |
| Push tokens | [M][X] | Mobile Device; FCM v1 |
| Flutter UI/navigation | [M] | Home/Shop/Cart/Orders/Profile (separate build target) |
| Reports (sales/inventory/fish/customer/finance) | [X][S] | 10 script reports + standard reports |
| Workflows | [X][C] | 6 Workflow fixtures |
| Scheduled jobs | [X] | reservation release, reminders, digests, retries |

## Deliberately NOT rebuilt (use ERPNext)
Tax engine, multi-currency engine, GL/AR/AP, bank reconciliation, serial/barcode (standard),
loyalty (phase 5 via standard loyalty program), email campaigns, HR/payroll (use ERPNext HR),
manufacturing BOM (optional standard for expected yield), stock valuation math, document
versioning/backups/permissions framework — all standard.
