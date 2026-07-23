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

            # PayNexus signs every webhook with HMAC-SHA256 over the RAW
            # request body, sent in X-PayNexus-Signature. Verify first,
            # trust nothing until it checks out.
            secret = os.environ.get('PAYNEXUS_WEBHOOK_SECRET', '')
            if not secret:
                print('Missing PAYNEXUS_WEBHOOK_SECRET — refusing to process an unverifiable webhook')
                self._send_json({'ResultCode': 1, 'ResultDesc': 'Webhook secret not configured'}, 500)
                return

            signature = self.headers.get('X-PayNexus-Signature', '')
            expected = hmac.new(secret.encode('utf-8'), raw_body, hashlib.sha256).hexdigest()

            if not signature or not hmac.compare_digest(expected, signature):
                print('PayNexus webhook signature mismatch — ignoring request')
                self._send_json({'ResultCode': 1, 'ResultDesc': 'Invalid signature'}, 401)
                return

            data = json.loads(raw_body) if raw_body else {}
            print(f"PayNexus Callback received (signature verified): {json.dumps(data, indent=2)}")

            event = data.get('event')
            payload = data.get('data', {})

            paynexus_reference = payload.get('reference')
            reference = get_reference_by_checkout(paynexus_reference) if paynexus_reference else None

            if not reference:
                print(f"No stored reference for this webhook — PayNexus reference: {paynexus_reference}")
            elif event == 'payment.completed':
                print(f"Payment succeeded: {paynexus_reference}")
                set_payment_status(
                    reference,
                    status='SUCCESS',
                    provider_transaction_id=payload.get('provider_transaction_id'),
                    payer_name=payload.get('payer_name'),
                )
            elif event == 'payment.failed':
                print(f"Payment failed: {paynexus_reference}")
                set_payment_status(
                    reference,
                    status='FAILED',
                    failure_reason=payload.get('failure_reason'),
                    user_message=payload.get('user_message'),
                )
            elif event == 'payment.initiated':
                print(f"Payment initiated confirmed by webhook: {paynexus_reference}")
            # invoice.*, subscription.* events ignored unless subscribed.

            self._send_json({'ResultCode': 0, 'ResultDesc': 'Received'}, 200)
        except Exception as e:
            self._send_json({'ResultCode': 1, 'ResultDesc': str(e)}, 400)

    def do_GET(self):
        self._send_json({'status': 'Callback endpoint active'}, 200)

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors_headers()
        self.end_headers()

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data).encode('utf-8')
        self.send_response(status)
        self._cors_headers()
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-PayNexus-Signature')

    def log_message(self, format, *args):
        pass
