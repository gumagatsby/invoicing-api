"""Stands in for a merchant's server in the local stack, so the demo's webhooks have somewhere to go.

It accepts every delivery and logs the event. A real receiver must check the signature before
trusting a delivery; services/webhooks.verify is what that check looks like.
"""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer


class Receiver(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        event = json.loads(body or b"{}").get("type", "?")
        print(f"received {event}, signature {self.headers.get('Invoicing-Signature', 'missing')[:20]}...", flush=True)
        self.send_response(204)
        self.end_headers()

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 9000), Receiver).serve_forever()
