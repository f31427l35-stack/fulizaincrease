# FulizaUpdatess — Vercel Edition

A Fuliza limit increase app with PayHero M-Pesa STK Push integration, built for Vercel deployment.

## Project Structure

```
fuliza-vercel/
├── index.html                  # Full frontend (static)
├── api/
│   ├── initiate-payment.py     # POST /api/initiate-payment  → PayHero STK Push
│   └── mpesa-callback.py       # POST /api/mpesa-callback    → M-Pesa callback
├── vercel.json                 # Vercel routing config
├── requirements.txt            # Python dependencies
└── .env.example                # Environment variable template
```

## Deploy to Vercel

### 1. Push to GitHub
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

### 2. Import on Vercel
- Go to https://vercel.com/new
- Import your GitHub repo
- Vercel auto-detects the config

### 3. Set Environment Variables
In your Vercel project → **Settings → Environment Variables**, add:

| Variable | Value |
|---|---|
| `PAYHERO_API_URL` | `https://backend.payhero.co.ke/api/v2/payments` |
| `PAYHERO_CHANNEL_ID` | Your channel ID from PayHero dashboard |
| `BASIC_AUTH_TOKEN` | `Basic <your_base64_token>` |
| `PAYHERO_CALLBACK_URL` | `https://your-project.vercel.app/api/mpesa-callback` |

> **Tip:** Get your `BASIC_AUTH_TOKEN` by base64-encoding `username:password`:
> ```bash
> echo -n "your_username:your_password" | base64
> ```
> Then prefix with `Basic `: `Basic dXNlcm5hbWU6cGFzc3dvcmQ=`

### 4. Redeploy
After setting env vars, trigger a redeploy from the Vercel dashboard.

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/initiate-payment` | Initiates M-Pesa STK push via PayHero |
| `POST` | `/api/mpesa-callback` | Receives payment result from PayHero |

### POST /api/initiate-payment
```json
// Request
{ "phone_number": "254712345678", "amount": "99" }

// Success response
{ "success": true, "data": { ...payhero_response } }

// Error response
{ "success": false, "message": "Error description" }
```
