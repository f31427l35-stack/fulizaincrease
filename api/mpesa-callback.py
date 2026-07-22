import hashlib
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler


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

            # This minimal version just logs, matching the original
            # PayHero file's scope. If you want this to actually update a
            # payment's status (e.g. for a polling endpoint to read), do
            # that here: look up payload.get('metadata', {}).get('our_reference')
            # or payload.get('reference'), and mark it SUCCESS if
            # event == 'payment.completed', FAILED if 'payment.failed'.
            if event == 'payment.completed':
                print(f"Payment succeeded: {payload.get('reference')}")
            elif event == 'payment.failed':
                print(f"Payment failed: {payload.get('reference')}")

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
