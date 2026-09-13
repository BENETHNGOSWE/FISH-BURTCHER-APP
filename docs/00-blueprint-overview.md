# MANASE BUTCHER — Technical Blueprint (Part 1: Overview & Architecture)

> **MANASE BUTCHER** is a custom ERPNext v16 / Frappe application (`manase_butcher`) for a
> weight-based, multi-branch fish butcher and retail business in Tanzania.
>
> The single most important objective:
> **Track every fish KG from supplier → receiving → processing → waste → central warehouse →
> branch → sale/order → final reconciliation, with full visibility of money, stock, branches,
> customers and profitability.**

---

## 1. System Architecture

### 1.1 Classification legend

Every feature in this blueprint is tagged with exactly one of:

| Tag | Meaning |
|---|---|
| `[ERPNext STANDARD]` | Used as-is, no code (Item, Customer, Warehouse, Sales Invoice, Stock Ledger…) |
| `[ERPNext CONFIGURATION]` | Standard feature enabled/configured by the app's setup (UOMs, Item Groups, Warehouses, Cost Centers, Price Lists, Modes of Payment, Numbering, User Permissions, Custom Fields) |
| `[MANASE CUSTOM]` | New DocType / page / report / workflow / server logic shipped in the `manase_butcher` app |
| `[MOBILE]` | Flutter customer application |
| `[API]` | Secure JSON API layer exposed by the Frappe app for the mobile app |

### 1.2 Logical architecture

```
                            ┌──────────────────────────────────────┐
                            │           ERPNext v16 / Frappe        │
                            │        (MariaDB + Redis + RQ)         │
                            │                                       │
                            │  Core: Item, Customer, Supplier,      │
                            │  Warehouse, Batch, Stock Ledger,      │
                            │  Purchase Receipt/Invoice, Sales      │
                            │  Order/Invoice, Payment Entry, JE,    │
                            │  Stock Entry, Stock Reconciliation,   │
                            │  Stock Reservation Entry, GL, Cost    │
                            │  Centers, Item Price, Mode of Payment │
                            │                                       │
                            │  ┌────────────────────────────────┐   │
                            │  │      manase_butcher app         │   │
                            │  │  Workspaces · DocTypes · Pages  │   │
                            │  │  Reports · Workflows · Roles    │   │
                            │  │  Hooks · Scheduled Jobs · API   │   │
                            │  └────────────────────────────────┘   │
                            └───────────┬───────────────┬───────────┘
                                        │               │
                 Frappe Desk (browser)  │               │  HTTPS JSON (token auth)
        ┌──────────────────────────────┘               └────────────────────────┐
        ▼                                                                       ▼
 Admin / Branch Web UI (native Frappe)                              Flutter Customer Mobile App
 (POS page, operations, reports)                                   (OTP, shop, cart, orders,
                                                                    branch stock, payments)
```

**Principles**

1. **ERPNext is the only system of record.** The custom app never creates a parallel inventory or
   accounting database. Every custom transaction *generates* standard ERPNext documents
   (Purchase Receipt, Stock Entry, Sales Order, Sales Invoice, Payment Entry, Journal Entry,
   Stock Reconciliation, Stock Reservation Entry).
2. **KG is a first-class unit.** Fish items stock and sell in **Kg** (stock UOM). Every stock
   movement therefore already carries a KG quantity in the Stock Ledger. Custom documents capture
   weight at every stage and post it into the ledger.
3. **Every branch is a real Warehouse tree** with a Cost Center, so stock, valuation, sales and
   profit can never be ambiguous about location.
4. **No unexplained KG movement.** Input KG = Output KG + Waste KG ± Variance KG, enforced in
   validations; waste, variance, returns and adjustments are all *documents with reasons*.
5. **Mobile never touches Desk.** Customers use a narrow, authenticated, rate-limited JSON API and
   can only ever see their own data and the stock of the branch they selected.

### 1.3 Application package

```
manase_butcher/                      # app package (pip-installable, bench get-app)
├── pyproject.toml / setup.py
├── requirements.txt
└── manase_butcher/
    ├── hooks.py                     # events, jobs, fixtures, permissions
    ├── modules.txt                  # Manase Butcher, Fish Inventory, Fish Sales, Fish Mobile
    ├── setup/                       # after_install / after_migrate provisioning
    ├── stock_utils.py               # KG availability, reservations, stock entry helpers
    ├── branch_utils.py              # branch↔warehouse, user-branch permission helpers
    ├── accounting_utils.py          # wallets, modes of payment, JE/PE helpers
    ├── audit.py                     # immutable Audit Log writer
    ├── otp.py                       # OTP providers (log, Africa's Talking, Beem, generic SMS)
    ├── fcm.py                       # Firebase Cloud Messaging (service account JWT)
    ├── manase_butcher/              # module: settings, branch, audit, sessions…
    ├── fish_inventory/              # module: receiving, processing, waste, transfer, recon
    ├── fish_sales/                  # module: POS, customer orders, expenses, closing
    ├── fish_mobile/                 # module: API package
    ├── workspace/  page/  report/   # UI artefacts
    └── fixtures/                    # Workflows (loaded on migrate)
```

Modules (shown in the module list / app launcher grouping):

| Module | Folder | Content |
|---|---|---|
| Manase Butcher | `manase_butcher` | Settings, Branch, Audit Log, OTP/Session/Device, Price Change Log, Notification Log |
| Fish Inventory | `fish_inventory` | Fish Species, Fish Batch, Receiving, Processing, Waste, Transfer, Reconciliation, Stock Reservation |
| Fish Sales | `fish_sales` | Customer Order, Fish Expense, Daily Branch Closing, POS page |
| Fish Mobile | `fish_mobile` | Public mobile API package (no Desk DocTypes) |

### 1.4 Technology stack `[ERPNext CONFIGURATION]`

- ERPNext **v16**, Frappe Framework v16, Python 3.11+, MariaDB 10.6+, Redis, RQ workers
- Multi-site capable; single company initially ("MANASE BUTCHER LTD")
- Flutter 3.x mobile (Dart), Riverpod/Bloc state, Dio HTTP, Google Maps/Geolocator, FCM
- SMS: Africa's Talking / Beem / generic HTTP SMS gateway (Tanzania); OTP via SMS
- Payments: cash + Tanzanian mobile money (M-Pesa, Tigo Pesa, Airtel Money, HaloPesa) + bank/card
  as standard Modes of Payment; provider push/callbacks recorded against orders
- Currency: TZS; stock/selling UOM: **Kg** (with Piece as alternate UOM where relevant)

---

## 2. Business Process Diagrams

### 2.1 End-to-end physical & financial flow

```
 SUPPLIER/FISHERMAN
      │  (Fish Receiving: weigh, grade, landed costs)
      ▼
 PURCHASE RECEIPT ──► Purchase Invoice ──► Payment Entry (supplier debt)
      │ +KG
      ▼
 CENTRAL RAW FISH WAREHOUSE
      │
      │  Fish Processing (Manufacture Stock Entry)
      ▼
 ┌──────────────┬───────────────┬──────────────┬─────────────┐
 ▼              ▼               ▼              ▼             ▼
Cleaned       Fillet        Other Cuts     Fish Waste    (yield%)
      │              │               │              │ (Material
      └──────┬───────┴───────┬───────┘              │  Issue / disposal)
             ▼               ▼                      ▼
   CENTRAL PROCESSED WAREHOUSE            WASTE WAREHOUSE → write-off
             │
             │ Fish Stock Transfer (source → transit → branch, with received KG + variance)
      ┌──────┼───────────────┬──────────────┐
      ▼      ▼               ▼              ▼
   MASAKI MIKOCHENI       SINZA        KARIAKOO   (each a real Warehouse + Cost Center)
      │
      ├── Walk-in / Wholesale / Restaurant sale (POS page → Sales Invoice + Payment Entry)
      ├── Mobile order (Sales Order + Stock Reservation → Sales Invoice on fulfilment)
      ├── Waste / Returns / Adjustments (all documented, KG-conserving)
      └── Daily Branch Closing (cash/mobile/credit reconciliation)
             │
             ▼
 HEAD OFFICE: consolidated KG Movement, Reconciliation, Performance, Profitability reports
```

### 2.2 The KG conservation equation `[MANASE CUSTOM]`

Enforced server-side on every operation:

```
Receiving : received_kg                     = ledger_in_kg
Processing: input_kg                        = sellable_output_kg + waste_kg
Transfer  : sent_kg                         = received_kg + variance_kg   (reason mandatory if ≠0)
Recon     : opening + in − out − sales − waste ± adjustments = expected_kg
            variance_kg                     = physical_kg − expected_kg   (reason mandatory if ≠0)
Sale      : reserved_kg → delivered_kg      = ledger_out_kg
```

The **"Where Did The KG Go?"** report reconstructs this equation per item/warehouse/period purely
from the Stock Ledger Entry plus the custom source-document links stamped on Stock Entries, so the
report always agrees with the ledger (Rule 10: ERPNext is final source of truth).

---

## 3. Complete Business Flow (mapped to documents)

| # | Physical step | System document / action | KG effect | Tag |
|---|---|---|---|---|
| 1 | Supplier delivers fish | **Fish Receiving** → creates **Purchase Receipt** with Valuation tax rows (transport, handling, ice) | +KG to Central Raw | `[MANASE CUSTOM]` + `[ERPNext STANDARD]` |
| 2 | Supplier bill / payment | Purchase Invoice (optionally auto) + Payment Entry | — | `[ERPNext STANDARD]` |
| 3 | Quality/grade check | Grade/freshness fields on receiving lines; rejected → waste/return reason | ± | `[MANASE CUSTOM]` |
| 4 | Butchering | **Fish Processing** → Stock Entry *Manufacture* (raw out; cuts + waste in) | conserved | `[MANASE CUSTOM]` |
| 5 | Waste disposal | **Fish Waste Record** → Stock Entry *Material Issue* from Waste/branch warehouse | −KG, reason | `[MANASE CUSTOM]` |
| 6 | Dispatch to branch | **Fish Stock Transfer** (Draft→Submitted→Approved→Dispatched) → Stock Entry to Transit | out of Central | `[MANASE CUSTOM]` |
| 7 | Branch receiving | same doc, *Received* action → Stock Entry Transit→Branch with received KG/variance | into Branch | `[MANASE CUSTOM]` |
| 8 | Walk-in/wholesale sale | **POS page** → Sales Invoice (POS) + Payment Entry(s); credit → outstanding | −KG branch | `[MANASE CUSTOM]` page + standard |
| 9 | Mobile order | **Customer Order** → Sales Order + **Stock Reservation Entry**; on fulfilment → Sales Invoice + Payment | reserved then −KG | `[MANASE CUSTOM]` / `[API]` / `[MOBILE]` |
| 10 | Customer returns | Sales Return (Credit Note) or Waste Record (category Customer Return) | +/− KG with reason | standard + custom |
| 11 | Branch expense | **Fish Expense** → Journal Entry against branch Cost Center | — | `[MANASE CUSTOM]` |
| 12 | Daily closing | **Daily Branch Closing** with cash/mobile/credit counts and variance | (kg sold snapshot) | `[MANASE CUSTOM]` |
| 13 | Stock count | **Branch Stock Reconciliation** → standard **Stock Reconciliation** for approved variances | ±KG with reason | `[MANASE CUSTOM]` + standard |
| 14 | Management | KG Movement, Reconciliation, Yield, Waste, Performance, Profitability reports & dashboards | — | `[MANASE CUSTOM]` |
| 15 | Traceability | **Fish Batch** linked to ERPNext Batch; Batch Traceability report | — | `[MANASE CUSTOM]` + standard |

---

## 4. ERPNext Standard DocTypes Used (never duplicated)

| Area | Standard DocType | How MANASE uses it |
|---|---|---|
| Master data | Item, Item Group, UOM, Item Attribute, Brand | Fish product master; Item Group = Fresh Fish / Frozen Fish / Processed Cuts / Fish Waste |
| Master data | Customer, Supplier, Address, Contact | Customers incl. mobile customers; Suppliers typed Fisherman/Co-op/Wholesaler |
| Warehousing | Warehouse, Bin | Central Raw/Processed/Waste/Transit + one Warehouse per branch |
| Stock | Stock Ledger Entry, Stock Entry, Stock Reconciliation, Batch | All KG movements, manufacture, transfer, issue, counts |
| Reservations | Sales Order, **Stock Reservation Entry** | Mobile order KG reservation against branch warehouse |
| Buying | Purchase Receipt, Purchase Invoice, Landed Cost Voucher, Purchase Order | Receiving posts stock; transport/handling added to valuation |
| Selling | Sales Order, Sales Invoice, POS Profile, Pricing Rule | Mobile orders, POS, returns, discounts |
| Pricing | Item Price, Price List | Retail/Wholesale/Restaurant/Hotel/Special/Branch price types (custom fields + lists) |
| Money | Payment Entry, Mode of Payment, Account, Cost Center, GL Entry, Journal Entry | All money, mobile money, expenses, branch P&L |
| Credit | Customer Credit Limit, Credit Limit, Payment Terms, Collection of outstanding + aging | Customer credit limits & aging |
| People | Employee, User, User Permission, Role | Staff, branch-scoped access |
| Platform | Notification, Email/SMS Settings, Print Format, Workflow, Version, Auto Repeat, Energy Point (n/a) | Alerts, receipts, approvals, audit history |

**Standard vs custom decision rule:** if a standard DocType can legally represent the transaction and
post to the stock/accounting ledger, the custom DocType is only the *fish-specific front document*
that creates and links the standard document — it never replaces the ledger.

---

## 5. Custom DocTypes Required (summary — full model in Part 8)

| Module | Custom DocType | Submittable | Purpose |
|---|---|---|---|
| Manase Butcher | **Manase Butcher Settings** | singleton | accounts, warehouses, thresholds, OTP/SMS/FCM config, payment accounts |
| Manase Butcher | **Branch** | no | physical branch → Warehouse + Cost Center + geo-coordinates + manager |
| Manase Butcher | **Audit Log** | immutable | user/time/branch/document/old/new/reason for sensitive actions |
| Manase Butcher | **OTP Log** | no | hashed OTPs, attempts, expiry, rate-limit counters |
| Manase Butcher | **Mobile Session** | no | opaque bearer tokens (hashed), device, expiry |
| Manase Butcher | **Mobile Device** | no | device id, platform, FCM token per customer |
| Manase Butcher | **Price Change Log** | immutable | old/new price, branch, reason |
| Manase Butcher | **Notification Log** | no | FCM/SMS/WhatsApp sends and delivery status |
| Fish Inventory | **Fish Species** | no | species master (local + scientific name, image) |
| Fish Inventory | **Fish Batch** | yes | supplier batch → links ERPNext Batch; received/sellable/waste KG, distribution |
| Fish Inventory | **Fish Receiving** (+ 2 children) | yes | weighing/grade/landed cost → Purchase Receipt |
| Fish Inventory | **Fish Processing** (+ Input/Output children) | yes | manufacture with yield%/waste% |
| Fish Inventory | **Fish Waste Record** (+ child) | yes | material issue; threshold approval |
| Fish Inventory | **Fish Stock Transfer** (+ child) | yes | two-leg transit transfer; received KG & variance |
| Fish Inventory | **Branch Stock Reconciliation** (+ child) | yes | expected vs physical; posts Stock Reconciliation |
| Fish Inventory | **Stock Reservation** | yes | reservation ledger/fallback for mobile KG |
| Fish Sales | **Customer Order** (+ Item/Payment children) | yes | mobile order state machine wrapping SO→SI/PE |
| Fish Sales | **Fish Expense** | no (workflow) | branch expense → Journal Entry |
| Fish Sales | **Daily Branch Closing** (+ payment child) | yes | cash/mobile/credit/expected vs actual, variance |

Child tables: Fish Receiving Item, Fish Landing Cost, Fish Processing Input, Fish Processing
Output, Fish Waste Item, Fish Transfer Item, Reconciliation Count Item, Customer Order Item,
Customer Order Payment, Daily Closing Payment, Mobile Payment Account (settings child).

---

## 6. Custom Fields (configuration applied by `after_migrate`)

| DocType | Field(s) | Purpose |
|---|---|---|
| Item | `mb_is_fish`, `mb_species`, `mb_fish_category`, `mb_grade`, `mb_size`, `mb_freshness`, `mb_preparation`, `mb_sellable` | fish product master attributes |
| Warehouse | `mb_branch` (Link Branch), `mb_warehouse_kind` (Central Raw/Central Processed/Branch/Transit/Waste/Processing) | warehouse classification & branch scoping |
| Bin | `mb_custom_reserved_kg` | fallback reservation quantity (prefer standard SRE) |
| Batch | `mb_supplier`, `mb_fish_batch`, `mb_received_date` | batch traceability |
| Purchase Receipt | `mb_fish_receiving`, `mb_total_kg` | back-link & KG total |
| Purchase Receipt Item | `mb_grade`, `mb_freshness` | quality at intake |
| Stock Entry | `mb_branch`, `mb_fish_processing`, `mb_fish_waste_record`, `mb_fish_transfer`, `mb_stage` | classify every KG movement for reports |
| Sales Invoice | `mb_branch`, `mb_sales_channel` (Walk-in/Wholesale/Restaurant/Mobile), `mb_customer_order`, `mb_total_kg`, `mb_sales_staff` | branch & channel analytics |
| Sales Invoice Item | `mb_weight_kg` | line weight |
| Payment Entry | `mb_branch`, `mb_mobile_provider`, `mb_mobile_reference` | branch takings & mobile money reconciliation |
| Item Price | `mb_branch` (blank = all), `mb_price_type` (Retail/Wholesale/Restaurant/Hotel/Special/Branch) | multi-price management + audit |
| Customer | `mb_preferred_branch`, `mb_phone_verified` | mobile profile |
| Supplier | `mb_supplier_kind` (Fisherman/Cooperative/Wholesaler/Importer) | supplier/yield analytics |

All custom fields are created idempotently by
`manase_butcher/setup/custom_fields.py` on every `bench migrate`.

---

## 7. Navigation / App launcher

`[MANASE CUSTOM]` Workspaces (native Frappe workspace JSON, role-filtered):

- **MANASE BUTCHER** (hub: Today KPIs, branch performance chart, shortcuts)
- **Sales** (POS, Sales Invoices, Customer/Mobile Orders, Returns, Customer Credit)
- **Fish Inventory** (Stock/Branch Stock, Receiving, Processing, Transfers, Waste, Reconciliation, Batches)
- **Purchases** (Suppliers, Fish Receiving, Purchase Receipts/Invoices, Supplier Payments)
- **Customers** (Customers, Credit, Payments, Mobile Orders)
- **Branches** (Branches, Branch Stock, Daily Closing, Branch Performance)
- **Expenses** (Fish Expenses, approvals)
- **Reports** (all script reports grouped)
- **Settings** (Manase Butcher Settings, Price audit, OTP/SMS/FCM)

Mobile navigation is specified in Part 6.

---

## 8. Development Phase Mapping

| Phase | Scope (spec §45) | Delivered in app |
|---|---|---|
| 1 Foundation | app, workspace, roles, branches/warehouses, products, customers, suppliers | setup wizard code, workspaces, roles, custom fields, Branch/Species/Settings |
| 2 Fish Operations | receiving, KG tracking, processing, yield, waste, transfers, branch receiving, reconciliation | Fish Receiving/Processing/Waste/Transfer/Reconciliation + reports |
| 3 Sales & Finance | POS, sales, payments, credit, expenses, daily reconciliation, profitability | POS page, Customer Order back-office, Fish Expense, Closing, finance reports |
| 4 Customer Mobile | OTP, branches/nearby, catalog, KG cart, checkout, orders, tracking | full `fish_mobile` API + Flutter app (separate repo/target) |
| 5 Advanced | delivery, push, SMS/WhatsApp, loyalty, promotions, analytics, supplier performance, batch traceability | FCM/SMS hooks, Notification Log, Batch + reports; loyalty/promotions via Pricing Rule roadmap |

See Part 10 for task-level phasing and Definition of Done per phase.
