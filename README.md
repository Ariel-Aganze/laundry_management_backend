# Laundry Management & POS — Backend

Django 5.2 + Django REST Framework + PostgreSQL. JWT authentication, two roles (Admin, Cashier).

## 1. Setup

```bash
cd laundry_management_backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then edit .env (see below)
```

## 2. PostgreSQL connection

Open `psql` as the `postgres` superuser (PostgreSQL 18 on macOS: `/Library/PostgreSQL/18/bin/psql -U postgres`) and run:

```sql
CREATE USER laundry_user WITH PASSWORD 'choose-a-strong-password';
CREATE DATABASE laundry_db OWNER laundry_user ENCODING 'UTF8';
-- Needed only to run the test suite against PostgreSQL (it creates/drops test_laundry_db):
ALTER USER laundry_user CREATEDB;
```

Then set these in `.env`:

```env
DB_ENGINE=postgresql
DATABASE_NAME=laundry_db
DATABASE_USER=laundry_user
DATABASE_PASSWORD=choose-a-strong-password
DATABASE_HOST=localhost
DATABASE_PORT=5432
```

Generate a `SECRET_KEY`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

## 3. Initialise

```bash
python manage.py migrate
python manage.py createadmin --username admin --first-name "Owner"   # prompts for password
python manage.py seed_catalog          # optional: demo categories & prices from the SRS
python manage.py runserver             # http://localhost:8000
```

- API root: `http://localhost:8000/api/v1/`
- Interactive API docs (Swagger): `http://localhost:8000/api/v1/docs/`

## 4. Tests

```bash
python manage.py test tests                          # uses PostgreSQL from .env
DB_ENGINE=sqlite python manage.py test tests         # quick run without PostgreSQL
```

## Project layout

| App | Responsibility |
| --- | --- |
| `common` | Base models, daily sequences (order/receipt numbers), error format, permissions, phone/money/i18n helpers |
| `accounts` | Custom user (UUID, role, language), login by username **or** email, cashier management |
| `audit` | Append-only activity log |
| `business` | Business settings (singleton), WhatsApp templates (English + Kinyarwanda) |
| `customers` | Customers (phone stored with country code, e.g. `+250788123456`) |
| `catalog` | Service categories and items with Normal / Express prices |
| `orders` | Orders, items (price snapshots), status workflow, collection approval, cancellation |
| `payments` | Payments, partial payments, reversals (never deleted) |
| `receipts` | Frozen receipt snapshots, PDF for 58mm / 80mm thermal and A4 (EN / RW) |
| `messaging` | Click-to-WhatsApp links (`wa.me`) + log of messages *initiated* (not delivered) |
| `reports` | Dashboards (Admin & Cashier) and Admin analytics |

## Key business rules

- All totals, balances and payment statuses are calculated by the server, never trusted from the client.
- Prices are copied into each order item; changing the catalog never changes existing orders or receipts.
- Order references `LND-YYYYMMDD-XXXX` and receipt numbers `RCP-YYYYMMDD-XXXX` come from a locked database sequence.
- Payments cannot exceed the balance; corrections are Admin reversals that keep the original record.
- Cancelled orders (Admin only, reason required) keep their payments but are excluded from revenue.
- **Collecting clothes while a balance is owed requires Admin approval**: the cashier requests it
  (`POST /orders/{id}/request-collection/`) and the Admin approves or rejects it (`POST /orders/{id}/decide-collection/`),
  or the Admin approves directly when marking the order collected (`approve_balance: true`).
- Cashiers can see all orders. They can edit notes, the pickup date and item condition notes; changes to the customer,
  drop-off date or items are Admin only.

## Error format

```json
{ "detail": "Human readable message", "code": "payment_exceeds_balance", "balance": "2000.00" }
{ "detail": "...", "code": "validation_error", "errors": { "phone_number": [{ "message": "...", "code": "phone_missing_country_code" }] } }
```

The frontend translates by `code` (English / Kinyarwanda).

## Main endpoints (`/api/v1/`)

| Area | Endpoints |
| --- | --- |
| Auth | `auth/login/`, `auth/refresh/`, `auth/logout/`, `auth/me/` (GET/PATCH), `auth/change-password/` |
| Users (Admin) | `users/`, `users/cashiers/` CRUD, `…/{id}/activate/`, `…/{id}/deactivate/`, `…/{id}/reset-password/` |
| Customers | `customers/` (`?search=`), `customers/{id}/`, `customers/{id}/orders/`, `customers/{id}/payments/` |
| Catalog | `categories/`, `services/` (DELETE = deactivate), `catalog/` (active tree for New Order) |
| Orders | `orders/` (filters: `search, status, payment_status, service_type, created_by, drop_off_from/to, pickup_from/to, overdue, has_balance, collection_approval`), `orders/search/?q=`, `orders/{id}/` PATCH, `…/status/`, `…/cancel/`, `…/request-collection/`, `…/decide-collection/`, `…/payments/`, `…/receipt/`, `…/receipts/`, `…/whatsapp/` |
| Payments | `payments/` (GET/POST), `payments/{id}/`, `payments/{id}/reverse/` (Admin) |
| Receipts | `receipts/`, `receipts/{id}/`, `receipts/{id}/pdf/?paper=58mm\|80mm\|A4&lang=en\|rw&download=1` |
| Dashboard | `dashboard/summary/?period=…`, `dashboard/pickups/?days=`, `dashboard/overdue/` |
| Analytics (Admin) | `analytics/revenue/`, `analytics/services/`, `analytics/cashiers/`, `analytics/customers/`, `analytics/payments/` |
| Settings | `settings/` (GET all, PATCH Admin, multipart for logo), `settings/public/`, `settings/whatsapp-templates/` |
| Audit (Admin) | `audit-logs/` (`?user=&action=&entity_type=&date_from=&date_to=`) |

Periods: `today, yesterday, last_7_days, last_30_days, this_month, last_month, custom&start=YYYY-MM-DD&end=YYYY-MM-DD`.

## Backups

Run a daily `pg_dump` and copy the `media/` folder (business logo) to separate storage, for example:

```bash
pg_dump -U laundry_user -h localhost -Fc laundry_db > backups/laundry_$(date +%F).dump
# restore: pg_restore -U laundry_user -h localhost -d laundry_db --clean backups/laundry_YYYY-MM-DD.dump
```
