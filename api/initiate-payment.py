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


def initiate_stk_push(phone_number: str, amount: float) -> dict:
    """Call PayHero API to initiate an M-Pesa STK push."""
    api_url = os.environ.get('PAYHERO_API_URL', 'https://backend.payhero.co.ke/api/v2/payments')
    channel_id = os.environ.get('PAYHERO_CHANNEL_ID', '')
    callback_url = os.environ.get('PAYHERO_CALLBACK_URL', '')
    basic_auth_token = os.environ.get('BASIC_AUTH_TOKEN', '')
    username = os.environ.get('PAYHERO_API_USERNAME', '')
    password = os.environ.get('PAYHERO_API_PASSWORD', '')

    # Validate required config
    missing = []
    if not api_url: missing.append('PAYHERO_API_URL')
    if not channel_id: missing.append('PAYHERO_CHANNEL_ID')
    if not callback_url: missing.append('PAYHERO_CALLBACK_URL')
    if missing:
        return {'success': False, 'message': f"Missing config: {', '.join(missing)}"}

    has_token = bool(basic_auth_token.strip().strip('"').strip("'"))
    has_creds = bool(username and password)
    if not (has_token or has_creds):
        return {'success': False, 'message': 'Missing PayHero authentication credentials'}

    reference = str(uuid.uuid4())[:8].upper()
    description = f"Fuliza Updatess Charge - {reference}"
    phone_number = normalize_phone(phone_number)

    headers = {'Content-Type': 'application/json'}
    auth = None

    if has_token:
        token = basic_auth_token.strip().strip('"').strip("'")
        headers['Authorization'] = token
    else:
        auth = (username, password)

    # Convert channel_id to int if numeric
    ch_id = int(channel_id) if str(channel_id).isdigit() else channel_id

    payload = {
        'amount': int(float(amount)),
        'phone_number': phone_number,
        'channel_id': ch_id,
        'provider': 'm-pesa',
        'external_reference': reference,
        'callback_url': callback_url,
        'description': description,
    }

    try:
        response = requests.post(api_url, headers=headers, json=payload, auth=auth, timeout=30)
        if response.status_code in [200, 201]:
            data = response.json()
            # Extract the transaction reference PayHero assigns
            # so the frontend can poll check-payment with it
            payhero_ref = (
                data.get('reference') or
                data.get('transaction_reference') or
                data.get('CheckoutRequestID') or
                data.get('id') or
                reference  # fallback to our own reference
            )
            return {'success': True, 'reference': payhero_ref, 'data': data}
        else:
            detail = response.json() if response.content else response.text
            return {
                'success': False,
                'message': f"STK Push failed with status {response.status_code}",
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

            if not phone_number or not amount:
                self._send_json({'success': False, 'message': 'phone_number and amount are required'}, 400)
                return

            # Strip commas from amount if it's a string (e.g. "1,000")
            if isinstance(amount, str):
                amount = float(amount.replace(',', ''))

            result = initiate_stk_push(phone_number, amount)
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
