import json
import os
import requests
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs


def check_transaction_status(reference: str) -> dict:
    """
    Poll PayHero's transaction status API directly.
    No database needed — PayHero holds the source of truth.
    """
    api_url = os.environ.get('PAYHERO_API_URL', 'https://backend.payhero.co.ke/api/v2/payments')
    basic_auth_token = os.environ.get('BASIC_AUTH_TOKEN', '')
    username = os.environ.get('PAYHERO_API_USERNAME', '')
    password = os.environ.get('PAYHERO_API_PASSWORD', '')

    # Build status URL: GET /api/v2/payments?reference=XXX
    status_url = f"{api_url}?reference={reference}"

    headers = {'Content-Type': 'application/json'}
    auth = None

    if basic_auth_token:
        token = basic_auth_token.strip().strip('"').strip("'")
        headers['Authorization'] = token
    elif username and password:
        auth = (username, password)
    else:
        return {'success': False, 'status': 'error', 'message': 'Missing authentication'}

    try:
        response = requests.get(status_url, headers=headers, auth=auth, timeout=15)

        if response.status_code == 200:
            data = response.json()

            # PayHero transaction status values:
            # "Success" / "successful" → paid
            # "Failed" / "cancelled"  → not paid
            # "Pending" / "queued"    → still waiting
            raw_status = (
                data.get('status') or
                data.get('transaction_status') or
                data.get('payment_status') or
                ''
            ).lower()

            if raw_status in ['success', 'successful', 'completed']:
                return {
                    'success': True,
                    'status': 'paid',
                    'message': 'Payment confirmed',
                    'data': data,
                }
            elif raw_status in ['failed', 'cancelled', 'canceled', 'rejected']:
                return {
                    'success': True,
                    'status': 'failed',
                    'message': 'Payment was cancelled or failed',
                    'data': data,
                }
            else:
                # Still pending — tell frontend to keep polling
                return {
                    'success': True,
                    'status': 'pending',
                    'message': 'Waiting for M-Pesa PIN...',
                    'data': data,
                }

        elif response.status_code == 404:
            return {
                'success': True,
                'status': 'pending',
                'message': 'Transaction not yet recorded, still waiting...',
            }
        else:
            return {
                'success': False,
                'status': 'error',
                'message': f"PayHero API returned {response.status_code}",
            }

    except requests.exceptions.Timeout:
        return {'success': False, 'status': 'error', 'message': 'Status check timed out'}
    except Exception as e:
        return {'success': False, 'status': 'error', 'message': str(e)}


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        reference = params.get('reference', [None])[0]

        if not reference:
            self._send_json({'success': False, 'status': 'error', 'message': 'reference param required'}, 400)
            return

        result = check_transaction_status(reference)
        self._send_json(result, 200)

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
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def log_message(self, format, *args):
        pass
