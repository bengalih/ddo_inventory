# DDO Inventory — Django rewrite

A full rewrite of the Flask version onto Django, replicating all existing
functionality. No data migration from the old app — this starts fresh.

Built against **Django 5.2 (LTS)**, which supports Python 3.10–3.13 —
run `python --version` if you're unsure what you have. (Django's very
latest release, 6.1, requires Python 3.12+, so 5.2 is the safer/broader
pin, and being an LTS release it gets security patches for longer too.)

## Setup

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

python manage.py migrate          # creates db.sqlite3 and seeds the
                                   # original item types / attributes

python manage.py createsuperuser  # creates your admin account - this
                                   # replaces the old "first user to
                                   # register becomes admin" behavior
```

## Running locally

```bash
DDO_DEBUG=true python manage.py runserver
```

**Important:** unlike Flask, Django only auto-serves static files (CSS)
through `runserver` when `DEBUG=True`. Set `DDO_DEBUG=true` for local
development. For any real deployment, leave `DDO_DEBUG` unset (defaults to
off) and serve static files properly instead — either run
`python manage.py collectstatic` and point a real web server (nginx,
etc.) at the output, or add something like `whitenoise` if you want
Django/Gunicorn to serve them directly.

The app runs at `http://127.0.0.1:8000/`.

## What changed from the Flask version (and from the first Django pass)

- **Characters are optional.** Items don't need one. Instead of a
  mandatory gate, new users see a one-time "you can create a character
  now, or skip and assign items later" screen right after registering or
  logging in for the first time — it never appears again after that
  (tracked per-user via `Profile.has_seen_character_intro`).
- **Character names are unique per server, globally** — not just within
  your own account. Matches how DDO itself works: two different users
  can each have a character named "Pursuit," but not both on the same
  server.
- **Item names are optional.** They were never a database key (Django
  always uses a separate hidden numeric id for that) — just a label. The
  Add Item form has an "auto-generate name from type and attributes"
  checkbox (e.g. "Belt (Seeker +6, Deadly +8)") that remembers your last
  choice for next time via `Profile.auto_generate_item_names`.

- **Auth**: Django's built-in `django.contrib.auth` replaces the hand-rolled
  users table, password hashing, and session code.
- **Admin bootstrap**: no more "first registrant automatically becomes
  admin." Admins are created via `python manage.py createsuperuser`
  (Django's standard workflow) and gated by the built-in `is_staff` flag.
- **Attributes & item types**: managed through Django's real built-in
  admin site at `/admin/` (staff-only) instead of a hand-built custom
  page. Deletion is blocked automatically at the database-relationship
  level (`on_delete=PROTECT`) if an attribute or item type is still in
  use by an item — same rule as before, enforced structurally instead of
  by a hand-written check.
- **Migrations**: real Django migrations (`inventory/migrations/`)
  instead of hand-written `PRAGMA table_info()` / `ALTER TABLE` checks.
  This is the class of bug (the `is_default` column migration gap) that
  bit the Flask version — Django's migration system tracks schema
  changes structurally instead.
- **CSRF**: Django's built-in CSRF protection (`{% csrf_token %}` +
  middleware) instead of a hand-rolled token system.
- **Item attribute values**: stored as a real `IntegerField` instead of
  text, so numeric search comparisons ("Seeker ≥ 5") are correct by
  construction rather than needing an explicit `CAST` at query time.
- **Search's LIKE-escaping**: Django's `__icontains` lookup escapes `%`
  and `_` automatically, so the manual escaping helper from the Flask
  version isn't needed here.

Everything else — the character gate (zero characters → forced to
`/characters/` before doing anything else), first-character auto-default
and item auto-assignment, bulk reassignment, minimum level 1–36 dropdown,
server/character-name search filters, multi-attribute AND search
filtering, and character deletion with reassign-or-unassign — works
identically to the Flask version. All of it was tested end-to-end against
a running instance of this app before delivery.
