"""Public-URL transport must pin DNS and refuse redirect rebinding."""
import io
from unittest.mock import Mock
from drift import tools


def test_fetch_default_transport_does_not_use_auto_redirect_opener(monkeypatch):
    called = []
    monkeypatch.setattr(tools, '_host_resolves_public', lambda *a: True)
    monkeypatch.setattr(tools.urllib.request, 'urlopen', lambda *a, **kw: called.append(1))
    monkeypatch.setattr('socket.getaddrinfo', lambda *a, **kw: [(2, 1, 6, '', ('127.0.0.1', 443))])
    result = tools.fetch_url('https://public.example/test')
    assert called == []
    assert result.startswith('Error:')


def test_public_transport_connects_to_checked_ip_not_hostname(monkeypatch):
    import socket, ssl
    from http.client import HTTPSConnection
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **kw:
        [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))])
    connected = []
    sock = Mock()
    monkeypatch.setattr(socket, 'create_connection', lambda target, *a, **kw: connected.append(target) or sock)
    context = Mock(); context.wrap_socket.return_value = sock
    monkeypatch.setattr(ssl, 'create_default_context', lambda: context)
    monkeypatch.setattr(HTTPSConnection, 'request', lambda self, *a, **kw: self.connect())
    response = Mock(status=200); response.headers = {}; response.read.return_value = b''
    monkeypatch.setattr(HTTPSConnection, 'getresponse', lambda self: response)
    tools.fetch_url('https://public.example/test')
    assert connected == [('93.184.216.34', 443)]
    assert context.wrap_socket.call_args.kwargs['server_hostname'] == 'public.example'


def test_fetch_rejects_url_credentials(monkeypatch):
    monkeypatch.setattr(tools, '_host_resolves_public', lambda *a: True)
    called = []
    def opener(request):
        called.append(1)
        return Mock(status=200)
    result = tools.fetch_url('https://owner:secret@public.example/test', opener=opener)
    assert result.startswith('Error:')
    assert not called
