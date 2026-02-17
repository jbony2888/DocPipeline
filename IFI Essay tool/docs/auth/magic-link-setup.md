# Magic Link Authentication Setup Guide

## Overview
The IFI Essay Gateway now uses **passwordless authentication** via magic links (email links). Users enter their email address and receive a secure login link that expires in 1 hour.

## Supabase Configuration Required

### 1. Configure Redirect URLs

You must add your app's callback URL to Supabase's allowed redirect URLs:

1. Go to: **Authentication** → **URL Configuration** in your Supabase project.
2. Set **Site URL** to your app root (e.g. `http://localhost:5000` or `https://your-production-domain.com`).
3. Under **Redirect URLs**, add:
   - For local: `http://localhost:5000/auth/callback`
   - For production: `https://your-production-domain.com/auth/callback`
4. Click **Save**.

The app uses `APP_URL` from `.env` when set to build the magic link redirect; set `APP_URL` in production so links point to your public URL.

### 2. Enable Magic Link Authentication

1. Go to: https://supabase.com/dashboard/project/escbcdjlafzjxzqiephc/auth/providers
2. Find **Email** provider
3. Ensure **Enable Email provider** is checked
4. Under **Email Auth**, ensure **Enable email confirmations** is configured as needed
5. For magic links, you can disable email confirmations or set them to optional

### 3. Send Magic Links From Your Gmail (Recommended)

To send magic link emails **from** your GSuite Gmail (e.g. the address in `EMAIL` / `GMAIL_PASSWORD` in `.env`), configure Supabase custom SMTP. See **[Magic link SMTP (Gmail)](./magic-link-smtp-gmail.md)** for step-by-step setup.

### 4. Email Templates (Optional)

You can customize the magic link email template:

1. Go to: https://supabase.com/dashboard/project/escbcdjlafzjxzqiephc/auth/templates
2. Edit the **Magic Link** template
3. Customize the email subject and body as needed

## How It Works

1. **User enters email**: User visits the login page and enters their email address
2. **Magic link sent**: Supabase sends an email with a secure login link
3. **User clicks link**: User clicks the link in their email
4. **Automatic login**: User is redirected back to the app and automatically logged in
5. **Session persists**: User stays logged in until they log out or the session expires

## Testing

### Local Development

1. Start the app: `docker-compose up` or `flask run` (see project README).
2. Open: http://localhost:5000/login
3. Enter your email address.
4. Check your email for the magic link (from Supabase or your custom Gmail SMTP).
5. Click the link — you should be redirected to `/auth/callback` and then logged in.

### Production Deployment

1. Set `APP_URL` in `.env` (or Render env) to your production URL (e.g. `https://your-app.onrender.com`).
2. Add `https://your-app.onrender.com/auth/callback` to Supabase **Redirect URLs** (see step 1 above).
3. Optionally configure [custom SMTP with Gmail](./magic-link-smtp-gmail.md) so magic links are sent from your Gmail.
4. Deploy and test the magic link flow.

## Troubleshooting

### "Invalid redirect URL" error
- Make sure you've added the redirect URL to Supabase Dashboard > Authentication > URL Configuration

### Email not received
- Check spam/junk folder
- Verify email address is correct
- Check Supabase logs: https://supabase.com/dashboard/project/escbcdjlafzjxzqiephc/logs/edge-logs

### Link doesn't work
- Magic links expire after 1 hour
- Request a new link if the old one expired
- Make sure you're using the correct redirect URL

### Session not persisting
- Check that cookies are enabled in the browser
- Verify Flask session is configured (e.g. `FLASK_SECRET_KEY` set)

## Security Notes

- Magic links expire after 1 hour
- Each link can only be used once
- Links contain secure tokens that are validated by Supabase
- Sessions are managed securely by Supabase Auth





