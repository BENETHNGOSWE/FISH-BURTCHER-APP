# MANASE BUTCHER Customer Mobile API — curl walkthrough

Base URL: `https://<your-erpnext-domain>`
All methods are under `/api/method/manase_butcher.fish_mobile.api.`.
Authenticated calls need header: `Authorization: Bearer <token>`.
Responses: `{"ok": true, "data": ...}` or `{"ok": false, "error": ..., "message": ...}`.

> Customers never receive ERPNext user accounts or Desk access. Only the methods below are
> callable with a customer token.

## 1. Request OTP

```bash
curl -X POST "$B/api/auth.request_otp" \
  -H "Content-Type: application/json" \
  -d '{"phone":"0712345678","device_id":"abc-123","platform":"Android"}'
# development gateway logs the OTP in the bench logs
```

## 2. Verify OTP → session token

```bash
curl -X POST "$B/api/auth.verify_otp" \
  -H "Content-Type: application/json" \
  -d '{"phone":"0712345678","otp":"123456","device_id":"abc-123",
       "fcm_token":"fcm-xyz","platform":"Android"}'
# -> data.session.token = save securely on device
TOKEN="..."
```

## 3. Nearby branches (Haversine, server computed)

```bash
curl -s "$B/api/branches.nearby?lat=-6.7470&lng=39.2778&radius_km=20" | jq
# [{"id":"BR-xxxxx","name":"Masaki","distance_km":1.2,"delivery_available":true,...}]
```

## 4. Branch catalog — availability is that branch warehouse ONLY

```bash
curl -s "$B/api/branches.products?id=BR-xxxxx" \
  -H "Authorization: Bearer $TOKEN" | jq
# items: [{item, name, price_per_kg, currency:"TZS", available_kg,
#          status:"in_stock|low_stock|out_of_stock"}]
```

## 5. Validate cart (server reprices + checks KG, no write)

```bash
curl -X POST "$B/api/orders.validate_cart" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"data":{
        "branch":"BR-xxxxx","order_type":"Pickup",
        "lines":[{"item":"Red Snapper - Cleaned","kg":5}]}}'
# -> {subtotal, delivery_fee, total, lines:[{price_per_kg,...}]}
```

## 6. Checkout (reserves KG; idempotent)

```bash
curl -X POST "$B/api/orders.create_order" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -H "X-Idempotency-Key: cart-uuid-001" \
  -d '{"data":{
        "branch":"BR-xxxxx","order_type":"Delivery",
        "lines":[{"item":"Red Snapper - Cleaned","kg":5}],
        "delivery_address":"ADDR-1","address_text":"Masaki, Dar es Salaam",
        "latitude":-6.748,"longitude":39.280,
        "payment":{"provider":"M-Pesa"}}}'
# 20 KG branch stock, orders 10 + 8 => next order for 5 is rejected INSUFFICIENT_STOCK
```

## 7. Track / history / cancel

```bash
curl "$B/api/orders.list_orders" -H "Authorization: Bearer $TOKEN"
curl "$B/api/orders.get_order?id=MO-2026-00001" -H "Authorization: Bearer $TOKEN"
curl -X POST "$B/api/orders.cancel_order" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"id":"MO-2026-00001","reason":"changed mind"}'   # only Pending/Confirmed
```

## 8. Profile / addresses / payments

```bash
curl "$B/api/customer.profile" -H "Authorization: Bearer $TOKEN"
curl -X POST "$B/api/customer.save_address" -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"label":"Home","address_line1":"Kawe","city":"Dar es Salaam",
       "latitude":-6.730,"longitude":39.260}'
curl "$B/api/customer.payments" -H "Authorization: Bearer $TOKEN"
```

## 9. Mobile money provider callback (server-to-server, HMAC)

```bash
SIGN=$(printf '{"provider":"M-Pesa","reference":"MP123","amount":65000,"order":"MO-2026-00001"}' \
  | openssl dgst -sha256 -hmac "$MB_WEBHOOK_SECRET" | sed 's/^.* //')
curl -X POST "$B/api/webhooks.mobile_payment_callback?provider=M-Pesa" \
  -H "X-MB-Signature: $SIGN" -H "Content-Type: application/json" \
  -d '{"provider":"M-Pesa","reference":"MP123","amount":65000,"order":"MO-2026-00001","status":"CONFIRMED"}'
# duplicate references are rejected (replay protection); Payment Entry is created.
```

## Flutter integration notes

- Bottom navigation: **Home | Shop | Cart | Orders | Profile**.
- Persist token with `flutter_secure_storage`; attach via Dio interceptor; call
  `auth.refresh` on 401; FCM token registered at verify-time and via `auth.register_push`.
- Catalog images are Frappe File URLs returned in `image`; render thumbnails with caching.
- All prices and availability are authoritative server-side; never compute totals client-side
  for payment — use `orders.validate_cart`/`create_order` responses.
