"""
Minimal shared status store, keyed by payment reference.

IMPORTANT LIMITATION (read before relying on this):
Vercel deploys each file under /api as a SEPARATE serverless function.
initiate-payment.py, callback.py, and payment-status.py are three
independent functions that do not reliably share the same running
process — a plain in-memory dict here can work while testing casually
(if Vercel happens to route repeat calls to a warm container that
already has this module loaded), but there is NO guarantee that
initiate-payment.py writing a value here means callback.py or
payment-status.py can see it, especially under real concurrent traffic
or after any cold start.

This is fine to keep moving today, but before this is relied on for the
actual judged run: swap the four functions below for a real external
store — Vercel KV or Upstash Redis both work over a simple REST API and
would need only these four functions rewritten, nothing else in the
other files.
"""

_store = {}


def set_payment_status(reference: str, **fields) -> None:
    existing = _store.get(reference, {})
    existing.update(fields)
    _store[reference] = existing


def get_payment_status(reference: str) -> dict | None:
    return _store.get(reference)


def link_checkout_reference(provider_reference: str, our_reference: str) -> None:
    """Providers often identify a transaction by their own reference/ID,
    not ours — this lets a webhook translate their ID back to ours."""
    _store[f'checkout:{provider_reference}'] = our_reference


def get_reference_by_checkout(provider_reference: str) -> str | None:
    return _store.get(f'checkout:{provider_reference}')

