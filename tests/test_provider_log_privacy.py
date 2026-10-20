"""Offline synthetic fixtures: provider logs must not retain private content."""
from contextlib import nullcontext
import logging
from types import SimpleNamespace

import httpx
import pytest


@pytest.mark.parametrize('failure', [False, True])
def test_request_and_failure_logs_are_metadata_only(monkeypatch, caplog, failure):
    from drift import providers
    marker = 'SYNTHETIC_PRIVATE_PROVIDER_CONTENT'

    def create(**kwargs):
        if failure:
            raise RuntimeError(marker)
        return SimpleNamespace(model='offline-fixture', usage=None)

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(providers, '_completions_client', lambda: nullcontext(client))
    monkeypatch.setattr(providers, '_normalize_completions_response', lambda _: {'text': 'ok'})
    caplog.set_level(logging.INFO, logger='drift.providers')
    if failure:
        with pytest.raises(RuntimeError, match=marker):
            providers._chat_completions([{'role': 'user', 'content': marker}], tools=False)
    else:
        providers._chat_completions([{'role': 'user', 'content': marker}], tools=False)
    assert marker not in caplog.text
    assert 'chat_completions' in caplog.text


def test_http_error_log_omits_body_and_credential_url(caplog):
    from drift.providers import _log_error_response
    marker = 'SYNTHETIC_PRIVATE_PROVIDER_CONTENT'
    response = httpx.Response(401, text=marker,
        request=httpx.Request('GET', 'http://user:fixture-password@localhost/test'))
    caplog.set_level(logging.INFO, logger='drift.providers')
    _log_error_response(response)
    assert marker not in caplog.text and 'fixture-password' not in caplog.text
    assert '401' in caplog.text
