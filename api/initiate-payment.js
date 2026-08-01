/**
 * Vercel Serverless Function
 * POST /api/initiate-payment
 *
 * Called by the frontend when the user taps "Proceed to Payment".
 * Triggers a real STK push through your own Sendit gateway
 * (the "sendit" project), rather than a third-party provider.
 *
 * Set these in your Vercel project:
 *   Project -> Settings -> Environment Variables
 *     SENDIT_API_KEY    (the sk_live_... key from your Sendit dashboard's
 *                        linked account, once it's active)
 *     SENDIT_BASE_URL   (your deployed Sendit app URL, e.g.
 *                        https://your-sendit-app.vercel.app — no trailing slash)
 *
 * NOTE ON ARCHITECTURE: Sendit's callback (Safaricom -> Sendit) is the
 * verified, trusted path on Sendit's side (it checks a per-account
 * callback_token). From camp's point of view we don't receive that
 * callback directly — instead camp authenticates with its own API key
 * and asks Sendit's GET /api/v1/status endpoint, which is backed by
 * Sendit's own stored transaction record (filled in by its callback) or,
 * if that hasn't landed yet, a live Daraja query. See api/payment-status.js
 * and api/callback.js for how that plays out.
 */

const BASE_URL = (process.env.SENDIT_BASE_URL || '').replace(/\/+$/, '');

function normalizePhoneNumber(phone) {
    // Sendit's own normalizePhone (lib/daraja.js) accepts the same common
    // shapes, but we normalize here too so what we log/send is predictable.
    const digits = String(phone).replace(/\D/g, '');
    if (digits.startsWith('254')) return digits;
    if (digits.startsWith('0')) return '254' + digits.slice(1);
    return '254' + digits;
}

export const maxDuration = 30; // seconds — Daraja's real STK response times can exceed Vercel's default limit

export default async function handler(req, res) {
    if (req.method !== 'POST') {
        return res.status(405).json({ success: false, message: 'Method not allowed' });
    }

    const { phone_number, amount, reference } = req.body || {};

    if (!phone_number || !amount) {
        return res.status(400).json({ success: false, message: 'Missing phone_number or amount' });
    }

    if (!reference) {
        return res.status(400).json({ success: false, message: 'Missing reference' });
    }

    if (!process.env.SENDIT_API_KEY || !BASE_URL) {
        console.error('Missing SENDIT_API_KEY or SENDIT_BASE_URL environment variable');
        return res.status(500).json({ success: false, message: 'Payment provider not configured' });
    }

    const normalizedPhone = normalizePhoneNumber(phone_number);

    try {
        console.log('Calling Sendit:', `${BASE_URL}/api/v1/stkpush`, 'phone:', normalizedPhone, 'amount:', amount, 'reference:', reference);

        const response = await fetch(`${BASE_URL}/api/v1/stkpush`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${process.env.SENDIT_API_KEY}`
            },
            body: JSON.stringify({
                phone: normalizedPhone,
                amount: Math.round(Number(amount)),
                account_reference: reference,
                transaction_desc: 'Payment'
            })
        });

        console.log('Sendit response status:', response.status);

        const raw = await response.text();
        console.log('Sendit response body:', raw);

        let body;
        try {
            body = JSON.parse(raw);
        } catch {
            console.error('Sendit returned non-JSON response:', raw);
            return res.status(502).json({ success: false, message: 'Payment provider returned an unexpected response' });
        }

        // Sendit's success responses carry ResponseCode "0" plus
        // CheckoutRequestID — that's what /api/v1/status is queried with,
        // so its presence is the real signal of success here.
        if (!response.ok || !body.CheckoutRequestID) {
            console.error('Sendit STK push failed:', body);
            return res.status(502).json({
                success: false,
                message: body.error || body.ResponseDescription || 'Could not reach payment provider'
            });
        }

        // We keep the field name transaction_request_id for the frontend
        // (it just needs a single opaque handle to poll with) even though
        // the value is Sendit's CheckoutRequestID.
        return res.status(200).json({
            success: true,
            reference,
            transaction_request_id: body.CheckoutRequestID,
            checkout_request_id: body.CheckoutRequestID,
            merchant_request_id: body.MerchantRequestID
        });

    } catch (err) {
        console.error('Sendit request error:', err.name, err.message, err.cause || '');
        return res.status(502).json({ success: false, message: 'Could not reach payment provider' });
    }
}
