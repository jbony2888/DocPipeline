# Copy This for Render Deployment

## Google Cloud Vision Credentials

**Copy this ENTIRE string** (everything between the quotes):

```
{"type":"service_account","project_id":"youtube-ai-tool-478918","private_key_id":"1941d902d881dcaf66ff970127926db540894cb0","private_key":"-----BEGIN PRIVATE KEY-----\nMIIEvAIBADANBgkqhkiG9w0BAQEFAASCBKYwggSiAgEAAoIBAQDsxke4AF6PUTby\natcTwLFVXcEN7qVlP77FLCPe7i0KlIDHzcdUCnlpYEJhm22+ckH3Fpp0+Ael6nXL\n1mskrtIMTgP7LCHqB470Jh1nFSinSl8GvZSEgJroQEA77w9cdJlcmvfzO+2AW8mW\nHDSBi376QA5cS9ofIxk7XWtOzRSurLqMhYL/dnv7GYWxVI1vnBP9IpJ9NXvDxbb0\n7fJDcRBNb2Ua6lyRictU3enn53RlQO/HR0OudWnV4sSuLWOfRqUbS63lY/nsmqGM\nyDuYCV30GNaAXGTSXLcYKTjEcWVjHc6iF7X6/81dWnbs6dOds8RwMhLRhrk15f8g\n7ynx/mRBAgMBAAECggEAZo3TTo1KZ8UDiahhE/soVBNRpRkyplIf7QMbXlnHRIfh\n56jnpy0KPWwmFGTf+dc/Xyh5KiSsG18cOnfa3H6kGBRKgSYyYk13y6QepCF0BFGg\nKyk+BM43SlVZ/RukiaUvL/8nWkEgs7IN9GivDVVAYGASWEO6bDYlnaLu8ai+RpFQ\nyxldhPi2N21qiB5F5e1swtZN7q93Zta6CqYizSaObYu0OMee7d0tB++b8+eHwjjb\nbc8yBKm7OY+Ay7r/XeK77LVOMFZeGy8ZAz2ZaAgT1HyvkLczdj4mEIjhfiUVoRzi\nC8wk2DUE8t7KmsxHARKHf2TANsKqZ+UkBnK+B4qzKQKBgQD4VML8RXWZ/jCkRFir\nJdMl/XYNqIM0BNvIcxqJDnTsel0TWfLv9/uNHCF6QqEGIZtws0zi7rAe+/POG7kf\nm8Hjojyayor1TcSDiyn1wShq58CfqJTjhKV6zUILzkXvDJvk1AMVl1Cl+ylhOVKk\n9ZIphjQPGHM44lZyUQS2WN5rKwKBgQD0FifH35cxYsSuOQMLZJN2LRmCh/1+d6qP\nPbLANMY2go2M9w+h8KfY/NRIOJIG7qHbJraBirCa2iATKvD7aBeiHIkkMG7drrdY\nHmHArNIpBy5sAOWbevlpJQRE59M6HELdArYEL26bWEYRDToPBo86r9/lbNNZ2SpT\nqAwIQc0IQwKBgBAYrmrbtbu9ljmPlI/Da+RSgYxxF9APYI+lplqr7ThG1jGi6vRT\nBqMm56SdHQLgusqbVKiBADmB61O4yE8cMX0nzvXZmxg7ajl8k8OyOYR0cS/oJX55\n4qALHfTV8gKEtrYmZ+zGWhvoI86BgLHgmRDH+ifgVdeiFChkyAFp0UDxAoGAFbHW\nbVR5OsF9m8Kje6K/3JQbnVd693+pYDvqpFzMdVHbRPk8oXcjZAzszVKB4C3bov/o\n3tC1672RdkKt0pqo5xbENbw8TmXWE/X3WEnEEDN8M8tMnSor+uV4YKt+Qb77TmuM\nRAj3OsV4zNExJN6/Ykb5jonCq0y7D15zW1SF5cMCgYA2Pm0rZ7uNw8SLScqam/i/\nKDrGsl/+IntmYzSNmiCfl7Ryfibh5nwtD6bNdOhWgT9XYAUwJyOU19KZmvAfRtFD\nqve23bcdFvlUjBzvYfUAkoguiq/Gzlp98yD8EdzvUFGuUABwDycYJ1inF+JDQ49Z\nt86DZucFJGYU8dEsMYshFQ==\n-----END PRIVATE KEY-----\n","client_email":"essay-forms@youtube-ai-tool-478918.iam.gserviceaccount.com","client_id":"100480778647871249613","auth_uri":"https://accounts.google.com/o/oauth2/auth","token_uri":"https://oauth2.googleapis.com/token","auth_provider_x509_cert_url":"https://www.googleapis.com/oauth2/v1/certs","client_x509_cert_url":"https://www.googleapis.com/robot/v1/metadata/x509/essay-forms%40youtube-ai-tool-478918.iam.gserviceaccount.com","universe_domain":"googleapis.com"}
```

---

## Step-by-Step Instructions

### 1. Go to Render Dashboard
- Visit: https://dashboard.render.com
- Select your service: `ifi-essay-gateway`

### 2. Add Google Cloud Vision Variable
- Click: **"Environment"** tab (left sidebar)
- Click: **"Add Environment Variable"**
- **Key**: `GOOGLE_CLOUD_VISION_CREDENTIALS_JSON`
- **Value**: Paste the entire JSON string above (starts with `{"type":"service_account"` and ends with `"universe_domain":"googleapis.com"}`)
- Click: **"Save Changes"**

### 3. Add Groq API Key
- Click: **"Add Environment Variable"** again
- **Key**: `GROQ_API_KEY`
- **Value**: Copy this exact key:
  ```
  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
  ```
- Click: **"Save Changes"**

### 4. Deploy
- Your service will automatically redeploy, OR
- Click **"Manual Deploy"** → **"Clear build cache & deploy"**

---

## Quick Checklist

- [ ] Copied the entire JSON string (everything from `{` to `}`)
- [ ] Pasted into Render dashboard as `GOOGLE_CLOUD_VISION_CREDENTIALS_JSON`
- [ ] Added `GROQ_API_KEY` = `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`
- [ ] Saved both variables
- [ ] Redeployed service

---

**That's it!** Your app should now work on Render. ✅

