"""Teste deepsearch — căutare + citirea paginilor, cu search și fetch fake."""
import base64

from postsyt import deepsearch as dse


class _FakeHub:
    def __init__(self, online=True):
        self._online = online
        self.submissions = []

    def status(self):
        return [{"online": self._online}]

    def submit(self, url, method="GET", headers=None, body=b"", timeout=40, project="x"):
        self.submissions.append(url)
        return {"status": 200, "headers": {},
                "body_b64": base64.b64encode(
                    b"<html><head><style>.a{color:red}</style></head>"
                    b"<body><script>alert(1)</script><h1>Titlu pagina</h1>"
                    b"<p>Continut esential despre minecraft si pokemoni</p></body></html>").decode()}


class _HubPicat(_FakeHub):
    def __init__(self):
        super().__init__(online=False)

    def submit(self, *a, **k):
        raise AssertionError("NU trebuia să mă chemi — bridge-ul e offline")


FAKE_SEARCH = lambda q, limit=8, hub=None: {  # noqa: E731
    "results": [{"titlu": f"Rez {i}", "url": u} for i, u in enumerate(
        ["https://a.example/p1", "https://b.example/p2", "https://c.example/p3",
         "https://d.example/p4"], 1)],
    "via": "bridge" if hub else "direct"}


def _getter(url, headers=None, timeout=None):
    if "c.example" in url:
        raise ConnectionError("pagina c e moarta")
    return ("<html><body><p>Continut direct pentru " + url + "</p></body></html>")


class TestDeepSearch:
    def test_citeste_paginile_prin_bridge(self, monkeypatch):
        monkeypatch.setattr(dse.websearch, "search", FAKE_SEARCH)
        hub = _FakeHub(online=True)
        rez = dse.deep_search("minecraft pokemon", k=2, hub=hub, getter=_getter)
        assert rez["via"] == "bridge" and rez["rezultate_gasite"] == 4
        assert len(rez["pagini_citite"]) == 2
        p1 = rez["pagini_citite"][0]
        assert p1["ok"] is True
        assert "Continut esential" in p1["continut"]
        assert "<h1>" not in p1["continut"] and "alert" not in p1["continut"]
        assert hub.submissions == ["https://a.example/p1", "https://b.example/p2"]

    def test_bridge_offline_fallback_direct(self, monkeypatch):
        monkeypatch.setattr(dse.websearch, "search", FAKE_SEARCH)
        rez = dse.deep_search("x", k=1, hub=_HubPicat(), getter=_getter)
        assert rez["pagini_citite"][0]["ok"] is True
        assert "Continut direct" in rez["pagini_citite"][0]["continut"]

    def test_pagina_moarta_nu_opreste_restul(self, monkeypatch):
        monkeypatch.setattr(dse.websearch, "search",
                            lambda q, limit=8, hub=None: {
                                "results": [{"titlu": "C", "url": "https://c.example/p3"},
                                            {"titlu": "A", "url": "https://a.example/p1"}],
                                "via": "direct"})
        rez = dse.deep_search("x", k=5, hub=None, getter=_getter)
        assert rez["pagini_citite"][0]["ok"] is False
        assert "eroare" in rez["pagini_citite"][0]
        assert rez["pagini_citite"][1]["ok"] is True
        assert len(rez["pagini_citite"]) == 2  # k e clamped la nr. de rezultate

    def test_strip_html(self):
        out = dse._strip_html("<p>A</p><script>x=1</script><style>B</style>&nbsp;C")
        assert "A" in out and "C" in out and "x=1" not in out and "B" not in out
