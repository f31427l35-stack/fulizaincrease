/**
 * Vercel Serverless Function
 * POST /api/callback
 *
 * Optional: register this URL (https://your-app.vercel.app/api/callback)
 * as a webhook on your Sendit account (Sendit dashboard -> Webhooks) if you
 * want a push notification in this app's logs in addition to polling.
 *
 * IMPORTANT — WHY THIS DOESN'T MARK ANYTHING AS PAID:
 * Sendit forwards webhook payloads (see its pages/api/v1/status.js) without
 * any signature scheme — no HMAC, no secret. That means anyone who
 * discovers this URL could POST a fake "success" payload with no way for
 * us to tell it apart from a real one. So this handler deliberately does
 * NOT update any payment status based on what it receives — it only logs
 * the event for visibility/debugging.
 *
 * The actual source of truth for payment status is api/payment-status.js,
 * which queries Sendit's own GET /api/v1/status endpoint directly
 * (authenticated with our Sendit API key) every time the frontend polls.
 * That can't be spoofed the way an open webhook can, since it requires our
 * real API key to even ask the question.
 *
 * If Sendit later adds webhook signing, this is the file to update —
 * verify first, then it would be safe to let this also update a store
 * directly rather than just logging.
 */

export default async function handler(req, res) {
    if (req.method !== 'POST') {
        return res.status(405).json({ status: 'received' });
    }

    console.log('Sendit webhook received (UNVERIFIED — logged only, not trusted):', JSON.stringify(req.body, null, 2));

    // Deliberately no status update here — see the note above.

    res.status(200).json({ status: 'received' });
}
