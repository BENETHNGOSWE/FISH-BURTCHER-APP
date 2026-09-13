# Part 7 — Reports, Dashboards, Workspaces

Tags: `[MANASE CUSTOM]`, `[ERPNext STANDARD]`, `[ERPNext CONFIGURATION]`.

All custom reports are **Script Reports** (standard Frappe mechanism: `.json` + `.py` execute +
`.js` filters) shipped in the app and installed via `bench migrate`; they read standard ledgers,
so figures always reconcile with ERPNext.

---

## 1. Reports catalogue

### Fish & KG (Fish Inventory module)

**1. Where Did The KG Go? (`kg_movement`)** — the flagship report.
Filters: company, item (or species), branch/warehouse (multi incl. Central), from/to dates.
Columns: Item, Opening KG, Purchases, Processing In, Processing Out/Sellable, Transfers In,
Transfers Out, Sales, Sales Returns, Waste, Adjustments, Closing KG (computed), Ledger Closing KG,
Difference (must be 0). Built purely from Stock Ledger Entry classified by voucher type +
custom stock-entry stage/source links (Part 3 §3.4).

**2. Branch Stock Reconciliation Summary (`branch_reconciliation`)**
Per branch/period: expected vs physical KG & value per item, variance KG/value/%, reasons,
approver, pending counts; branches with missing counts flagged.

**3. Processing Yield (`processing_yield`)**
Groups Fish Processing by species/item/supplier (via batch)/processor/branch/date/batch:
input KG, sellable KG, waste KG, yield%, waste%, processing cost, cost/KG, deviation vs BOM.
Identifies suppliers/teams with high loss (spec §12).

**4. Waste Analysis (`waste_analysis`)**
Waste KG/value by category, branch, item, employee, period; % of intake/sales; top offenders;
approval status.

**5. Low Stock by Branch (`low_stock_branch`)**
Bin projected qty vs standard Item Reorder levels per branch warehouse; fish below minimum;
suggested replenishment to max level (drives transfer advice).

**6. Fish Batch Traceability (`batch_traceability`)**
Enter batch/ERPNext Batch: supplier, receiving doc/date/KG, processing output & waste, transfers
to branches (KG each), sales (invoices/customers/dates), current KG — forward & backward trace
(spec §37).

### Sales & customers (Fish Sales module)

**7. Sales Analysis (`sales_analysis`)**
Sales KG, revenue, discounts, tax, tender split by day/branch/fish item/employee/customer/channel
(Walk-in/Wholesale/Restaurant/Mobile); pivot via standard report builder too.

**8. Branch Performance (`branch_performance`)**
One row per branch/day or period: Sales value, KG sold, Waste KG/value, GP (revenue−COGS),
Expenses, Net Profit, receivables added, closing stock KG; drill-down to branch workspace.

**9. Customer Debt & Aging (`customer_debt_aging`)**
Outstanding per customer with current/7/30/60/90+ buckets, credit limit, last payment, sales
staff; statement action. (Standard AR built-in report remains available.)

**10. Profitability (`profitability`)**
Revenue, COGS (GL/SLE), Gross Profit & %, operating expense categories, Net Profit for company /
branch / species / channel; actual cost = landed + processing valuation (Part 5 §5).

### Standard reports reused (workspace links) `[ERPNext STANDARD]`
Stock Balance, Stock Ledger, Stock Projected Qty, Stock Aging, Item-wise Price, Purchase Receipt/
Invoice reports, Purchase Order Analysis, Accounts Payable/Receivable, General Ledger, Trial
Balance, P&L per cost center, Payment Ledger, Bank Reconciliation, Gross Profit (built-in),
Stock Valuation, Batch Item-wise Ledger.

---

## 2. Dashboards / Workspace composition `[MANASE CUSTOM]`

### MANASE BUTCHER hub ("TODAY")
Number cards (created in setup, role-aware):
- Today's Sales (value & count), Today's Purchases, Today's Expenses, Today's Profit (GP)
- Fish Received KG today, Fish Sold KG today, Fish Waste KG today
- Current Stock KG (all / by branch), Customer Debt total, Supplier Debt total
- Pending mobile orders, Open transfers (in transit), Pending reconciliations
Charts: Sales last 14 days (line, by branch), KG received vs sold vs waste (bar), Branch
performance table/bar; quick links: POS, New Receiving, Processing, Transfer, Reconciliation,
Closing, Mobile Orders; "Where Did The KG Go?" report shortcut.

### Sub-workspaces
Sales (POS page shortcut, Sales Invoices by channel, Customer Orders, returns, prices),
Fish Inventory (Branch Stock view, receiving, processing, transfers, waste, reconciliation,
batches), Purchases (suppliers, receiving, PR/PI, supplier payments), Customers (customers,
credit/aging, payments, mobile orders), Branches (branches, stock, transfers in/out, daily
closing, performance), Expenses (expenses, approvals), Reports (all custom + standard grouped),
Settings (settings, price audit, OTP/SMS/FCM config, audit log).

### Branch drill-down
Branch workspace/desk view filtered by User Permission: opening that branch's card filters number
cards and reports via `branch` context; branch managers land directly on their branch.

### Mobile operator screens (desk)
"Mobile Orders" list view with branch filter, status kanban-like grouping (standard List filters),
quick Accept/Reject/Ready/Deliver buttons (server actions) and FCM logs per order.

---

## 3. KPI definitions (single source)

| KPI | Definition / source |
|---|---|
| KG received | Σ Purchase Receipt item qty (Kg), posted via Fish Receiving, period |
| KG sold | Σ Sales Invoice Item mb_weight_kg/qty (non-return), period, branch |
| KG wasted | Σ Stock Entry Material Issue linked to Fish Waste Record |
| Yield % | Σ sellable output KG / Σ processing input KG |
| Waste % | waste KG / (input KG for processing; sales KG at branch) |
| Current stock KG | Σ Bin.projected/actual qty for fish warehouses |
| Expected/Physical/Variance KG | Reconciliation snapshot fields |
| GP | Revenue − COGS posted in GL by branch cost center |
| Net Profit | GP − operating expense JEs/GL by branch cost center |
| Customer/Supplier debt | standard receivable/payable GL totals |
