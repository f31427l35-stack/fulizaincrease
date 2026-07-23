import json
import os
import requests
from http.server import BaseHTTPRequestHandler

from lib.store import set_payment_status, link_checkout_reference


def normalize_phone(phone: str) -> str:
    """PayNexus's documented format is 0xxxxxxxxx (e.g. 0746990866).
    Defensive normalization since the frontend now leaves the leading
    0 visible as typed — handles 254-prefixed or bare 9-digit input too."""
    digits = ''.join(filter(str.isdigit, phone))
    if digits.startswith('0'):
        return digits
    if digits.startswith('254'):
        return '0' + digits[3:]
    return '0' + digits


def get_base_url() -> str:
    return 'https://paynexus.co.ke/api'


def initiate_stk_push(phone_number: str, amount: float, description: str = None) -> dict:
    """Call PayNexus's STK Push API."""
    secret_key = os.environ.get('PAYNEXUS_SECRET_KEY', '')

    if not secret_key:
        print('Missing PAYNEXUS_SECRET_KEY environment variable')
        return {'success': False, 'message': 'Missing config: PAYNEXUS_SECRET_KEY'}

    phone_number = normalize_phone(phone_number)

    headers = {
        'Content-Type': 'application/json',
        'X-API-Key': secret_key,
    }

    payload = {
        'amount': int(float(amount)),
        'phone': phone_number,
    }
    if description:
        payload['description'] = description

    api_url = f'{get_base_url()}/mpesa/payment/initiate'

    try:
        response = requests.post(api_url, headers=headers, json=payload, timeout=30)

        # TEMP DEBUG — remove once we've diagnosed the response issue
        print(f"PayNexus status code: {response.status_code}")
        print(f"PayNexus raw response: {response.text[:500]!r}")
        print(f"PayNexus response headers: {dict(response.headers)}")

        body = response.json() if response.content else {}

        if response.status_code in (200, 201) and body.get('success'):
            data = body.get('data', {})
            paynexus_reference = data.get('reference')

            # PayNexus generates ITS OWN reference — link it back to our
            # own reference so the webhook (which only carries PayNexus's
            # reference) can be translated back to ours.
            if paynexus_reference:
                link_checkout_reference(paynexus_reference, phone_number)

            return {
                'success': True,
                'reference': paynexus_reference,
                'checkout_request_id': data.get('checkout_request_id'),
                'data': data,
            }
        else:
            message = body.get('message') if isinstance(body, dict) else None
            return {
                'success': False,
                'message': message or f"STK Push failed with status {response.status_code}",
                'detail': body,
            }
    except requests.exceptions.Timeout:
        print("PayNexus request timed out")
        return {'success': False, 'message': 'Payment API request timed out.'}
    except requests.exceptions.RequestException as e:
        print(f"PayNexus network error: {str(e)}")
        return {'success': False, 'message': f'Network error: {str(e)}'}
    except Exception as e:
        print(f"PayNexus unexpected error: {str(e)}")
        return {'success': False, 'message': f'Unexpected error: {str(e)}'}


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body)

            phone_number = data.get('phone_number', '')
            amount = data.get('amount', 0)
            reference = data.get('reference')
            description = data.get('description') or data.get('customer_name')

            if not phone_number or not amount:
                self._send_json({'success': False, 'message': 'phone_number and amount are required'}, 400)
                return

            if isinstance(amount, str):
                amount = float(amount.replace(',', ''))

            # Record our own PENDING entry before calling PayNexus, so
            # payment-status.py has something to report even if the
            # request is still in flight.
            if reference:
                set_payment_status(reference, status='PENDING', amount=amount, phone_number=phone_number)

            result = initiate_stk_push(phone_number, amount, description)

            if result.get('success') and reference:
                set_payment_status(
                    reference,
                    status='PENDING',
                    paynexus_reference=result.get('reference'),
                    checkout_request_id=result.get('checkout_request_id'),
                )
            elif reference:
                set_payment_status(reference, status='FAILED', error=result.get('message'))

            status = 200 if result.get('success') else 500
            self._send_json(result, status)

        except json.JSONDecodeError:
            self._send_json({'success': False, 'message': 'Invalid JSON body'}, 400)
        except Exception as e:
            print(f"initiate-payment handler exception: {str(e)}")
            self._send_json({'success': False, 'message': str(e)}, 500)

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
