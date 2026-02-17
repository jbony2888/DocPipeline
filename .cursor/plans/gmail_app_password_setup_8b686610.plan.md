---
name: Gmail App Password Setup
overview: How to create a Gmail/Google Workspace app password and configure the IFI Essay tool to send job-completion emails via SMTP.
todos: []
isProject: false
---

# Gmail / GSuite app password setup for IFI Essay tool

## 1. Create an app password in Google (Gmail or Google Workspace)

You must use an **app password**, not your normal account password. Google requires 2-Step Verification before app passwords are available.

### If you use **personal Gmail** (@gmail.com)

1. Go to [Google Account](https://myaccount.google.com/) and sign in.
2. **Security** → **2-Step Verification**. Turn it on if it is off (required for app passwords).
3. **Security** → **App passwords** (or go to [App passwords](https://myaccount.google.com/apppasswords)).
  - If you don’t see “App passwords,” 2-Step Verification must be on and you may need to use a personal Google account (not a Workspace account with strict admin policies).
4. Choose app: **Mail**; device: **Other** → name it (e.g. “IFI Essay tool”).
5. Click **Generate**. Copy the **16-character password** (spaces can be removed).

### If you use **Google Workspace (GSuite)** (@yourdomain.com)

1. Your admin must allow app passwords:
  - **Admin console** → **Security** → **Authentication** → **Less secure apps** / **App passwords** (or **Basic and additional settings**). Ensure users can use app passwords or “Less secure app access” if your org still shows that.
2. For your own account:
  - Go to [Google Account](https://myaccount.google.com/) (or [workspace.google.com](https://workspace.google.com) and open Account).
  - **Security** → **2-Step Verification** → turn on if required.
  - **Security** → **App passwords**.
  - If “App passwords” is missing, the admin has disabled it; ask them to allow 2-Step Verification and app passwords for your account.
3. Create the app password as above (Mail, Other, name it, Generate, copy the 16-character password).

**Note:** The app password is the value you put in `SMTP_PASS`; you never use your normal Gmail/Workspace password for SMTP.

---

## 2. Configure the app (env vars)

The worker sends email via [utils/email_notification.py](IFI Essay tool/utils/email_notification.py) using `send_smtp_email()`, which reads:

- `SMTP_HOST` – Gmail: `smtp.gmail.com`
- `SMTP_PORT` – Gmail: `587`
- `SMTP_USER` – Your full Gmail or Workspace address (e.g. `you@gmail.com` or `you@yourdomain.com`)
- `SMTP_PASS` – The **16-character app password** from step 1 (no spaces)
- `SMTP_USE_TLS` – `true` for Gmail
- `FROM_EMAIL` – (optional) Same as `SMTP_USER` if you want the “From” to be your address

Add these to [IFI Essay tool/.env](IFI Essay tool/.env) (do not commit `.env`):

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASS=your-16-char-app-password
SMTP_USE_TLS=true
FROM_EMAIL=your-email@gmail.com
```

If the worker runs in Docker, ensure the same variables are passed into the worker container (your [docker-compose.yml](IFI Essay tool/docker-compose.yml) uses `env_file: - .env`, so adding them to `.env` is enough). Then restart the worker so it picks up the new env:

```bash
docker compose up -d worker
```

---

## 3. Verify

After saving `.env` and restarting the worker, process a submission (e.g. upload a PDF). On job completion the worker will call `send_job_completion_email()`. If SMTP is correct, the user’s email (from the Supabase token) receives the notification. If it fails, worker logs will show the SMTP error (e.g. `SMTPAuthenticationError`).

---

## Optional: document this in the repo

You can add a short doc (e.g. `docs/auth/gmail-app-password.md`) that points to this flow and the required env vars so others can set up Gmail/Workspace sending without searching. The plan does not add this file; say if you want it created.