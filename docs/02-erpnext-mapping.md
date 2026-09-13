# Part 3 — ERPNext Mapping, Configuration & Data Relationships

Tag legend: `[ERPNext STANDARD]` · `[ERPNext CONFIGURATION]` · `[MANASE CUSTOM]` · `[MOBILE]` · `[API]`

---

## 1. Master data provisioning (`after_install` / setup wizard)

The app's `manase_butcher/setup/install.py` creates, idempotently, for the target Company:

### 1.1 UOMs `[ERPNext CONFIGURATION]`

- **Kg** (must be stock/selling UOM for fish), Piece (alternate, UOM conversion per item,
  e.g. whole fish by piece), Box/Crate where needed.

### 1.2 Item Groups `[ERPNext CONFIGURATION]`

```
All Item Groups
├── Fish
│   ├── Fresh Fish           (whole/raw by species)
│   ├── Frozen Fish
│   ├── Processed Fish
│   │   ├── Cleaned
│   │   ├── Fillet
│   │   ├── Steaks / Cuts
│   │   └── Other Products
│   └── Fish Waste           (valued items: Fish Waste – generic; stockable, zero/weight valuation)
├── Packaging
└── Services (delivery fee as item)
```
Item Attributes: Grade (A/B/C), Size (S/M/L/XL), Freshness (Fresh/Frozen), Preparation
(Whole/Cleaned/Fillet/Steak/Cut). Implemented both as attributes and as searchable custom fields.

### 1.3 Warehouse tree `[ERPNext CONFIGURATION]`

```
MANASE BUTCHER LTD
├── Central Fish Warehouse - MB
│   ├── Central Raw Fish - MB          (mb_warehouse_kind = Central Raw)
│   ├── Central Processed Fish - MB    (Central Processed)
│   ├── Fish Processing Floor - MB     (Processing / WIP)
│   ├── Fish Waste - MB                (Waste)
│   └── Fish In-Transit - MB           (Transit)
├── Masaki Warehouse - MB              (mb_warehouse_kind = Branch, mb_branch = Masaki)
├── Mikocheni Warehouse - MB
├── Sinza Warehouse - MB
└── Kariakoo Warehouse - MB
```
Every physical branch therefore has a real Warehouse in the Stock Ledger (Rule 2). Branch creation
in **Branch** doctype auto-creates/links the Warehouse and Cost Center.

### 1.4 Cost Centers `[ERPNext CONFIGURATION]`

```
Main - MB
├── Central Operations - MB
├── Masaki - MB
├── Mikocheni - MB
├── Sinza - MB
└── Kariakoo - MB
```
Sales invoices, expenses, waste issues and stock adjustments carry the branch Cost Center → branch
P&L works with standard ERPNext financials.

### 1.5 Accounts (standard CoA additions) `[ERPNext CONFIGURATION]`

- Cash: Cash - Masaki/Mikocheni/Sinza/Kariakoo - MB; Petty Cash HO
- Mobile money wallet accounts (current assets): M-Pesa Wallet - MB, Tigo Pesa Wallet - MB,
  Airtel Money Wallet - MB, HaloPesa Wallet - MB
- Fish Waste & Losses (expense), Stock Adjustments - MB, Cash Over/Short - MB
- Cost of Goods Sold – Fish (standard COGS), Delivery Income (income)
- Supplier Payables & Customer Receivables (standard)

### 1.6 Modes of Payment & Price Lists `[ERPNext CONFIGURATION]`

Modes: Cash, M-Pesa, Tigo Pesa, Airtel Money, HaloPesa, Bank Transfer, Card, Credit
each linked to the right account (mobile wallets/bank/cash).
Price Lists: Standard Selling (Retail), Wholesale Selling, Restaurant Selling, Hotel Selling,
Special; per-branch pricing uses Item Price custom fields `mb_branch` + `mb_price_type`; the POS
and API resolve price with priority: customer/special → branch+type → price list → standard.

### 1.7 Naming series `[ERPNext CONFIGURATION]`

REC- (receiving), PROC-, WASTE-, TR-, RECON-, RES-, MO-, EXP-, CLOSE- registered in Numbering
Series; Sales Invoice/Purchase Receipt series default; key series role-permission controlled.

---

## 2. Fish Product Master (Item extension) `[ERPNext STANDARD]` + `[MANASE CUSTOM]`

| Attribute | Implementation |
|---|---|
| Fish name | Item name (e.g. "Red Snapper - Fillet") |
| Species | custom Link to **Fish Species** (`mb_species`) |
| Category | Item Group + `mb_fish_category` |
| Grade | Item Attribute + `mb_grade` |
| Size | Item Attribute + `mb_size` |
| Fresh/Frozen | Item Attribute + `mb_freshness` |
| Whole/Cleaned/Fillet/Cut | Item Attribute + `mb_preparation`; naming convention "Species - Preparation" |
| UOM | stock/selling UOM Kg (Piece with conversion where required) |
| Purchase / Retail / Wholesale / Restaurant / Hotel / Branch price | Item Price rows with `mb_price_type` (+ `mb_branch`); valuation from landed cost |
| Minimum/Maximum stock | standard **Item Reorder** rows per warehouse (reorder level/qty) → Low Stock report |
| Image, barcode | standard Item image/barcode (mobile catalog uses image URL) |
| Sellable flag | `mb_sellable` (processing outputs and catalog only show sellable items) |

Example catalogue: Red Snapper - Whole / - Cleaned / - Fillet; Tuna - Whole / - Cut;
King Fish - Whole / - Fillet; plus generic "Fish Waste".

Price changes: server-side only, each write to Item Price inserts a **Price Change Log**
(item, branch, type, old→new, user, reason); POS/API never write prices.

---

## 3. KG / Weight Tracking Architecture `[MANASE CUSTOM]`

### 3.1 Why KG reconciles automatically

Fish Items transact in stock UOM **Kg**, so every standard ledger row already is a KG movement:
`Stock Ledger Entry.actual_qty` = KG in/out; `qty_after_transaction` = KG remaining;
`stock_value_difference` = money movement; `valuation_rate` = moving/weighted average cost/KG
(Weighted Average / Moving Average valuation per warehouse; FIFO optional).

### 3.2 KG stage fields (stamped on Stock Entry via custom fields)

`custom_mb_stage` ∈ Receiving / Processing Input / Processing Output / Waste / Transfer Dispatch /
Transfer Receipt / Sale / Return / Adjustment, plus source-document links
(`custom_mb_fish_processing`, `custom_mb_fish_waste_record`, `custom_mb_fish_transfer`) and
`custom_mb_branch`. Sales KGs come from Sales Invoice/SLE (voucher type) and Sales Invoice Item
`mb_weight_kg`.

### 3.3 Weight records at every stage

| Stage | Weight recorded on |
|---|---|
| Receiving | Fish Receiving Item gross/tare/net Kg → PR Item qty (Kg) |
| Processing input/output/waste | Fish Processing children → Manufacture Stock Entry |
| Transfer sent/received | Fish Transfer Item sent_kg / received_kg → two transfer Stock Entries |
| Sale | Sales Invoice Item `mb_weight_kg` (defaults = qty Kg) |
| Return | Sales Return items (Kg) |
| Adjustment | Reconciliation child physical/expected/variance → Stock Reconciliation |
| Reservation | Stock Reservation Entry (Kg) / Stock Reservation custom doc |

### 3.4 "Where Did The KG Go?" reconstruction

For item × warehouse(s) × period, the report queries SLE:

```
opening_qty  = latest qty_after_transaction before period (or 0)
+purchases   = voucher_type Purchase Receipt
+proc_in/out = Stock Entry purpose Manufacture, sign by direction & stage
+transfers   = Stock Entry Material Transfer (in/out by warehouse side)
−sales       = Sales Invoice (non-return)
+returns     = Sales Invoice is_return
−waste       = Stock Entry Material Issue linked to Fish Waste Record
±adjustments = Stock Reconciliation
closing_qty  = opening + Σ movements   (must equal latest qty_after_transaction)
```
Any disagreement is highlighted as a ledger integrity warning — the report is read from the
ledger, not from custom document totals (Rule 10).

---

## 4. Branch Architecture `[MANASE CUSTOM]`

**Branch** fields: branch name, code, company, linked Warehouse (auto-provisioned), Cost Center,
address (Link Address), phone, manager (User), latitude, longitude, opening/closing hours,
delivery radius km, default price list, active, opening stock optional.

Data isolation mechanics (see Part 3 permissions doc):

1. **User Permission** records: Branch Manager/User → Branch (and child Warehouses & Cost Centers
   via "apply to all child warehouses/companies" and linked documents).
2. Hook `permission_query_conditions` / `has_permission` for Sales Invoice, Payment Entry,
   Stock Entry, Purchase Receipt and every custom transactional DocType: branches filtered by
   `custom_mb_branch` / warehouse branch link; head-office roles bypass.
3. POS page branch dropdown is restricted the same way; API keys never bypass.
4. Branch stock views: standard Stock Balance/Bin filtered by branch warehouses + custom
   "Branch Stock" report; mobile availability only reads the selected branch warehouse.

---

## 5. Fish Processing Architecture `[MANASE CUSTOM]`

- One source raw item (whole fish) may produce many sellable outputs + waste rows.
- Outputs are existing Items ("Red Snapper - Cleaned", "Red Snapper - Fillet", …) — product master
  grows once per species×preparation.
- Stock Entry purpose **Manufacture** from Central Raw (via Processing Floor optionally):
  raw lines `t_warehouse` blank (out), product lines `t_warehouse` Central Processed,
  waste line to Fish Waste warehouse.
- `fg_bom` optional (BOM per species gives standard yield); actual yield captured vs BOM expected
  for deviation analytics. Processing cost (labour/ice/packaging) added via additional_costs on
  the Stock Entry → true product cost.
- Yield%/Waste% stored per document; Fish Batch inherits totals; drill-down in Yield report by
  species/supplier/processor/batch/date to identify high-loss suppliers/teams.

## 6. Waste Architecture `[MANASE CUSTOM]`

Waste is a **stockable item flow** (never an invisible deletion):

```
Processing → Fish Waste item into Waste WH (Manufacture output, KG preserved)
Spoilage/Expired/Damaged/Dropped/Staff Consumption/Unknown Loss
           → Fish Waste Record → Material Issue out of branch/central WH (cost to Fish Waste & Losses)
Customer Return of unusable fish → Waste Record category Customer Return (+credit note to customer)
Transfer discrepancy missing KG → Waste Record (Transfer Discrepancy reason)
```
Approval: threshold KG or value (settings) and "Unknown Loss" always require approval workflow.
High-waste alerts: Notification when branch daily waste KG/value crosses settings %.

## 7. Reconciliation Architecture `[MANASE CUSTOM]`

Expected quantities are *derived* (never manually editable) from ledger movements between the
last approved reconciliation and the count date; physical count entered; variance and reason;
approval workflow; on approval a standard Stock Reconciliation posts differences; the custom doc
stores opening/expected/physical/variance snapshot permanently. KPI: unreconciled variance KG per
branch on the dashboard.

## 8. Reservation / Availability Architecture `[API]` `[MANASE CUSTOM]`

- Preferred path: standard **Stock Reservation Entry (SRE)** against the Sales Order created for
  the mobile order, warehouse = branch warehouse; SRE increments `Bin.reserved_qty`, so standard
  projected quantity ("actual − reserved") is availability everywhere.
- Fallback (if SRE unavailable): custom **Stock Reservation** ledger + `Bin.custom_mb_custom_reserved_kg`.
- `stock_utils.available_kg(item, warehouse)` = projected qty (actual − SRE reserved − custom
  reserved − already-in-cart session holds for short holds).
- Checkout re-checks and reserves atomically (row locks / `for_update` on Bin); orders exceeding
  availability are rejected (Rule 4). Expired unconfirmed reservations auto-release (scheduled job).

---

## 9. Purchase / Accounting Architecture

### Buying
Fish Receiving → Purchase Receipt posts stock at purchase cost; transport/handling/ice rows added
as Purchase Taxes **Add to Valuation = 1** (landed cost at intake). Where invoices arrive later,
standard **Landed Cost Voucher** is used instead/also. Purchase Invoice & Payment Entry handle
supplier balances (supplier debt on dashboard from standard payables).

### Selling cost & profitability
ERPNext standard inventory accounting gives COGS per Sales Invoice at the running valuation rate
(which already includes landed + processing additional costs). Branch P&L:

```
Revenue (by channel)            GL income, cost center = branch
− COGS (weighted landed/processed cost of the KG sold)
= Gross Profit
− Operating expenses            Fish Expense JEs + wage postings
= Net Profit
```
Profitability Report (Part 7) reads GL Entry by cost center/account/date — standard numbers, fish
dimensions (KG, species, channel) joined from invoices.

### Money channels
Cash/card/bank via standard Payment Entry; mobile money modes post to wallet accounts; provider
callbacks (`/api/method/.../webhooks.mobile_payment_callback`) create Payment Entries with provider
reference, reconciled in Daily Closing against provider statements.

---

## 10. Data Relationships (ERD, textual)

```
Supplier 1──* Fish Receiving *──1 Purchase Receipt 1──* Purchase Invoice ──* Payment Entry
Fish Receiving 1──* Fish Batch 1──1 Batch(standard)
Fish Processing *──1 Fish Batch ; Fish Processing 1──1 Stock Entry(Mfg)
Fish Waste Record 1──1 Stock Entry(Issue)
Fish Stock Transfer 1──2 Stock Entry (out/in via Transit)
Branch 1──1 Warehouse ; Branch 1──1 Cost Center ; Branch 1──* User(User Permission)
Branch 1──* Fish Stock Transfer(target) ; Warehouse(branch) *──* Item : Bin
Branch Stock Reconciliation 1──1 Stock Reconciliation(standard)
Customer 1──* Customer Order 1──1 Sales Order 1──* SRE 1──1 Sales Invoice 1──* Payment Entry
Customer Order 1──* Customer Order Item / Payment ; Sales Invoice.custom_mb_customer_order → order
Branch 1──* Fish Expense 1──1 Journal Entry
Branch 1──* Daily Branch Closing
Item Price(mb_branch, mb_price_type) *──1 Item ; Price Change Log audits Item Price
Mobile Session/Device *──1 Customer ; OTP Log *──1 phone ; Notification Log *──1 Customer
Audit Log ── any doctype/name (polymorphic via Link options + document name)
```
All ledgers (stock & GL) remain standard; custom docs are operational front-ends with immutable
audit + snapshots.
