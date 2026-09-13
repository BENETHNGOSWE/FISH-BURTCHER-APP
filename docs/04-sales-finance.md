# Part 5 — Sales, POS, Credit, Expenses, Closing & Profitability

Tags: `[MANASE CUSTOM]`, `[ERPNext STANDARD]`, `[ERPNext CONFIGURATION]`.

---

## 1. Sales Architecture

### 1.1 Channels (Sales Invoice `custom_mb_sales_channel`)
Walk-in (POS), Wholesale, Restaurant, Mobile. Channel drives default price list/type and reports.

### 1.2 POS page (`fish_pos`) `[MANASE CUSTOM]`
- Branch picker limited by the user's permitted branches; branch sets warehouse, cost center,
  cash/wallet accounts and POS profile.
- Customer selector (Walk-in default); selecting a credit customer shows live outstanding and
  enforces standard Credit Limit before Credit tender.
- Item grid: search by species/local name, preparation, grade, freshness; image; shows branch
  available KG (standard projected qty) and blocks lines above availability.
- Weight entry in KG (3 decimals); price auto-resolved:
  `Branch+price type Item Price → price list Item Price → Item standard rate`.
- Discount %/amount with per-role Maximum Discount (POS Profile / settings); reason logged.
- Split tender across Cash + each mobile money provider + Card/Bank + Credit; change calculation.
- Submit creates a **Sales Invoice** (POS, is_pos) and **Payment Entry** per tender in one server
  method (`fish_sales/api/pos.py::submit_pos_sale`) — atomic, server-priced (client prices are
  never trusted). Mobile-money tender stores provider + transaction reference; reconciliation
  matching in Daily Closing.
- Receipt: custom fish-branded Print Format with branch, KG, items, tenders, QR/receipt no;
  reprint allowed; cancel requires role + reason (Audit Log); returns use standard Credit Note
  flow with KG back into branch stock (or Waste Record if unusable).

### 1.3 Mobile sale `[MANASE CUSTOM]` / `[API]`
Customer Order is converted to a Sales Invoice on fulfilment (see Part 6); invoices carry
`custom_mb_branch`, `custom_mb_sales_channel = Mobile`, `custom_mb_customer_order`, total KG.

### 1.4 Wholesale/restaurant
Same POS page with price type Wholesale/Restaurant and credit terms; customer statements and
invoices standard. Mobile ordering for restaurants is a phase-5 extension of the same API
(B2B accounts).

---

## 2. Customer Credit Architecture `[ERPNext STANDARD]` + `[MANASE CUSTOM]`

- Credit Limit per Customer (and per branch/company using standard Credit Limit child table);
  Bypass Credit Limit Check right reserved to GM/Owner.
- Sale 210,000 / paid 100,000 → Sales Invoice 210,000 + Payment Entry 100,000 →
  outstanding 110,000 on standard Accounts Receivable (customer ledger/Filippino?—standard GL).
- Partial payments any time: Payment Entry against invoices (standard references); payments via
  mobile money linked automatically by callback reference.
- **Debt aging**: script report with 0–7/8–30/31–60/61–90/90+ buckets, statements export.
- Reminders: scheduled job (settings: days + time) renders SMS/WhatsApp template, logs in
  Notification Log; credit hold enforced in POS and mobile checkout server-side.
- Customer-facing endpoints (own data only): `/customer/payments`, balances & invoice list.

---

## 3. Expense Architecture `[MANASE CUSTOM]`

- Fish Expense categories: Rent, Transport, Fuel, Electricity, Water, Packaging, Maintenance,
  Staff Meals, Other (+ free-text account selection; category → default expense account mapping
  in settings child table).
- Every expense: branch, cost center, category, account, amount, mode of payment + paying
  account, employee, date, receipt attachment, approval status.
- On approval/submit → **Journal Entry**: Dr Expense (cost center branch) / Cr Cash or mobile
  wallet/bank (branch account). Edit after posting only via standard cancel/amend, audited.
- Threshold workflow: branch manager limit (settings), above → GM; Accountant sees all.

---

## 4. Daily Branch Closing `[MANASE CUSTOM]`

```
DAILY CLOSING (CLOSE.DATE.BRANCH unique)
  Fetch from ledger for branch+date:
    Sales total (and channel split), KG sold, invoice count
    Expected per Mode of Payment (Payment Entries incl. mobile references)
    Credit sales total, returns total, expenses paid from cash (Fish Expenses)
  Count: Actual cash; confirm wallet totals per provider (M-Pesa/Tigo/Airtel/Halo)
    → expected/actual/variance per tender; cash variance highlighted
  Opening KG (fish lines at day start) / Closing KG (projected now)
  Manager explanation mandatory for any variance; approve → Cash Over/Short JE
  After approval: same-day POS blocked for Cashier (override by Manager, audited)
```
Closing never edits historical invoices — it reads and reports; only variance adjustment JE posts.

---

## 5. Profitability Architecture `[ERPNext STANDARD]` + `[MANASE CUSTOM]`

Real fish cost (never simple sell−buy):

```
Actual cost of a KG = purchase price/kg + allocated transport/handling/ice (landed)
                      + allocated processing additional costs (labour, ice, packaging)
                    = ERPNext moving-average (or FIFO) valuation_rate on the branch warehouse
COGS                = Σ valuation_rate × KG sold (posted by Sales Invoice to COGS account)
Gross Profit        = Revenue − COGS            (GL, branch cost center)
Net Profit          = Gross Profit − Operating Expenses (Fish Expense JEs + other GL expenses)
```

- Landed costs: Purchase Receipt valuation taxes at intake, or Landed Cost Voucher for bills
  arriving later; Processing Stock Entry `additional_costs` carry processing cost into product
  valuation; transfer adds no cost (stock moves at value).
- **Profitability Report**: parameters date range, branch, species/item, channel; columns Revenue,
  KG sold, COGS (from GL/SLE), Gross Profit & GP%, Expenses (by category), Net Profit; built from
  GL Entry joined to invoices/items (and SLE valuation for COGS cross-check).
- **Branch Performance report/table on dashboard**: Sales, KG sold, Waste KG, GP, Expenses, NP,
  receivables — drill-through to branch workspace filtered.

---

## 6. Money & Mobile Payment Integration `[ERPNext CONFIGURATION]` `[API]`

- Modes of Payment map to branch cash accounts and provider wallet accounts.
- Mobile flows:
  1. Checkout chooses provider → order created with payment status Pending; API returns
     provider reference request (STK push triggered via provider gateway in phase-5 plugin,
     or teller-initiated flow).
  2. Provider callback `POST /api/method/manase_butcher.fish_mobile.api.webhooks.mobile_payment_callback`
     verified by signature/secret (settings per provider, IP allow-list) → matches amount+reference
     to order → creates Payment Entry (wallet account, customer receivable) → FCM receipt.
  3. Branch-side payments at POS: cashier enters confirmation code; reference uniqueness enforced.
- Refunds: Payment Entry (reverse) + reason; mobile refund via provider API recorded & audited.

---

## 7. Notifications tied to money/ops `[MANASE CUSTOM]`

Low stock (reorder level), stock variance over threshold, high waste %, debt due, supplier payment
due, new/transfer/transfer-discrepancy events: standard **Notification** documents (created in
setup) for desk users + custom FCM/SMS dispatcher for customers (order events) — see Part 6 §8.

---

## 8. Sales & Finance reports (Part 7 details the query design)

Sales by day/branch/fish/employee/customer; Retail/Wholesale/Restaurant/Mobile splits; Customer
balances & aging & payment history; Revenue/COGS/GP/Expenses/NP; Cash & mobile money takings;
Supplier balances (standard Accounts Payable) — all branch/cost-center scoped.
