# Send Magic Link Emails From Your GSuite Gmail

Magic link emails are sent by **Supabase Auth**. By default Supabase uses its own SMTP (limited and not for production). To send magic links **from** your GSuite Gmail (from `EMAIL` in your `.env`), configure Supabase to use custom SMTP with the same credentials as in your `.env`.

## Prerequisites

- Gmail/Google Workspace account with 2FA enabled
- App password for that account (use the same `EMAIL` and `GMAIL_PASSWORD` as in `.env`)

## Configure Supabase Custom SMTP

1. Open your project in the Supabase Dashboard.
2. Go to **Authentication** → **SMTP Settings** (or **Project Settings** → **Auth** → **SMTP**).
3. Enable **Custom SMTP** and set:

   | Field        | Value                    |
   |-------------|---------------------------|
   | Sender email| Your Gmail (e.g. from `EMAIL` in .env) |
   | Sender name | e.g. "IFI Essay Gateway"  |
   | Host        | `smtp.gmail.com`          |
   | Port        | `587` (TLS) or `465` (SSL)|
   | Username    | Same as sender (your Gmail)|
   | Password    | Gmail app password (same as `GMAIL_PASSWORD` in .env) |

4. Save. Supabase will use this SMTP for all Auth emails (magic link, confirmations, etc.).

## Redirect URL for Magic Links

- In **Authentication** → **URL Configuration**, set:
  - **Site URL**: Your app’s public URL (e.g. `https://your-app.onrender.com` or `http://localhost:5000` for local).
  - **Redirect URLs**: Add the exact callback URL users land on after clicking the link, e.g.:
    - `http://localhost:5000/auth/callback` (local)
    - `https://your-app.onrender.com/auth/callback` (production)

The app uses `APP_URL` from `.env` when set to build the redirect URL for the magic link; ensure `APP_URL` matches the URL you use in Supabase (e.g. `https://your-app.onrender.com`).

## Flow Summary

- Users enter email on the login page → app calls `sign_in_with_otp` with `should_create_user: True`.
- Supabase sends the magic link email **via your Gmail** (once custom SMTP is configured).
- User clicks the link → Supabase redirects to your `.../auth/callback` with tokens.
- App sets the session; if it’s the user’s first time, Supabase creates the account automatically.

No code changes are required for “send from this email”; only Supabase SMTP configuration and `EMAIL` / `GMAIL_PASSWORD` in `.env` (and optionally `APP_URL` for production).
