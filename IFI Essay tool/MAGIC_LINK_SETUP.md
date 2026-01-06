# Magic Link Authentication Setup Guide

## Overview
The IFI Essay Gateway now uses **passwordless authentication** via magic links (email links). Users enter their email address and receive a secure login link that expires in 1 hour.

## Supabase Configuration Required

### 1. Configure Redirect URLs

You must add your app's URL to Supabase's allowed redirect URLs:

1. Go to: https://supabase.com/dashboard/project/escbcdjlafzjxzqiephc/auth/url-configuration
2. Under **Redirect URLs**, add:
   - For local development: `http://localhost:8501`
   - For production: `https://your-production-domain.com` (replace with your actual domain)
3. Click **Save**

### 2. Enable Magic Link Authentication

1. Go to: https://supabase.com/dashboard/project/escbcdjlafzjxzqiephc/auth/providers
2. Find **Email** provider
3. Ensure **Enable Email provider** is checked
4. Under **Email Auth**, ensure **Enable email confirmations** is configured as needed
5. For magic links, you can disable email confirmations or set them to optional

### 3. Email Templates (Optional)

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

1. Start the app: `docker-compose up` or `streamlit run app.py`
2. Open: http://localhost:8501
3. Enter your email address
4. Check your email for the magic link
5. Click the link - you should be redirected back and logged in

### Production Deployment

1. Update `redirect_url` in `auth/auth_ui.py` to your production domain
2. Add your production URL to Supabase redirect URLs (see step 1 above)
3. Rebuild and deploy your app
4. Test the magic link flow

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
- Verify Supabase session is being stored in `st.session_state`

## Security Notes

- Magic links expire after 1 hour
- Each link can only be used once
- Links contain secure tokens that are validated by Supabase
- Sessions are managed securely by Supabase Auth

