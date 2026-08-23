from __future__ import annotations

import json
import os
import secrets
import threading
import time
import urllib.parse
import urllib.request
from collections import defaultdict, deque

from flask import jsonify, request


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self._last_cleanup = 0.0

    def allow(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        now = time.time()
        cutoff = now - window_seconds
        with self._lock:
            q = self._events[key]
            while q and q[0] <= cutoff:
                q.popleft()
            if len(q) >= limit:
                retry_after = max(1, int(window_seconds - (now - q[0])))
                return False, retry_after
            q.append(now)
            if now - self._last_cleanup > 300:
                self._cleanup(now)
        return True, 0

    def _cleanup(self, now: float) -> None:
        stale = now - 3600
        for key in list(self._events.keys()):
            q = self._events.get(key)
            if not q:
                self._events.pop(key, None)
                continue
            while q and q[0] < stale:
                q.popleft()
            if not q:
                self._events.pop(key, None)
        self._last_cleanup = now


def install_request_guard(app) -> None:
    limiter = SlidingWindowLimiter()
    trust_cloudflare = os.environ.get('SINANEO_TRUST_CLOUDFLARE', '0') == '1'
    edge_secret = os.environ.get('SINANEO_EDGE_SECRET', '')
    require_edge = os.environ.get('SINANEO_REQUIRE_EDGE_SECRET', '0') == '1'
    turnstile_secret = os.environ.get('SINANEO_TURNSTILE_SECRET', '')
    require_turnstile = os.environ.get('SINANEO_REQUIRE_TURNSTILE', '0') == '1'

    start_per_minute = int(os.environ.get('SINANEO_STARTS_PER_MINUTE', '10'))
    start_per_hour = int(os.environ.get('SINANEO_STARTS_PER_HOUR', '40'))
    messages_per_minute = int(os.environ.get('SINANEO_MESSAGES_PER_MINUTE', '90'))
    global_per_minute = int(os.environ.get('SINANEO_GLOBAL_PER_MINUTE', '300'))
    origin_global_per_minute = int(os.environ.get('SINANEO_ORIGIN_GLOBAL_PER_MINUTE', '5000'))
    origin_starts_per_minute = int(os.environ.get('SINANEO_ORIGIN_STARTS_PER_MINUTE', '300'))
    max_chat_body = int(os.environ.get('SINANEO_MAX_CHAT_BODY_BYTES', '32768'))

    def socket_ip() -> str:
        return (request.remote_addr or 'unknown')[:80]

    def client_ip() -> str:
        if trust_cloudflare:
            cf_ip = (request.headers.get('CF-Connecting-IP') or '').strip()
            if cf_ip:
                return cf_ip[:80]
        forwarded = (request.headers.get('X-Forwarded-For') or '').split(',')[0].strip()
        if forwarded:
            return forwarded[:80]
        return socket_ip()

    def limited(key: str, limit: int, window: int):
        ok, retry_after = limiter.allow(key, max(1, limit), max(1, window))
        if ok:
            return None
        resp = jsonify(error='rate_limited', retryAfter=retry_after)
        resp.status_code = 429
        resp.headers['Retry-After'] = str(retry_after)
        return resp

    def verify_turnstile(token: str, remote_ip: str) -> bool:
        if not turnstile_secret:
            return not require_turnstile
        if not token:
            return False
        body = urllib.parse.urlencode({
            'secret': turnstile_secret,
            'response': token,
            'remoteip': remote_ip,
        }).encode('utf-8')
        req = urllib.request.Request(
            'https://challenges.cloudflare.com/turnstile/v0/siteverify',
            data=body,
            method='POST',
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                payload = json.loads(response.read().decode('utf-8'))
            return payload.get('success') is True
        except Exception:
            return False

    @app.before_request
    def sinaneo_request_guard():
        path = request.path or ''
        if request.method == 'OPTIONS':
            return None

        if not path.startswith('/alanoffer/api/'):
            return None

        if path in {'/alanoffer/api/health', '/alanoffer/api/chat/health'}:
            return None

        ip = client_ip()
        origin_ip = socket_ip()

        blocked = limited(f'origin-global:{origin_ip}', origin_global_per_minute, 60)
        if blocked:
            return blocked
        blocked = limited(f'global:{ip}', global_per_minute, 60)
        if blocked:
            return blocked

        if path.startswith('/alanoffer/api/admin/'):
            return limited(f'admin:{ip}', 120, 60)

        if require_edge:
            supplied = request.headers.get('X-SinaNeo-Edge', '')
            if not edge_secret or not secrets.compare_digest(supplied, edge_secret):
                return jsonify(error='edge_required'), 403

        if path == '/alanoffer/api/chat/start':
            if request.content_length and request.content_length > max_chat_body:
                return jsonify(error='payload_too_large'), 413
            blocked = limited(f'origin-start:{origin_ip}', origin_starts_per_minute, 60)
            if blocked:
                return blocked
            blocked = limited(f'start-minute:{ip}', start_per_minute, 60)
            if blocked:
                return blocked
            blocked = limited(f'start-hour:{ip}', start_per_hour, 3600)
            if blocked:
                return blocked
            if require_turnstile:
                body = request.get_json(silent=True) or {}
                token = str(body.get('turnstileToken') or '')
                if not verify_turnstile(token, ip):
                    return jsonify(error='turnstile_failed'), 403
            return None

        if path == '/alanoffer/api/chat/message':
            if request.content_length and request.content_length > max_chat_body:
                return jsonify(error='payload_too_large'), 413
            body = request.get_json(silent=True) or {}
            session_id = str(body.get('sessionId') or '')[:120]
            key = session_id if session_id else ip
            blocked = limited(f'message:{key}', messages_per_minute, 60)
            if blocked:
                return blocked
            return None

        if path.startswith('/alanoffer/api/request/'):
            return limited(f'request-status:{ip}', 120, 60)

        return None

    @app.after_request
    def sinaneo_security_headers(response):
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
        return response

    @app.get('/security/health')
    def security_health():
        return jsonify(
            ok=True,
            rateLimit=True,
            edgeLock=require_edge and bool(edge_secret),
            turnstile=require_turnstile and bool(turnstile_secret),
            trustCloudflare=trust_cloudflare,
        )
