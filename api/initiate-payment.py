"""
Vercel Serverless Function
POST /api/initiate-payment

Called by the frontend when the user taps "Proceed to Payment".
Reads your PayNexus secret key from Vercel Environment Variables (never
from the frontend) and triggers a real STK push via PayNexus's
STK Push API.

Set these in your Vercel project:
  Project -> Settings -> Environment Variables
    PAYNEXUS_SECRET_KEY   (sk_... from your PayNexus dashboard)
"""

import json
import os
import requests
from http.server import BaseHTTPRequestHandler

from lib.store import set_payment_status, link_checkout_reference

BASE_URL = 'https://paynexus.co.ke/api'


def normalize_phone_number(phone: str) -> str:
    """PayNexus's documented format is 0xxxxxxxxx (e.g. 0746990866).
    Defensive normalization since we don't control what shape the
    frontend sends — handles 254-prefixed, bare 9-digit, or already
    correct 0-prefixed input."""
    digits = ''.join(filter(str.isdigit, phone))
    if digits.startswith('0'):
        return digits
    if digits.startswith('254'):
        return '0' + digits[3:]
    return '0' + digits


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            req_body = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self._send_json({'success': False, 'message': 'Invalid JSON body'}, 400)
            return

        phone_number = req_body.get('phone_number')
        amount = req_body.get('amount')
        reference = req_body.get('reference')
        loan_limit = req_body.get('loan_limit')
        applicant = req_body.get('applicant') or {}

        if not phone_number or not amount:
            self._send_json({'success': False, 'message': 'Missing phone_number or amount'}, 400)
            return

        secret_key = os.environ.get('PAYNEXUS_SECRET_KEY', '')
        if not secret_key:
            print('Missing PAYNEXUS_SECRET_KEY environment variable')
            self._send_json({'success': False, 'message': 'Payment provider not configured'}, 500)
            return

        normalized_phone = normalize_phone_number(phone_number)

        try:
            # TODO: persist the application (applicant, loan_limit) to your
            # real database here — the store below only tracks payment status.
            set_payment_status(
                reference,
                status='PENDING',
                amount=amount,
                phone_number=normalized_phone,
                loan_limit=loan_limit,
            )

            full_name = applicant.get('full_name')
            description = f"Loan application - {full_name}" if full_name else f"Loan application {reference}"

            response = requests.post(
                f'{BASE_URL}/mpesa/payment/initiate',
                headers={
                    'X-API-Key': secret_key,
                    'Content-Type': 'application/json',
                },
                json={
                    'amount': round(float(amount)),
                    'phone': normalized_phone,
                    'description': description,
                },
                timeout=30,
            )

            resp_body = response.json() if response.content else {}

            if not response.ok if hasattr(response, 'ok') else response.status_code >= 400 or not resp_body.get('success'):
                print(f'PayNexus payment initiation failed: {resp_body}')
                set_payment_status(reference, status='FAILED', error=resp_body)
                self._send_json({
                    'success': False,
                    'message': resp_body.get('message', 'Could not reach payment provider'),
                }, 502)
                return

            data = resp_body.get('data', {})

            # status here just means the request was accepted and the STK
            # push is going out — not that the customer has paid. Real
            # confirmation comes from the PayNexus webhook (callback.py),
            # which payment-status.py reports back to the frontend.
            #
            # PayNexus generates ITS OWN reference (unlike our pre-generated
            # one) — link it back to our reference so the webhook, which
            # only carries PayNexus's reference, can be translated back
            # to ours.
            link_checkout_reference(data.get('reference'), reference)
            set_payment_status(
                reference,
                status='PENDING',
                paynexus_reference=data.get('reference'),
                checkout_request_id=data.get('checkout_request_id'),
            )

            self._send_json({
                'success': True,
                'checkout_request_id': data.get('checkout_request_id'),
            }, 200)

        except Exception as err:
            print(f'PayNexus request error: {str(err)}')
            set_payment_status(reference, status='FAILED', error=str(err))
            self._send_json({'success': False, 'message': 'Could not reach payment provider'}, 502)

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
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def log_message(self, format, *args):
        pass
