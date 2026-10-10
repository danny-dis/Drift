from drift import tools


def test_fetch_keeps_article_after_removing_large_html_head(monkeypatch):
    page='<html><head><script>'+('var ignored=1;'*1000)+'</script></head><body><p>Errors detected during execution are called exceptions.</p></body></html>'
    class Response:
        from io import BytesIO
        body=BytesIO(page.encode())
        status=200
        headers={}
        def read(self,n):return self.body.read(n)
        def close(self):pass
    monkeypatch.setattr(tools,'_host_resolves_public',lambda *a:True)
    text=tools.fetch_url('https://docs.python.org/',max_chars=5000,opener=lambda *a,**kw:Response())
    assert 'Errors detected during execution are called exceptions.' in text
    assert 'var ignored' not in text
