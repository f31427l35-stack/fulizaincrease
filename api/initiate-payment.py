import json
import os
import uuid
import requests
from http.server import BaseHTTPRequestHandler


def normalize_phone(phone: str) -> str:
    """Normalize phone number to 2547xxxxxxx format."""
    phone = ''.join(filter(str.isdigit, phone)).lstrip('0')
    if phone.startswith('0'):
        phone = '254' + phone[1:]
    elif not phone.startswith('254'):
        phone = '254' + phone
    return phone


def get_base_url() -> str:
    """CitaPay has separate sandbox/production hosts — pick one via env var."""
    env = os.environ.get('CITAPAY_ENV', 'sandbox').strip().lower()
    if env == 'production':
        return 'https://citapayapi.citatech.cloud/api/v1'
    return 'https://sandbox.citapayapi.citatech.cloud/api/v1'


def initiate_stk_push(phone_number: str, amount: float, customer_name: str = None) -> dict:
    """Call CitaPay's Payments API to initiate an M-Pesa STK push."""
    api_key = os.environ.get('CITAPAY_API_KEY', '')

    # Validate required config
    if not api_key:
        return {'success': False, 'message': 'Missing config: CITAPAY_API_KEY'}

    reference = str(uuid.uuid4())[:8].upper()
    phone_number = normalize_phone(phone_number)

    # A fresh key per logical request — prevents a network retry or a
    # double-tap on the frontend from creating a duplicate STK push.
    idempotency_key = str(uuid.uuid4())

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}',
        'Idempotency-Key': idempotency_key,
    }

    payload = {
        'amount': int(float(amount)),
        'paymentMethod': 'MPESA',
        'phoneNumber': phone_number,
        'metadata': {
            'our_reference': reference,
        },
    }
    if customer_name:
        payload['customerName'] = customer_name

    api_url = f'{get_base_url()}/checkout/payments'

    try:
        response = requests.post(api_url, headers=headers, json=payload, timeout=30)
        if response.status_code == 201:
            data = response.json()
            # data['reference'] is CITAPAY'S own reference (e.g. TXNABC123DEF),
            # separate from our internal `reference` above. Both matter:
            # our reference is what the frontend polls with; CitaPay's is
            # what you'd use to call their cancel/refund endpoints later.
            return {
                'success': True,
                'reference': reference,
                'citapay_reference': data.get('reference'),
                'transaction_id': data.get('transactionId'),
                'data': data,
            }
        else:
            detail = response.json() if response.content else response.text
            message = detail.get('message') if isinstance(detail, dict) else None
            return {
                'success': False,
                'message': message or f"STK Push failed with status {response.status_code}",
                'detail': detail,
            }
    except requests.exceptions.Timeout:
        return {'success': False, 'message': 'Payment API request timed out.'}
    except requests.exceptions.RequestException as e:
        return {'success': False, 'message': f'Network error: {str(e)}'}
    except Exception as e:
        return {'success': False, 'message': f'Unexpected error: {str(e)}'}


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body)

            phone_number = data.get('phone_number', '')
            amount = data.get('amount', 0)
            customer_name = data.get('customer_name')

            if not phone_number or not amount:
                self._send_json({'success': False, 'message': 'phone_number and amount are required'}, 400)
                return

            # Strip commas from amount if it's a string (e.g. "1,000")
            if isinstance(amount, str):
                amount = float(amount.replace(',', ''))

            result = initiate_stk_push(phone_number, amount, customer_name)
            status = 200 if result.get('success') else 500
            self._send_json(result, status)

        except json.JSONDecodeError:
            self._send_json({'success': False, 'message': 'Invalid JSON body'}, 400)
        except Exception as e:
            self._send_json({'success': False, 'message': str(e)}, 500)

    def do_OPTIONS(self):
        """Handle CORS preflight."""
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
        pass  # Suppress default logging noise
