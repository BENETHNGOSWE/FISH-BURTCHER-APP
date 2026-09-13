# Part 6 — Mobile Application & API Specification

Tags: `[MOBILE]`, `[API]`, `[MANASE CUSTOM]`, `[ERPNext CONFIGURATION]`.

The customer app (**Flutter**) never talks to generic ERPNext REST. It calls a small, explicitly
whitelisted surface under `manase_butcher.fish_mobile.api.*`. Customers never have desk access.

---

## 1. Authentication flow (phone + OTP)

```
POST /request-otp {phone, device_id, fcm_token?, platform}
   ├─ normalize phone to E.164 (+255…), validate Tanzanian MSISDN
   ├─ rate limit: max R1 per phone / IP per window (settings; default 3/10 min, 10/hour)
   ├─ generate 6-digit OTP, store SHA-256 hash + expiry (settings, default 5 min) in OTP Log
   ├─ send via configured SMS gateway (dev: server log), or FCM-inapp for repeat devices
   └─ 200 {status: sent} (never reveal whether the phone existed before)

POST /verify-otp {phone, otp, device_id, fcm_token?}
   ├─ rate limit attempts (max 5; mark Expired after)
   ├─ on success: find/create Customer (territory Tanzania, customer_group Walk-in/Retail),
   │  mark phone verified, upsert Mobile Device, create Mobile Session:
   │    opaque token = secrets.token_urlsafe(48); store sha256 hash; expiry 30d sliding
   └─ 200 {token, customer:{name, customer_name, phone, preferred_branch}, expires_at}

POST /logout                 (Authorization: Bearer token) → revoke session/device token
POST /refresh                → rotate token (sliding expiry); old token revoked
```

Security: OTPs stored hashed only; constant-time hash compare; generic error messages;
device binding optional (setting); admin can revoke sessions; all methods validate
`get_current_customer()` and rate-limit per session. Email/username/password never required
(email is an optional profile field).

Server-side authorization rule: every authenticated endpoint loads the customer from the token
and **only ever queries records owned by that customer**; branch/stock data is read-only catalog
data scoped by the selected branch.

---

## 2. API Specification (base path `/api/method/manase_butcher.fish_mobile.api`)

All responses are JSON `{ "ok": true, "data": ... }` or `{ "ok": false, "error": code, "message": … }`.
Auth header: `Authorization: Bearer <token>`.

### Auth — `auth.py` `[API]`
| Method | Endpoint | Guest | Body / params |
|---|---|---|---|
| POST | `auth.request_otp` | ✓ | phone, device_id, platform, fcm_token |
| POST | `auth.verify_otp` | ✓ | phone, otp, device_id, fcm_token |
| POST | `auth.logout` | – | – |
| POST | `auth.refresh` | – | – |

### Branches — `branches.py`
| Method | Endpoint | Description |
|---|---|---|
| GET | `branches.list_branches` | active branches: id, name, code, phone, hours, location |
| GET | `branches.nearby` | params `lat,lng,radius_km?` → branches sorted by Haversine distance, delivery radius flag |
| GET | `branches.get_branch` | id → branch detail incl. today's availability summary |
| GET | `branches.products` | id, optional category/search → sellable items with branch stock & price |
| POST | `branches.set_preferred` | {branch} → save on Customer |

Nearby logic: pure server-side Haversine from Branch.latitude/longitude (source of truth), radius
filter by `delivery_radius_km` for delivery eligibility; client may also cache locations but
availability/pricing always re-computed server-side.

### Products — `products.py`
| Method | Endpoint | Description |
|---|---|---|
| GET | `products.list_products` | branch, search?, category?, freshness?, page/size → only `mb_sellable=1` |
| GET | `products.get_product` | id, branch → full catalog card (image, species, prep, grade, price/kg) |
| GET | `products.availability` | branch, item(s) → `{available_kg, reserved_kg, in_transit_kg?, status}` |

**Availability (critical, spec §24):** quantity = projected stock in the **selected branch
warehouse only** = `Bin.actual_qty − reserved_qty (SRE) − custom_reserved_kg`; central warehouse
stock is never shown as purchasable. `available_kg ≤ 0` → `Out of Stock` (catalog returns
status but app hides/disables Add). Prices resolved with branch+type priority; the payload
includes only the customer-applicable price (Retail default).

### Cart & Orders — `orders.py`
| Method | Endpoint | Description |
|---|---|---|
| POST | `orders.validate_cart` | {branch, lines:[{item, kg}]} → reprices, rechecks stock; returns totals/delivery |
| POST | `orders.create_order` | {branch, type: Pickup/Delivery, lines, address?, scheduled?, delivery?, payment:{provider?}} |
| GET | `orders.list_orders` | paginated order history (own only) |
| GET | `orders.get_order` | id (ownership enforced) → full order + statuses + payment state |
| POST | `orders.cancel_order` | id, reason (allowed only Pending/Confirmed within SLA) → releases reservation |
| POST | `orders.add_payment` | id, provider, reference (teller) or STK result |
| GET | `orders.order_status` | id → status (app polls; FCM pushes too) |

`create_order` server flow (atomic):
1. auth + customer checks (credit hold if applicable — mobile is prepaid by default),
2. branch active & within delivery radius/order window,
3. reprice every line server-side (never trust client prices),
4. **availability check with row locking**: `available_kg` for each line; reject with
   `INSUFFICIENT_STOCK` listing available KG (Rule 4),
5. create **Sales Order** (delivery or pickup, branch warehouse, customer) then
   **Stock Reservation Entry(ies)** reserving KG at branch warehouse
   (`from_voucher_type="Sales Order"`); fallback custom Stock Reservation + Bin custom reserved KG,
6. create **Customer Order** linked to SO (status Pending, expiry timestamp),
7. notify branch (desk Notification + optional FCM/SMS to branch manager),
8. return order with payment instructions.
Scheduled job auto-rejects/releases orders not confirmed by branch within
`order_validity_minutes` (default 20).

### Customer — `customer.py`
| Method | Endpoint | Description |
|---|---|---|
| GET | `customer.profile` | name, phone, verified, preferred branch, optional email |
| POST | `customer.update_profile` | name, email |
| GET | `customer.addresses` | standard Addresses linked to customer |
| POST | `customer.save_address` | label, recipient, phone, lat/lng, area, details (creates Address) |
| GET | `customer.orders` | (alias of orders list with filters) |
| GET | `customer.payments` | own payments/invoices/receipts |
| GET | `customer.balance` | outstanding/credit info (retail customers: usually 0) |

### Payments callbacks — `webhooks.py` (guest, provider-authenticated)
| Method | Endpoint | Description |
|---|---|---|
| POST | `webhooks.mobile_payment_callback` | provider-key/HMAC verified; matches reference/amount → Payment Entry + order update |
| POST | `webhooks.delivery_event` | (optional delivery partner token) status updates |

### Other platform behaviour
- `[API]` Inputs validated; unknown fields rejected; max cart lines/weights capped in settings.
- HTTP 429 with retry-after on rate limits; 401 on bad/expired token; 403 on foreign resources.
- ETags/`updated_at` for catalog polling; images served as Frappe files (thumbnails).

---

## 3. Customer order workflow & status mapping `[MOBILE]`

```
Pickup :  Received → Confirmed → Preparing → Ready for Pickup → Collected
Delivery: Received → Confirmed → Preparing → Ready → Out for Delivery → Delivered
Terminal: Completed (invoiced, paid) · Cancelled (reservation released) · Rejected
```
Branch actions (Desk/Customer Order actions or POS): Accept, Reject, Start Preparing,
Ready, Dispatch (delivery), Mark Delivered/Collected, Complete (invoice+payment capture),
Cancel (reason). Each transition: permission check, FCM push + SMS fallback, Notification Log,
and ledger action on reserve/release/invoice.

---

## 4. Mobile screens / navigation `[MOBILE]`

Bottom nav: **Home | Shop | Cart | Orders | Profile**

- **Home**: preferred/nearby branch selector (location permission → nearest list with KM and
  opening state; manual selection), search, categories, featured/available fish, order status card.
- **Shop/Fish**: category & species/filters (fresh/frozen, cut), fish image cards with
  branch-available KG and TZS/KG; out-of-stock disabled; product detail (origin/species, grade).
- **Cart**: lines with KG stepper (respects available), price × KG, subtotal, delivery fee, total,
  pickup/delivery toggle, address/slot, payment provider choice, place order.
- **Orders**: live status timeline, history, reorder, cancel (within SLA), receipt view/download.
- **Profile**: name/phone (verified badge)/optional email, addresses (map pick), preferred branch,
  payments/balance, help, logout.
- States for no-location, closed branch, zero stock, network failure, payment pending.

Tech: Flutter 3, Dio + interceptors (token/refresh), Riverpod, secure storage for token,
geolocator + map/link, flutter_local_notifications + FCM, intl TZS, image caching; CI builds for
Android/iOS. The Flutter codebase is a separate build target; this repository ships the complete
API it consumes, plus API request examples in `mobile_api_examples/`.

---

## 5. Branch-specific product availability logic (sequence) `[API]`

```
App: location/branch chosen
  → GET branches.products?branch=MASAKI
Server:
  Branch → warehouse (custom mb_branch)
  JOIN Bin (actual_qty, reserved_qty, custom reserved) on Item default/warehouse
  WHERE item.mb_sellable = 1 AND Item.disabled = 0 AND (has website item? publish flag)
  available = actual − reserved − custom_reserved
  price = resolve_price(item, branch, price_type=Retail, customer)
  return only positive-or-published rows with status in_stock|low_stock|out_of_stock
Order:
  create_order repeats the same computation under lock before reserving (authoritative)
```

---

## 6. Stock reservation logic `[MANASE CUSTOM]` `[ERPNext STANDARD]`

```
available_kg(item, wh) = projected_qty           -- Bin.actual_qty − Bin.reserved_qty (SRE)
                                          − Bin.custom_mb_custom_reserved_kg (fallback)
On checkout:
  for each line (ordered by item):
    SELECT … FROM tabBin WHERE item_code=%s AND warehouse=%s FOR UPDATE
    if available_kg < line.kg: raise INSUFFICIENT_STOCK (available=…)
  create Sales Order → create SRE qty=line.kg warehouse=branch warehouse
  on SRE failure: insert Stock Reservation rows + increment Bin.custom reserved (fallback)
On branch completion:
  Sales Invoice from SO consumes reservation (standard pick/deliver), stock −KG
On cancel/timeout/reject:
  cancel SRE (or decrement custom reserved) → KG immediately available
```
This prevents overselling across two concurrent 10+8 KG orders against 20 KG stock (spec §29).

---

## 7. Notifications `[MANASE CUSTOM]` `[ERPNext CONFIGURATION]`

Customer push (order lifecycle, payment receipts): FCM v1 using service account credentials stored
in Settings (`fcm.py` mints OAuth2 JWT with google-auth if installed; messages logged in
Notification Log; SMS fallback via gateway). Desk/business notifications use standard
**Notification** documents auto-created in setup:

| Event | Recipient | Channel |
|---|---|---|
| New mobile order | Branch Manager, Sales Staff (branch) | Desk + FCM/SMS manager |
| Order accepted/ready/out-for-delivery/delivered/completed | Customer | FCM + SMS fallback |
| Low stock (reorder level) | Branch/Inventory manager | Desk/email |
| Stock variance over threshold | Inventory Manager, GM | Desk + email |
| High waste %/KG | GM, Inventory Manager | Desk |
| Debt due / overdue | Accountant (and customer SMS) | Desk + SMS/WhatsApp |
| Supplier payment due | Accountant, Procurement | Desk/email |
| Transfer dispatched / discrepancy | Target branch | Desk + SMS |

Phase 5: WhatsApp templates via provider; loyalty/promotions via Pricing Rule/coupons + FCM.

---

## 8. Rate limiting & abuse controls `[API]`

Redis counters with sliding windows: OTP request (per phone & IP), verify attempts, order create,
cart validate, profile updates; deny-list after repeated failures; minimum/maximum KG and order
value bounds; reference-number uniqueness; idempotency key on create_order/payment to avoid double
charges; callback replay protection (seen-provider-reference set + timestamp window).
