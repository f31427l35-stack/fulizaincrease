import hashlib
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler

from lib.store import set_payment_status, get_reference_by_checkout


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            raw_body = self.rfile.read(content_length) if content_length else b''

            # CitaPay signs every webhook with HMAC-SHA256 over the RAW
            # request body, sent in the X-CitaPay-Signature header. Unlike
            # PayHero (which had no documented verification mechanism at
            # all), skipping this check here means anyone who finds this
            # URL could POST a fake "payment.completed" event and get an
            # unpaid transaction marked as paid. So: verify first, trust
            # nothing until it checks out.
            secret = os.environ.get('CITAPAY_WEBHOOK_SECRET', '')
            if not secret:
                print('Missing CITAPAY_WEBHOOK_SECRET — refusing to process an unverifiable webhook')
                self._send_json({'status': 'Error', 'message': 'Webhook secret not configured'}, 500)
                return

            signature = self.headers.get('X-CitaPay-Signature', '')
            expected = hmac.new(secret.encode('utf-8'), raw_body, hashlib.sha256).hexdigest()

            # Constant-time comparison — a plain `!=` leaks timing
            # information that could theoretically help an attacker guess
            # a valid signature byte-by-byte.
            if not signature or not hmac.compare_digest(expected, signature):
                print('CitaPay webhook signature mismatch — ignoring request')
                self._send_json({'status': 'Error', 'message': 'Invalid signature'}, 400)
                return

            data = json.loads(raw_body) if raw_body else {}

            # Log callback data (visible in Vercel function logs)
            print(f"CitaPay Callback received (signature verified): {json.dumps(data, indent=2)}")

            event = data.get('event')
            payload = data.get('data', {})

            # Prefer our own reference echoed back via metadata; fall back
            # to the mapping we stored from CitaPay's own reference at
            # initiate-time.
            metadata = payload.get('metadata') or {}
            reference = metadata.get('our_reference') or get_reference_by_checkout(payload.get('reference'))

            if not reference:
                print(f"No stored reference for this webhook — citapay reference: {payload.get('reference')}")
            elif event == 'payment.completed':
                print(f"Payment succeeded: {payload.get('reference')}")
                set_payment_status(reference, status='SUCCESS', citapay_status=payload.get('status'))
            elif event == 'payment.failed':
                print(f"Payment failed: {payload.get('reference')}")
                set_payment_status(reference, status='FAILED', citapay_status=payload.get('status'))
            # Other event types (payout.*, refund.*, etc.) are ignored here
            # if this endpoint is ever subscribed to more than "payment.*".

            self._send_json({'status': 'Received'}, 200)
        except Exception as e:
            self._send_json({'status': 'Error', 'message': str(e)}, 400)

    def do_GET(self):
        self._send_json({'status': 'Callback endpoint active'}, 200)

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass
