# Part 4 — Roles, Permissions, Workflows, Multi-branch Isolation & Audit Trail

Tags: `[ERPNext CONFIGURATION]`, `[MANASE CUSTOM]`, `[API]`, `[MOBILE]`.

---

## 1. Roles `[ERPNext CONFIGURATION]`

Roles are created by `setup/install.py` (idempotent) with sensible desk/module access. Standard
ERPNext roles (Stock User/Manager, Accounts User/Manager, Buying User, Sales User, POS User,
Item Manager, System Manager) are assigned to users **in addition** to MANASE roles; the MANASE
roles govern the custom DocTypes and branch scoping.

| MANASE role | Standard companion role(s) | Scope |
|---|---|---|
| **Business Owner** | System Manager / Accounts Manager + all | Everything, all branches, settings, approvals, reports, audit log |
| **General Manager** | Stock Manager, Accounts Manager, Sales Manager, Buying Manager | All branches; operational & financial, no system/role admin |
| **Accountant** | Accounts User/Manager | Payments, expenses (finance review), invoices, credit, closing approval, financial reports |
| **Inventory Manager** | Stock Manager | Receiving, processing oversight, transfers, waste, reconciliations, all branches' stock |
| **Procurement Officer** | Buying User, Stock User | Suppliers, Fish Receiving create/submit, purchase documents |
| **Branch Manager** | Stock User, Sales User/Manager, Accounts User (limited) | **Own branch only**: POS oversight, transfers receive, reconciliation, closing, expenses up to limit |
| **Sales Staff** | Sales User, POS User | POS sales, customer orders at own branch |
| **Cashier** | POS User | POS & payments, daily own counts |
| **Processing Staff** | Stock User (manufacture) | Fish Processing (create/submit), processing waste |
| **Warehouse Staff** | Stock User | Receiving, dispatch, receive transfers, waste recording, counts |
| **Delivery Staff** | (none/limited) | Customer Order read + delivery status updates for assigned branch |
| **Customer** | Customer (portal, no desk) | Mobile API only: own profile/orders/payments/addresses; zero Desk access |

---

## 2. Custom DocType permission matrix

C=create, R=read, W=write, S=submit, X=cancel, A=amend, D=delete (draft)

| DocType | Owner | GM | Accountant | Inv Mgr | Procure | Branch Mgr | Sales | Cashier | Process | Warehouse | Delivery |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Manase Butcher Settings | CRW | R | R | R | – | – | – | – | – | – | – |
| Branch | CRW | R | R | R | R | R(own) | R(own) | R(own) | R | R | R |
| Fish Species / Item master | RW (via Item Mgr) | R | – | R | R | R | R | R | R | R | – |
| Fish Batch | CRWX | RWX | R | RWX | R | R(own) | R | – | R | R | – |
| Fish Receiving | CRWXA | RWXA | R | RWX | CRWS | – | – | – | – | R(warehouse) | – |
| Fish Processing | CRWXA | RWXA | R | RWXA (approve) | – | R | – | – | CRWS | – | – |
| Fish Waste Record | CRWXA | RWXA (approve) | R | RWXA (approve) | – | CRW (own, submit) | – | – | CRW | CRW | – |
| Fish Stock Transfer | CRWXA | RWXA | R | RWXA (approve) | C | C(dispatch own)/R+receive | – | – | – | C(dispatch)/receive | R |
| Branch Stock Reconciliation | CRWXA | RWXA | R | RWXA (approve) | – | CRWS (own) | – | – | R(count) | R(count) | – |
| Stock Reservation | R | RWX | – | RWX | – | R(own) | R(own) | – | – | – | R |
| Customer Order | R(all) | RWX | R | R | – | RW (own branch) | RW (process) | R | – | – | RW (delivery) |
| Fish Expense | CRWXA | RWXA (approve) | RWXA | R | – | CRW (own, within limit) | – | – | – | – | – |
| Daily Branch Closing | CRWXA | RWXA | RWX (approve) | R | – | CRWS (own) | – | CR (count) | – | – | – |
| Audit Log / Price Change Log | R | R | R(finance) | R(stock) | – | R(own) | – | – | – | – | – |
| OTP Log / Mobile Session / Device | R | R | – | – | – | – | – | – | – | – | – (via API only, data owner) |
| Notification Log | R | R | – | R | – | R(own) | – | – | – | – | R(own API) |

`(own)` is enforced by User Permissions + query conditions (next section), not just by checkbox.

Standard DocType access (Sales Invoice, Payment Entry, Stock Entry…) is granted via the standard
companion roles and additionally restricted by the branch hooks below.

---

## 3. Multi-branch data isolation `[MANASE CUSTOM]`

Three layers, enforced server-side:

1. **User Permission (standard):** when a Branch is assigned to a user, the app creates User
   Permissions on **Branch**, **Warehouse** (branch warehouse + children), and **Cost Center**.
2. **Query conditions + `has_permission` hooks** (`branch_utils.py`) are registered in `hooks.py`
   for: Sales Invoice, Sales Order, Purchase Receipt, Stock Entry, Payment Entry, Journal Entry,
   Stock Reconciliation and all custom transaction DocTypes. Condition shape:

   ```sql
   EXISTS (SELECT 1 FROM `tabWarehouse` w
           WHERE w.name = <doc>.set_warehouse /* or per-item warehouse join */
             AND w.custom_mb_branch IN (SELECT branch FROM permitted branches for user))
   ```
   custom docs filter directly on `branch` / `target_branch`.
   Roles Business Owner, General Manager, Accountant, Inventory Manager (warehouse docs) bypass.
3. **Write guards in controllers:** transfer receive, reconciliation, closing and POS server
   methods re-check the session user's permission for that branch; mobile endpoints are scoped to
   the token's customer only (Rule 9, §48).

Head Office sees all branches; Branch Manager only theirs; Customer only their own records
(enforced in each API method: `if order.customer != session.customer: throw`).

---

## 4. Workflows `[MANASE CUSTOM]` (fixtures, loaded on migrate)

### 4.1 Fish Stock Transfer
States/transitions:

| From | To | Allowed roles |
|---|---|---|
| Draft | Submitted | Warehouse Staff, Inventory Manager |
| Submitted | Approved | Inventory Manager, GM |
| Approved | Dispatched (action posts outbound SE) | Warehouse Staff, Inventory Manager |
| Dispatched | Received (enter received KG; posts inbound SE) | Branch Manager, Warehouse Staff (target branch) |
| Received | Completed | Branch Manager, Inventory Manager |
| any pre-completion | Cancelled | Inventory Manager, GM (reverses legs) |

### 4.2 Fish Processing
Draft → Pending Approval (when over threshold; otherwise auto Approved) → Approved → Rejected;
Approved allows "Process" (submit posts Manufacture SE). Roles: Processing Staff create; Inventory
Manager/GM approve.

### 4.3 Fish Waste Record
Draft → Pending Approval (threshold KG/value or Unknown Loss always) → Approved/Rejected →
submit posts Material Issue. Approvers: Inventory Manager/GM; Branch Manager may approve small
branch waste within limit.

### 4.4 Branch Stock Reconciliation
Draft → Submitted (Branch Mgr) → Reviewed (Inventory Mgr) → Approved (posts Stock Reconciliation)
/ Rejected (reason). Large-variance counts require GM.

### 4.5 Fish Expense
Draft → Pending Approval → Approved (Accountant/Branch Mgr within limit; GM over limit) →
Rejected; Journal Entry posted on approval/submit.

### 4.6 Daily Branch Closing
Draft → Submitted (Cashier/Manager counts) → Approved (Branch Manager; Accountant/GM review) →
Locked. Variance explanations mandatory; cash over/short JE posted on approval.

### 4.7 Customer Order status (programmatic, not a desk Workflow)
Pending → Confirmed/Rejected → Preparing → Ready → Out for Delivery → Delivered (or Collected) →
Completed; Cancelled with reason from Pending/Confirmed only (SLA). Each transition is a
whitelisted, role-checked server action that notifies the customer (FCM/SMS).

---

## 5. Audit Trail `[MANASE CUSTOM]`

- **Audit Log** DocType (immutable: no edit/delete for any role; created only by server code):
  `timestamp, user, branch, transaction_doctype, transaction_name, action, field_label,
  old_value, new_value, reason, ip_address, device_info`.
- Written (via `audit.log_action`) for: stock/KG adjustments, waste (incl. approval & rejection),
  price changes (Price Change Log mirrored), sale & order cancellation (with reason), payments
  edits/deletes, expenses & approvals, transfer dispatch/receive **with variance**, reconciliation
  approvals, credit limit changes, settings changes, manual journal entries made by the app.
- Standard **Version** history (`track_changes=1`) enabled on all custom transaction DocTypes plus
  Item Price, Customer credit settings; submitted docs use standard cancel/amend (Rule 8: cancelled
  documents remain in the ledger as cancelling entries; nothing is hard-deleted after submit).
- Login/API security events (OTP failures, token revocation) logged in OTP Log / Notification Log.

---

## 6. Security Model `[API]` `[MOBILE]` (summary; full spec in Part 6)

- RBAC (above) + branch User Permissions + server write guards.
- Mobile: phone+OTP only; opaque random bearer token (stored as SHA-256 hash in Mobile Session),
  expiry, refresh, per-device; customers never get Frappe users/desk; every endpoint enforces
  ownership; rate limiting (OTP request/verify, order create) via Redis counters; input validation
  with Frappe `frappe.flags` + explicit whitelisting (guests may call only auth endpoints);
  payment callbacks authenticated by provider secret/HMAC and IP allow-listing; no ERPNext
  credentials in the app; no generic REST exposure to customers (only the whitelisted methods).
- All API traffic over HTTPS; PII (phone) minimized; logs never store raw OTP (hash only).
