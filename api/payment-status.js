/**
 * Vercel Serverless Function
 * GET /api/payment-status?transaction_request_id=XXXXXXXX
 *
 * Polled by the frontend every few seconds after initiating a payment.
 *
 * Calls your own Sendit gateway's GET /api/v1/status endpoint directly on
 * every poll, authenticated with your Sendit API key. Sendit resolves this
 * from its own stored transaction record (filled in by Safaricom's callback
 * to Sendit, which IS verified there via a per-account callback_token) or,
 * if that hasn't landed yet, a live Daraja STK query — see Sendit's
 * pages/api/v1/status.js for the details. Either way this endpoint gives an
 * authoritative answer on demand, without camp needing to trust an
 * unverified webhook of its own.
 */

const BASE_URL = (process.env.SENDIT_BASE_URL || '').replace(/\/+$/, '');

function mapStatus(sendItStatus) {
    switch (String(sendItStatus || '').toLowerCase()) {
        case 'success':
            return 'SUCCESS';
        case 'failed':
            return 'FAILED';
        case 'pending':
        default:
            return 'PENDING';
    }
}

export default async function handler(req, res) {
    if (req.method !== 'GET') {
        return res.status(405).json({ status: 'ERROR', message: 'Method not allowed' });
    }

    const { transaction_request_id } = req.query;

    if (!transaction_request_id) {
        return res.status(400).json({ status: 'ERROR', message: 'Missing transaction_request_id' });
    }

    if (!process.env.SENDIT_API_KEY || !BASE_URL) {
        console.error('Missing SENDIT_API_KEY or SENDIT_BASE_URL environment variable');
        return res.status(500).json({ status: 'ERROR', message: 'Payment provider not configured' });
    }

    try {
        // transaction_request_id is actually Sendit's CheckoutRequestID —
        // see the note in initiate-payment.js about keeping the frontend's
        // field name stable while the value comes from Sendit.
        const url = `${BASE_URL}/api/v1/status?checkout_request_id=${encodeURIComponent(transaction_request_id)}`;

        const response = await fetch(url, {
            method: 'GET',
            headers: {
                'Authorization': `Bearer ${process.env.SENDIT_API_KEY}`
            }
        });

        const raw = await response.text();
        console.log('Sendit status raw response:', raw);
        let body;
        try {
            body = JSON.parse(raw);
        } catch {
            console.error('Sendit status returned non-JSON response:', raw);
            // Report PENDING rather than FAILED on a parse hiccup — a
            // transient/malformed response here shouldn't be mistaken for
            // an actual payment failure. The frontend will just poll again.
            return res.status(200).json({ status: 'PENDING' });
        }

        if (!response.ok) {
            console.error('Sendit status call failed:', body);
            return res.status(200).json({ status: 'PENDING' });
        }

        return res.status(200).json({
            status: mapStatus(body.status),
            receipt: body.receipt,
            amount: body.amount
        });

    } catch (err) {
        console.error('Sendit status request error:', err);
        // Network hiccup talking to the provider — report PENDING so the
        // frontend keeps polling rather than giving up on a transient blip.
        return res.status(200).json({ status: 'PENDING' });
    }
}
