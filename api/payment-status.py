"""
GET /api/payment-status?reference=XXXXXXXX

Polled by the frontend after initiating a payment, so the UI only shows
"Success" once callback.py has actually recorded a verified confirmation
— never based on the initial "queued" response from initiate-payment.py
alone.
"""

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from lib.store import get_payment_status


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        reference = params.get('reference', [None])[0]

        if not reference:
            self._send_json({'status': 'ERROR', 'message': 'reference param required'}, 400)
            return

        record = get_payment_status(reference)

        if not record:
            self._send_json({'status': 'UNKNOWN', 'message': 'No record for this reference yet'}, 404)
            return

        self._send_json({'status': record.get('status', 'PENDING')}, 200)

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
