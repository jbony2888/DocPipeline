# Switch Redis from Redis Platform to Render Key Value

Use this when moving from Redis Platform (Redis Cloud / Redis Labs) to **Render Key Value** (Render’s Redis-compatible add-on).

## What you need to change

Only **one** thing: the **`REDIS_URL`** environment variable. No code changes are required; the app supports both `redis://` and `rediss://` (TLS).

---

## 1. Create Render Key Value (Redis)

1. In **Render Dashboard** → **New** → **Key Value** (or **Add-ons** → **Key Value**).
2. Choose **region** (e.g. Oregon) — **same region as your Web Service and Worker** if you want to use the internal URL.
3. Create the instance.
4. Open the instance → **Connect** to see the URLs.

---

## 2. Choose internal vs external URL

| Use case | URL type | Format |
|----------|----------|--------|
| Web + Worker on Render, **same region** as Key Value | **Internal** (recommended) | `redis://red-XXXXXXXX:6379` — no password |
| Connecting from outside Render or different region | **External** | `rediss://red-XXXXXXXX:PASSWORD@REGION-kv.render.com:6379` — TLS + password |

- **Internal**: faster, no password, private network. Use this if both Flask app and RQ worker are Render services in the same region.
- **External**: use `rediss://` (with double “s”) and the host Render gives you (e.g. `oregon-kv.render.com`). Enable “External connections” in the Key Value dashboard if needed.

---

## 3. Set REDIS_URL on Render

1. **Web Service** → **Environment** → edit **REDIS_URL**.
2. **Worker Service** → **Environment** → edit **REDIS_URL**.

Set the value to the URL from step 2, for example:

**Internal (same region):**
```bash
REDIS_URL=redis://red-xxxxxxxxxxxxxxxxxxxxxxxx:6379
```

**External (TLS):**
```bash
REDIS_URL=rediss://red-xxxxxxxxxxxxxxxxxxxxxxxx:YOUR_PASSWORD@oregon-kv.render.com:6379
```

Save; Render will redeploy the services.

---

## 4. Local / .env (optional)

If you run the app or worker locally and want them to talk to Render Redis (external only):

1. In Key Value dashboard, enable **External connections** and note the external URL and password.
2. In `.env`:
   ```bash
   REDIS_URL=rediss://red-xxxx:PASSWORD@REGION-kv.render.com:6379
   ```

---

## 5. Verify

- **Web Service**: open your app, upload a file, and confirm the job runs (e.g. check job status).
- **Worker**: in Render logs for the Worker service, you should see it processing jobs.
- Optional: run `python test_redis_connection.py` in a shell that has `REDIS_URL` set (e.g. Render shell or local with `.env`).

---

## Summary

| Before (Redis Platform) | After (Render Key Value) |
|-------------------------|---------------------------|
| `REDIS_URL=redis://default:PASSWORD@redis-xxxx.cloud.redislabs.com:11474/0` | **Internal:** `redis://red-xxxx:6379` |
| Same env on Web + Worker | **External:** `rediss://red-xxxx:PASSWORD@REGION-kv.render.com:6379` |
| Set in Render env for Web + Worker | Set in Render env for Web + Worker |

No code or config file changes are required beyond updating **REDIS_URL** in the environments where the app and worker run.
