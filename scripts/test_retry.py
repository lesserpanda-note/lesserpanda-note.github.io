#!/usr/bin/env python3
"""Unit tests for read_url's retry of transient failures in fetch_news.py.

Run: python scripts/test_retry.py   (plain asserts, no network)
"""
from __future__ import annotations

import importlib.util
import io
import urllib.error
from pathlib import Path

_spec = importlib.util.spec_from_file_location("fetch_news", Path(__file__).with_name("fetch_news.py"))
fn = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fn)
fn.RETRY_DELAYS = (0, 0)
fn.time.sleep = lambda _s: None


def http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://x", code, "err", {}, None)


def scripted(*outcomes):
    """Stand-in for urlopen that raises or returns each outcome in turn."""
    calls = []

    def urlopen(_req, timeout):
        calls.append(timeout)
        out = outcomes[len(calls) - 1]
        if isinstance(out, Exception):
            raise out
        return io.BytesIO(out)
    return urlopen, calls


def run(*outcomes):
    urlopen, calls = scripted(*outcomes)
    fn.urllib.request.urlopen = urlopen
    try:
        return fn.read_url(fn.urllib.request.Request("https://x")), len(calls)
    except Exception as exc:
        return exc, len(calls)


def test_502_then_ok_is_retried():
    assert run(http_error(502), b"feed") == (b"feed", 2)


def test_network_errors_retried_until_exhausted():
    out, n = run(urllib.error.URLError("reset"), TimeoutError(), http_error(503))
    assert n == 3 and isinstance(out, urllib.error.HTTPError) and out.code == 503


def test_4xx_is_not_retried():
    out, n = run(http_error(403), b"never")
    assert n == 1 and out.code == 403


def test_429_is_retried():
    assert run(http_error(429), b"ok") == (b"ok", 2)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"ok ({len(tests)} tests)")
