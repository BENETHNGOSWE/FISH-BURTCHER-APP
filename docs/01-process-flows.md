# Part 2 — Business Process Diagrams & Flow Specifications

Tag legend: `[ERPNext STANDARD]` · `[ERPNext CONFIGURATION]` · `[MANASE CUSTOM]` · `[MOBILE]` · `[API]`

---

## 1. Fish Receiving flow `[MANASE CUSTOM]` + `[ERPNext STANDARD]`

```
Supplier/Fisherman arrives
        │
        ▼
 Fish Receiving (REC.YYYY.#####)            [MANASE CUSTOM, Submittable]
  header: supplier, date/time, employee,
          central raw warehouse, vehicle, payment status
  lines : item, grade, freshness, qty_kg, pieces, rate/kg, amount
  costs : Transport, Handling, Ice, Storage, Other (account + amount)
        │ validate weights > 0, totals, supplier credit status
        ▼ Submit
        ├─► Purchase Receipt (stock in, Central Raw Warehouse, +KG)
        │     purchase taxes rows flagged "Add to Valuation" → landed cost
        │     (optional Purchase Invoice per setting "Create PI on receive")
        ├─► ERPNext Batch per line (batch id = Fish Batch) + custom Fish Batch doc
        │     received_kg, supplier, grade, date
        ├─► back-links: PR.custom_mb_fish_receiving; Receiving.purchase_receipt
        └─► Audit Log (created)
```

Validation rules:

- `total_kg = Σ lines.qty_kg`; `purchase_total = Σ line.amount`
- `total_landed_cost = purchase_total + Σ landing costs`;
  `landed_cost_per_kg = total_landed_cost / total_kg`
- On cancel/amend, the Purchase Receipt is cancelled first (standard guard); Audit Log records reason.
- Weight capture supports gross/tare/net: line fields `gross_weight_kg`, `tare_weight_kg`,
  `qty_kg = gross − tare` (auto).

Example from spec: 500 KG Red Snapper @ 8,000 = 4,000,000 + 100,000 transport + 50,000 handling →
landed 4,150,000 → 8,300/KG effective cost flowing into stock valuation.

---

## 2. Processing / Butchering flow `[MANASE CUSTOM]`

```
 Fish Processing (PROC.YYYY.#####)
  header: date, employee(processor), source warehouse = Central Raw,
          target warehouse = Central Processed, waste warehouse, batch(optional)
  INPUT rows : item (whole fish), batch, qty_kg
  OUTPUT rows: item (cleaned/fillet/cut), qty_kg, target_warehouse, is_waste?
               (waste rows target Waste Warehouse)
        │
        │  validate: input_kg = sellable_kg + waste_kg   (tolerance in Settings, default 0)
        │  compute : yield_pct = sellable/input×100, waste_pct = waste/input×100
        ▼ Submit (workflow: Draft → Pending Approval → Approved → Processed*)
        └─► Stock Entry "Manufacture"
              items: raw fish (source) qty > 0 out; cuts & fish waste (targets) qty < 0 in
              fg_completed_qty / valuation: output valued from input + processing_cost
              custom_mb_fish_processing = doc name; custom_mb_stage = "Processing"
            Fish Batch updated: sellable_kg, waste_kg, yield_pct
            Audit Log
```

\* Approval workflow applies when `processing_cost` or input KG exceeds settings threshold;
otherwise auto-approves. Yield comparison by fish/supplier/processor/branch/date/batch is the
**Processing Yield Report** (Part 7).

---

## 3. Waste flow `[MANASE CUSTOM]`

```
 Fish Waste Record (WASTE.YYYY.#####)
  header: date, branch, warehouse, category
          (Processing Waste, Spoilage, Expired, Damaged, Dropped,
           Customer Return, Staff Consumption, Unknown Loss, Other)
  lines : item, qty_kg, valuation rate auto, reason (mandatory per line)
        │ requires_approval = total_kg ≥ settings.waste_approval_kg OR category ∈ {Unknown Loss}
        ▼ Submit → workflow (Draft → Pending Approval → Approved/Rejected)
        └─► Stock Entry "Material Issue" from the warehouse (stock out, −KG)
              expense account = "Fish Waste/Loss" (settings), cost center = branch CC
              custom_mb_fish_waste_record, custom_mb_branch
            Audit Log incl. reason; large/unexplained losses block until approval.
```

There is no path for KG to disappear without a Waste Record, Reconciliation (reasoned), or a
documented transfer variance.

---

## 4. Stock Transfer flow (Central ↔ Branch, two-leg transit) `[MANASE CUSTOM]`

```
 Fish Stock Transfer (TR.YYYY.#####)
  header: source warehouse (Central), target branch/warehouse, transit warehouse,
          driver/employee, vehicle
  lines : item, sent_kg, (later) received_kg, variance_kg, variance_reason

  Draft ──submit──► Submitted ──approve──► Approved ──dispatch──► Dispatched
                                                        │
                                       Stock Entry "Material Transfer"
                                       Source Warehouse → In-Transit Warehouse (−KG source)
                                                        │
                              branch team "Receive":
                              enter received_kg per line; variance computed
                                                        ▼
                                                   Received ──► Completed
                                       Stock Entry "Material Transfer"
                                       In-Transit → Branch Warehouse (+KG branch)
```

Rules:

- `variance_kg = received_kg − sent_kg`; **reason mandatory on any non-zero variance**.
- Negative variance on receipt posts an immediate **Fish Waste Record (category "Transfer
  Discrepancy")** for the missing KG (or it remains in transit pending investigation — selectable
  in settings; default: ask on receive).
- Dispatch/receive timestamps, dispatched by / received by stored and audited.
- Branch manager can only receive transfers *to their branch* (User Permission + server check).

---

## 5. Branch Inventory & Reconciliation flow `[MANASE CUSTOM]`

```
 Branch Stock Reconciliation (RECON.YYYY.#####)
   header: branch, warehouse, date, employee
   action "Fetch Expected Stock":
     for each fish item with activity/stock in the branch:
        opening_kg         (SLE qty at start of day/period)
        + received_kg      (transfers in, purchase receipts)
        − transferred_out  (transfers out)
        − sales_kg         (Sales Invoices incl. mobile)
        − waste_kg         (Fish Waste / material issues)
        + returns_kg       (sales returns)
        ± adjustments_kg   (prior reconciliations)
        = expected_kg
   user counts physical_kg → variance_kg = physical − expected
   reason mandatory where |variance| ≥ settings.variance_approval_kg
        ▼ Submit → Approval workflow (Branch Manager → Inventory Manager/GM)
        └─► standard Stock Reconciliation (Branch Warehouse) to physical quantities
            (current valuation rate; gain/loss to stock adjustment account, branch cost center)
            custom links + Audit Log (old/new KG + reason)
```

This makes the physical count a first-class, ledger-posting event (spec §16).

---

## 6. POS / Sales flow `[MANASE CUSTOM page]` + `[ERPNext STANDARD]`

```
 POS page (fish_pos, opens from Sales workspace)
   1. select branch (locked to the user's permitted branch(es)) → sets warehouse + cost center
   2. walk-in customer or select customer (credit check if credit)
   3. add lines: choose fish (search species/cut/fresh-frozen) → enter KG →
      price chosen by price type (Retail/Wholesale/Restaurant/Hotel/Special/Branch)
      via Item Price filtered by branch
   4. discount %/amount (with authority limit)
   5. split payment: Cash, M-Pesa, Tigo Pesa, Airtel Money, HaloPesa, Bank, Card, Credit
   6. Confirm:
        Sales Invoice (POS=1, branch warehouse, customer, channel, custom_mb_total_kg)
        + Payment Entry per paid mode (reference no. for mobile money)
        Credit → invoice outstanding only within Customer Credit Limit (standard check)
   7. Print/email receipt (fish-themed print format)
```

Stock reduction follows standard Sales Invoice stock posting (or POS invoice redemption);
warehouse = branch warehouse — KG is removed from the branch, never central.

---

## 7. Customer credit flow `[ERPNext STANDARD]` + `[MANASE CUSTOM]`

- Credit limit & hold: standard Customer Credit Limit / Credit Limit by branch/company;
  POS and mobile APIs both call the standard credit-limit check before allowing "Credit".
- Partial payment: Payment Entry against invoice (standard); outstanding tracked in GL.
- **Customer Debt Aging report** (script report, Part 7) gives 0/30/60/90+ buckets.
- Debt reminders: scheduled job daily at settings time → SMS/WhatsApp template via SMS gateway;
  Notification Log entry; customers with overdue debt blocked from new credit orders server-side.

---

## 8. Expense flow `[MANASE CUSTOM]`

```
 Fish Expense (EXP.YYYY.#####)
   branch, cost center (auto), category (Rent/Transport/Fuel/Electricity/Water/
   Packaging/Maintenance/Staff Meals/Other), expense account, amount,
   mode of payment + payment account (cash box or mobile wallet), employee, date,
   supplier (optional), attachments (receipt photo)
        ▼ submit → approval (amount threshold workflow) → Journal Entry:
        Dr Expense Account (cost center = branch)
        Cr Cash/Mobile Wallet/Bank Account (branch)
        Audit Log
```

---

## 9. Daily Branch Closing flow `[MANASE CUSTOM]`

```
 Daily Branch Closing (CLOSE.YYYY.#####)
   branch, date, cashier/manager
   action "Fetch":
     sales_total = Σ Sales Invoice for branch/day (by channel)
     expected per Mode of Payment from Payment Entries + credit amounts
     kg_sold = Σ invoice custom_mb_total_kg
   cashier counts cash & confirms each mobile wallet (with provider totals):
     expected / actual / variance per mode; explanation mandatory on variance
   opening & closing KG snapshots (all fish) for the branch
        ▼ submit → Branch Manager approval; cash over/short JE on variance
   one closing per branch per day (unique constraint); after closing,
   same-day edits/invoices for branch blocked for Cashier (Manager override, audited)
```

---

## 10. Customer order lifecycle (mobile) `[MOBILE]` `[API]` `[MANASE CUSTOM]`

```
PHONE+OTP → select branch (geo nearby/manual) → browse branch stock → enter KG → cart
   → checkout (pickup/delivery, address, time, payment)
        │ POST /orders (server re-validates availability & reservation)
        ▼
Customer Order (MO.YYYY.#####) + Sales Order + Stock Reservation Entry (branch warehouse)
        status: Pending
   branch: Accept (Confirmed) / Reject (auto-release reservation)
        → Preparing → Ready
           ├─ Pickup → Collected
           └─ Delivery → Out for Delivery → Delivered
   payment: prepaid via mobile money callback OR pay at collection/delivery
   completion → Sales Invoice from Sales Order (reserved KG consumed, stock −KG)
              → Payment Entry(s), receipt pushed to app
   Cancel (customer SLA / branch): releases reservation, stock back to available
```

Status rules, timers (auto-release unconfirmed orders after settings minutes — scheduled job),
and notifications (FCM + SMS fallback) are specified in Part 6.

---

## 11. End-to-end validation scenario (spec §42)

The automated test suite (`tests/`) implements the 25-step scenario:

500 KG Red Snapper received (PR/500 KG) → 470 KG produced + 30 KG waste → transfers
100/120/80 KG to Masaki/Mikocheni/Sinza with a −2 KG received variance scenario → mobile
order 5 KG (reservation blocks oversell) → fulfil → Sales Invoice/Payment → branch stock −5 KG →
reconciliation counts → closing → assertions on stock ledger, KG conservation and branch P&L.
