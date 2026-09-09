# UENR Student Payment Portal (Django)

A simulated student dues payment portal for the University of Energy and Natural Resources.

## Run it on your computer (Windows)

```powershell
cd uenr_portal
py -m pip install -r requirements.txt
py manage.py migrate
py manage.py seed          # optional demo data
py manage.py runserver
```

Then open http://127.0.0.1:8000/

If `python` is not recognised, use `py` as shown above.

### Demo logins (after `seed`)

| Role    | Username    | Password      |
| ------- | ----------- | ------------- |
| Student | 202312345   | password123   |
| Admin   | admin       | admin123      |

Students can also create their own account from **Get Started → Create one**.

## What students can do

- Sign up with name, index number, email, phone, **programme** (Computer Engineering
  or Electrical and Electronics Engineering) and **level** (100–400) — both dropdowns.
- See only the dues the admin has published for their level/programme.
  A brand-new account sees an empty list until dues are published.
- Pay with MTN MoMo, Vodafone Cash, card or bank transfer (simulated), entering
  the phone number used for the transaction.
- View and print an official receipt showing name, index number, **level**,
  programme, phone, transaction reference, receipt number, date and time.
- Reset a forgotten password by email.

## Receipt security

Each receipt carries a **security code** — an HMAC of the receipt number,
transaction reference, index number, amount and timestamp, signed with the
project `SECRET_KEY`. A QR code on the receipt links to a public verification
page (`/verify/<receipt-no>/`) that confirms the receipt against university
records. A faked or edited receipt fails verification. The receipt has the
university crest as a watermark and fits on **one A4 page** when printed.

## Admin console — http://127.0.0.1:8000/manage/

- **Dashboard** — total collected, expected, outstanding, collected today,
  and collections broken down by level and by programme, with totals.
- **Students** — filter by level, programme or search; upload students from
  Excel/CSV (a template is downloadable); download all filtered or only the
  selected students as Excel; remove a student.
- **Dues** — publish a due to a whole level at once, optionally limited to one
  programme. Re-apply to catch new students, or delete it everywhere.
- **Payments** — name, index number, level, programme, transaction reference,
  receipt number, phone, method, amount, date and time; filter by level,
  programme, method or search; export to Excel; open any receipt.

Uploaded students get the default password `uenr@1234` and can change it
through "Forgot password".

## Password reset email

By default reset links are printed to the terminal (no setup needed).
To send real email, set these environment variables before running the server:

```
EMAIL_HOST_USER=your@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=your@gmail.com
```

## Note

Payments are **simulated** — no money moves and no payment provider is called.
