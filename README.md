# MANASE BUTCHER — Custom ERPNext v16 Fish Business Management System

`manase_butcher` is a native Frappe/ERPNext **v16** application for a weight-based,
multi-branch fish supplier, butcher and retailer (Tanzania).

**Objective:** track every fish **KG** from supplier → receiving → processing → waste →
central warehouse → branch → sale/mobile order → final reconciliation, with full visibility
of money, stock, branches, customers and profitability.

> 📐 Read the full technical blueprint first: **[`docs/`](docs/)** (10 documents, all 35
> blueprint sections, every feature tagged `[ERPNext STANDARD]`, `[ERPNext CONFIGURATION]`,
> `[MANASE CUSTOM]`, `[MOBILE]` or `[API]`).

---

## What it does

- **KG is a first-class unit** — fish stock/sell in **Kg**; a flagship *Where Did The KG Go?*
  report reconstructs every movement from the Stock Ledger and proves it reconciles.
- **Receiving with landed cost** — weigh (gross/tare/net), grade, transport/handling/ice,
  creates a standard **Purchase Receipt** with valuation taxes + **Batch**.
- **Processing / butchering** — whole fish → cleaned/fillet/cuts + waste via **Manufacture
  Stock Entry**; enforces `input KG = sellable KG + waste KG`; yield %/waste % per supplier/
  processor/batch.
- **Waste is a real stock transaction** — Material Issue, reason mandatory, threshold approval.
- **Two-leg branch transfers** — source → in-transit → branch with **sent KG, received KG,
  variance KG (reason mandatory)**; missing KG becomes documented waste.
- **Branch stock reconciliation** — system-derived expected KG vs physical count → standard
  **Stock Reconciliation** on approval.
- **Fish POS desk page** — branch-scoped KG selling, retail/wholesale/restaurant prices, split
  tender (Cash, M-Pesa, Tigo Pesa, Airtel Money, HaloPesa, Bank, Card, Credit) → Sales Invoice
  + Payment Entries; credit uses the standard credit-limit engine.
- **Mobile ordering API** — phone+OTP login, nearby branches (Haversine), **branch-warehouse
  availability only**, KG cart, atomic **Stock Reservation** (oversell impossible), pickup/
  delivery status state machine, payment callbacks.
- **Expenses, daily branch closing** (expected vs actual per tender, cash over/short JE),
  **branch performance & profitability** built from GL/SLE.
- **Strict RBAC + branch isolation**, immutable **Audit Log**, price change audit, FCM/SMS.

ERPNext stays the only system of record — the custom DocTypes are fish-specific front
documents that create and link standard Purchase Receipt, Stock Entry, Sales Order,
Stock Reservation Entry, Sales Invoice, Payment Entry, Journal Entry and Stock Reconciliation.

---

## Repository layout

```
manase_butcher/
├── hooks.py                    # events, scheduled jobs, branch permission hooks, fixtures
├── branch_utils.py            # branches, warehouses, RBAC query conditions / has_permission
├── stock_utils.py             # availability, reservations, Stock Entry builder, KG ledger queries
├── accounting_utils.py        # Payment Entry / Journal Entry helpers
├── otp.py / mobile_auth.py    # OTP, hashed bearer sessions, SMS gateways
├── fcm.py / notifications.py  # Firebase push + SMS fallback, desk alerts
├── audit.py                   # immutable audit trail writer
├── setup/                     # after_install / after_migrate: roles, UOMs, warehouses,
│                              #   accounts, modes of payment, price lists, branches, custom fields
├── manase_butcher/            # module: settings, Branch, Fish Species, OTP/Session/Device,
│                              #   Audit Log, Price Change Log, Notification Log
├── fish_inventory/            # module: Receiving, Processing, Waste, Transfer,
│                              #   Reconciliation, Fish Batch, Stock Reservation
├── fish_sales/                # module: Customer Order, Fish Expense, Daily Branch Closing,
│                              #   POS server API, Sales Invoice hooks
├── fish_mobile/api/           # whitelisted JSON API: auth, branches, products, orders,
│                              #   customer, webhooks
├── report/                    # 10 script reports
├── workspace/                 # 7 native workspaces (app launcher categories)
├── page/fish_pos/             # POS desk page
├── public/js|css              # desk client code
└── tests/                     # FrappeTestCase suite (incl. §42 end-to-end scenario)
docs/                          # technical blueprint (Parts 0-9)
mobile_api_examples/           # curl walkthrough of the customer API
```

---

## Installation (bench)

Prerequisites: ERPNext v16 bench (Frappe v16, MariaDB 10.6+, Redis).

```bash
bench get-app https://github.com/BENETHNGOSWE/FISH-BURTCHER-APP.git
bench --site <site> install-app manase_butcher
bench --site <site> migrate
```

`after_install` provisions, idempotently, for the default company:

- roles (Business Owner, General Manager, Accountant, Inventory Manager, Procurement Officer,
  Branch Manager, Sales Staff, Cashier, Processing Staff, Warehouse Staff, Delivery Staff, Customer);
- UOM **Kg**, item groups (Fresh/Frozen/Processed/Fish Waste…), warehouse types;
- central warehouse tree (Raw, Processed, Processing Floor, Waste, In-Transit);
- fish expense/stock-adjustment/cash-over-short/delivery accounts;
- mobile-money wallet accounts and Modes of Payment;
- Wholesale/Restaurant/Hotel price lists;
- demo branches **Masaki, Mikocheni, Sinza, Kariakoo** (each auto-creates its Warehouse +
  Cost Center — create more in **Branches**).

Then configure **MANASE BUTCHER → Fish Settings → Manase Butcher Settings**
(accounts, approval thresholds, OTP/SMS gateway, FCM service account).

### Quick master-data setup

1. Create fish items per species×preparation (e.g. *Red Snapper - Whole/Cleaned/Fillet*),
   stock UOM **Kg**, tick **Is Fish Item**, set prices (Retail/Wholesale/…) with optional branch.
2. Set Item Reorder (min/max) per branch warehouse for low-stock alerts.
3. Assign a user as branch **Manager** and set User Permissions on Branch/Warehouse/Cost Center
   (auto-created when the manager is set on the Branch record).
4. Run the business: Receiving → Processing → Transfer → POS / Mobile Orders → Closing.

### Tests

```bash
bench --site <test-site> run-tests --app manase_butcher
```

The suite executes the blueprint's 25-step scenario (500 KG → 470 sellable + 30 waste →
transfers with variance → reserved mobile order → oversell rejection → ledger reconciliation).

---

## Customer mobile API (summary)

Base: `/api/method/manase_butcher.fish_mobile.api.*` — guest only for `auth.*` and signed
webhooks; everything else needs `Authorization: Bearer <token>`.

```
POST auth.request_otp {phone}            POST auth.verify_otp {phone, otp, device_id}
GET  branches.list_branches              GET  branches.nearby?lat&lng&radius_km
GET  branches.products?id=BR..           GET  products.list_products?branch=
POST orders.validate_cart                POST orders.create_order           (X-Idempotency-Key)
GET  orders.list_orders / get_order      POST orders.cancel_order
GET  customer.profile / payments         POST customer.save_address
POST webhooks.mobile_payment_callback    (HMAC signature header)
```
See [`mobile_api_examples/`](mobile_api_examples/) for a full curl walkthrough and the
Flutter data contract. The Flutter app itself is a separate build target consuming this API;
customers never receive Desk access or generic REST credentials.

## Security highlights

- OTPs stored as salted hashes; opaque session tokens stored hashed; sliding expiry + revoke.
- Redis rate limits on OTP and checkout; idempotent order/payment calls; HMAC-signed provider
  callbacks with replay protection; server-side pricing and authorisation on every mutation.
- Branch isolation via User Permissions + `permission_query_conditions`/`has_permission` hooks
  + controller checks; mobile endpoints can only ever read the token customer's own records.
- Immutable Audit Log for stock/KG changes, waste, prices, cancellations, payments, expenses,
  transfer variances and reconciliation approvals.

## License

MIT — see [LICENSE](LICENSE).
