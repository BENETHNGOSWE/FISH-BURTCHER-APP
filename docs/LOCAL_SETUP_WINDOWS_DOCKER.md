# Local testing on Windows with Docker (step by step)

This guide runs ERPNext **v16** + the **MANASE BUTCHER** app on your laptop using the
official [frappe_docker](https://github.com/frappe/frappe_docker) images and Docker Desktop.
Everything runs in Linux containers — you do **not** need Python, Node, or MariaDB on Windows.

> The custom app is installed *inside the running container* (fastest for testing).
> A production-style custom image is described at the end.

---

## 0. Prerequisites

1. **Docker Desktop for Windows** installed, running, using the **WSL 2** backend
   (Docker Desktop → Settings → General → "Use WSL 2 based engine"). Give it
   **at least 6–8 GB RAM** (Settings → Resources).
2. **Git for Windows** (provides Git Bash) — PowerShell also works.
3. ~5 GB free disk space.
4. Know the latest v16 image tag from
   <https://hub.docker.com/r/frappe/erpnext/tags?name=v16> (it looks like `v16.x.x`).
   All commands below assume you put that tag in the `.env` file.

Commands starting with `$` run in **Git Bash / PowerShell** on Windows.
Commands starting with `bench ...` run **inside the container**.

---

## 1. Get frappe_docker

```bash
cd ~/projects          # or any folder you like
git clone https://github.com/frappe/frappe_docker.git
cd frappe_docker
cp example.env .env
```

Open `.env` in an editor and set (leave the other lines as they are):

```env
ERPNEXT_VERSION=v16.x.x        # <-- newest tag starting with v16
MYSQL_ROOT_PASSWORD=123       # local testing only
DB_PASSWORD=123
```

---

## 2. Start the ERPNext stack (MariaDB + Redis, no proxy)

From the `frappe_docker` folder:

```bash
docker compose -f compose.yaml \
  -f overrides/compose.mariadb.yaml \
  -f overrides/compose.redis.yaml \
  -f overrides/compose.noproxy.yaml \
  up -d
```

Watch startup and wait until the `backend` and `db` containers are healthy:

```bash
docker compose ps
docker compose logs -f backend     # Ctrl+C to stop watching once it is idle
```

---

## 3. Create a site

```bash
docker compose exec backend bench new-site \
  --mariadb-user-host-login-scope='%' \
  --admin-password=changeit \
  --db-root-username=root \
  --db-root-password=123 \
  --set-default \
  mysite.localhost
```

Install ERPNext on the site:

```bash
docker compose exec backend bench --site mysite.localhost install-app erpnext
```

---

## 4. Run the ERPNext setup wizard (creates your Company)

1. Open <http://localhost:8080> (the `noproxy` override publishes port **8080**).
   - If the browser cannot resolve `mysite.localhost`, open <http://localhost:8080>
     directly — `--set-default` makes it the default site.
   - Optional: add the line `127.0.0.1 mysite.localhost` to
     `C:\Windows\System32\drivers\etc\hosts` (open Notepad **as Administrator**).
2. Log in as **Administrator** / **changeit**.
3. Complete the setup wizard with:
   - Company: **MANASE BUTCHER LTD**
   - Country: **Tanzania**, Currency: **TZS**
   - Industry: any (e.g. Distribution/Retail)

> Why do the wizard before installing our app? The app's installer auto-creates warehouses,
> accounts, branches and price lists **for the default Company**, which only exists after
> the wizard.

---

## 5. Install the MANASE BUTCHER app

```bash
# 1) download + pip-install the app into the bench (inside the backend container)
docker compose exec backend bench get-app --skip-assets --branch main \
  https://github.com/BENETHNGOSWE/FISH-BURTCHER-APP.git

# 2) install it on the site (runs after_install: roles, warehouses, branches, accounts...)
docker compose exec backend bench --site mysite.localhost install-app manase_butcher

# 3) apply any custom-field/schema changes
docker compose exec backend bench --site mysite.localhost migrate

# 4) build the app's JS/CSS assets (POS page, desk bundle)
docker compose exec backend bench build --app manase_butcher
```

Hard-refresh the browser (Ctrl+F5). You will see a **MANASE BUTCHER** category/workspace
in the workspace switcher.

> If the GitHub repo is **private**, either make it public for testing, or use a token:
> `bench get-app --skip-assets --branch main https://<USERNAME>:<TOKEN>@github.com/BENETHNGOSWE/FISH-BURTCHER-APP.git`
> (local machine only — the token ends up in the container's command history).

---

## 6. Verify the installation

- Search **Branches** → Masaki, Mikocheni, Sinza, Kariakoo exist; open one and confirm it has
  a linked **Warehouse** and **Cost Center** (auto-created).
- Search **Manase Butcher Settings** → central warehouses, accounts, payment methods filled in.
- Search **Role** → the 12 MANASE roles exist (Business Owner, Branch Manager, Cashier, …).
- Open the POS page: <http://localhost:8080/app/fish-pos>
- Search the report **Where Did The KG Go?**.

### Minimal end-to-end test (mirrors spec §42)

1. Create fish **Items** with stock UOM **Kg**, tick *Is Fish Item*
   (e.g. `Red Snapper - Whole` in Fresh Fish, `Red Snapper - Cleaned` in Processed Fish
   with *Sellable* ticked and a Retail price).
2. **Fish Receiving**: receive 500 KG whole @ 8,000 + transport/handling → Submit
   (creates Purchase Receipt, +500 KG Central Raw).
3. **Fish Processing**: input 500 whole → output 470 cleaned + 30 waste (set status
   Approved) → Submit (Manufacture Stock Entry; Yield 94%).
4. **Fish Stock Transfer**: 100 KG to Masaki → Approve → Dispatch → Receive 98 KG with
   a variance reason.
5. **Fish POS** → sell KG from Masaki, take Cash/M-Pesa → Sales Invoice + Payment Entry.
6. **Branch Stock Reconciliation** → *Fetch Expected Stock*, count, approve.
7. **Daily Branch Closing** → *Fetch Data*, count cash, submit.

### Trying the mobile API

OTP request (no auth):

```bash
curl -X POST "http://localhost:8080/api/method/manase_butcher.fish_mobile.api.auth.request_otp" \
  -H "Content-Type: application/json" \
  -d "{\"phone\":\"0712000000\",\"device_id\":\"test-1\"}"
```

With the **Log (development)** SMS gateway the OTP is printed in the backend logs:

```bash
docker compose logs backend | grep "verification code"
```

Then call `auth.verify_otp` and use the returned bearer token (full walkthrough in
[`mobile_api_examples/README.md`](../mobile_api_examples/README.md)).

---

## 7. Updating the app after you push code changes

```bash
docker compose exec backend bench get-app --branch main \
  https://github.com/BENETHNGOSWE/FISH-BURTCHER-APP.git
docker compose exec backend bench --site mysite.localhost migrate
docker compose exec backend bench build --app manase_butcher
docker compose restart frontend websocket backend
```

(Use this during development; never edit code inside the container for anything you want to keep.)

---

## 8. Stop / start / reset

```bash
# stop but keep database/site data
docker compose -f compose.yaml -f overrides/compose.mariadb.yaml \
  -f overrides/compose.redis.yaml -f overrides/compose.noproxy.yaml stop

# start again
docker compose -f compose.yaml -f overrides/compose.mariadb.yaml \
  -f overrides/compose.redis.yaml -f overrides/compose.noproxy.yaml start

# completely wipe the test environment (deletes volumes/site!)
docker compose -f compose.yaml -f overrides/compose.mariadb.yaml \
  -f overrides/compose.redis.yaml -f overrides/compose.noproxy.yaml down -v
```

> Note: apps installed with `bench get-app` live in the container image layer. They survive
> `stop/start` but not `down -v` + recreation. The custom image below removes that caveat.

---

## 9. (Optional, recommended) Build a custom image — production-parity

This bakes MANASE BUTCHER into the image so it survives recreation and matches production.

Create `frappe_docker/build/custom/apps.json` (there is an `apps.example.json` to copy):

```json
[
  {
    "url": "https://github.com/frappe/erpnext.git",
    "branch": "version-16"
  },
  {
    "url": "https://github.com/BENETHNGOSWE/FISH-BURTCHER-APP.git",
    "branch": "main"
  }
]
```

Build the image (use the same v16 tag as in `.env`):

```bash
docker build \
  --build-arg ERPNEXT_VERSION=v16.x.x \
  -t manase-erpnext:v16 \
  -f build/custom/Dockerfile build/custom
```

Create an override file `overrides/compose.custom.yaml` pointing every app service at the image:

```yaml
services:
  backend:
    image: manase-erpnext:v16
  configurator:
    image: manase-erpnext:v16
  websocket:
    image: manase-erpnext:v16
  queue-default:
    image: manase-erpnext:v16
  queue-short:
    image: manase-erpnext:v16
  queue-long:
    image: manase-erpnext:v16
  scheduler:
    image: manase-erpnext:v16
```

Bring it up with that extra override (and skip step 5's `get-app`):

```bash
docker compose -f compose.yaml -f overrides/compose.mariadb.yaml \
  -f overrides/compose.redis.yaml -f overrides/compose.noproxy.yaml \
  -f overrides/compose.custom.yaml up -d
```

Then create the site and install **erpnext** + **manase_butcher** as in steps 3–5
(no `bench get-app` needed — it is already in the image).

---

## 10. Troubleshooting

| Symptom | Fix |
|---|---|
| Port 8080 already in use | Edit `overrides/compose.noproxy.yaml` and change `8080:80` to e.g. `8090:80`, or stop the other container. |
| `get-app` fails on build/pip | Confirm the tag is a real ERPNext **v16** image and the container has internet; re-run the same command. |
| Branches/warehouses missing after install | The setup wizard (Company) wasn't completed first. Complete it, then run `bench --site mysite.localhost migrate` — after-migrate provisions the structure. |
| POS page looks unstyled / 404 on JS | Run `bench build --app manase_butcher` and hard-refresh (Ctrl+F5). |
| Assets not refreshing | `docker compose restart frontend websocket`, then Ctrl+F5. |
| Want a clean database | `bench --site mysite.localhost reinstall --admin-password=changeit` (ERPNext) then install apps again, or `down -v` and restart from step 2. |
| Where are logs / OTP codes? | `docker compose logs -f backend` (OTP codes appear here with the Log SMS gateway). |
| Database connection errors at `new-site` | Wait until `docker compose ps` shows `db` healthy; then retry. |
