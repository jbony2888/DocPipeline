# Local Testing URLs

## Flask Application URLs

### Main Application
- **Dashboard**: `http://localhost:5000/`
- **Login**: `http://localhost:5000/login`
- **Review Page**: `http://localhost:5000/review`
- **Review (Needs Review)**: `http://localhost:5000/review?mode=needs_review`
- **Review (Approved)**: `http://localhost:5000/review?mode=approved`

### API Endpoints
- **Upload**: `http://localhost:5000/upload` (POST)
- **Batch Status**: `http://localhost:5000/api/batch_status` (GET)
- **Job Status**: `http://localhost:5000/api/job_status/<job_id>` (GET)
- **Clear Jobs**: `http://localhost:5000/api/clear_jobs` (POST)
- **Get Batch**: `http://localhost:5000/api/batches/<upload_batch_id>` (GET)
- **Apply Defaults**: `http://localhost:5000/api/batches/<upload_batch_id>/apply-defaults` (POST)

### Record Management
- **Record Detail**: `http://localhost:5000/record/<submission_id>`
- **Approve Record**: `http://localhost:5000/record/<submission_id>/approve` (POST)
- **Send for Review**: `http://localhost:5000/record/<submission_id>/send_for_review` (POST)
- **Delete Record**: `http://localhost:5000/record/<submission_id>/delete` (POST)

### Export
- **Export All**: `http://localhost:5000/export`
- **Export School**: `http://localhost:5000/export/school/<school_name>`
- **Export Grade**: `http://localhost:5000/export/school/<school_name>/grade/<grade>`

### PDF Serving
- **View PDF**: `http://localhost:5000/pdf/<file_path>`

## Supabase Configuration for Local Testing

### Add to Supabase Redirect URLs

1. Go to: [Supabase Dashboard → Authentication → URL Configuration](https://supabase.com/dashboard/project/escbcdjlafzjxzqiephc/auth/url-configuration)

2. In the **Redirect URLs** section, click **"Add URL"**

3. Add this URL:
   ```
   http://localhost:5000/auth/callback
   ```

4. Click **"Save changes"**

### Site URL (Optional for Local Testing)
You can keep the production URL (`https://docpipeline.onrender.com`) or temporarily change it to:
```
http://localhost:5000
```

## Starting the Application Locally

1. **Set up environment variables** (create `.env` file):
   ```bash
   SUPABASE_URL=https://escbcdjlafzjxzqiephc.supabase.co
   SUPABASE_ANON_KEY=your-anon-key-here
   SUPABASE_SERVICE_ROLE_KEY=your-service-role-key-here
   FLASK_SECRET_KEY=your-secret-key-here
   FLASK_PORT=5000
   GROQ_API_KEY=your-groq-key-here
   ```

2. **Start Flask app**:
   ```bash
   ./START_FLASK_APP.sh
   # OR
   python flask_app.py
   ```

3. **Start worker** (in separate terminal):
   ```bash
   python worker.py
   ```

4. **Access the application**:
   - Open browser: `http://localhost:5000`
   - You'll be redirected to login
   - Enter your email to receive magic link
   - Click the link in email (should redirect to `http://localhost:5000/auth/callback`)
   - You'll be logged in and redirected to dashboard

## Testing Batch Defaults Flow

1. **Upload files**:
   - Go to: `http://localhost:5000/`
   - Select multiple files
   - Click "Process Entries"
   - Wait for processing to complete

2. **Set batch defaults**:
   - Go to: `http://localhost:5000/review?mode=needs_review`
   - You should see "Batch Defaults" panel at the top
   - Enter default school name and grade
   - Click "Apply Defaults to Batch"
   - Verify submissions are updated

3. **Test manual edit protection**:
   - Click on a submission to edit
   - Change the grade manually
   - Go back to review page
   - Re-apply defaults
   - Verify the manually edited grade is NOT overwritten

## Troubleshooting

### Magic Link Not Working
- Verify `http://localhost:5000/auth/callback` is in Supabase redirect URLs
- Check browser console for errors
- Verify `FLASK_SECRET_KEY` is set

### Batch Defaults Not Showing
- Verify you have an active batch in session (upload files first)
- Check browser console for JavaScript errors
- Verify batch was created (check Supabase `upload_batches` table)

### Defaults Not Applying
- Check browser console for API errors
- Verify you're authenticated (check session)
- Check Supabase logs for RLS policy violations

