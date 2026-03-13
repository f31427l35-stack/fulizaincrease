import json
from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body) if body else {}
            # Log callback data (visible in Vercel function logs)
            print(f"M-Pesa Callback received: {json.dumps(data, indent=2)}")
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
