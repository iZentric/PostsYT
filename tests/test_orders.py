import json
from types import SimpleNamespace

from postsyt import orders


def _cfg(tmp_path):
    return SimpleNamespace(data_dir=str(tmp_path / "data"),
                           cookies_file="data/cookies.txt",
                           cookies_json="data/cookies.json",
                           own_channel_id="UC" + "x" * 22)


class FakeStore:
    def __init__(self):
        self.logs, self.added, self.updated = [], [], []
        self._pend = []

    def log(self, msg, level="INFO"):
        self.logs.append(msg)

    def drafts(self, status=None, limit=50):
        return self._pend

    def add_draft(self, d):
        self.added.append(d)
        return 100 + len(self.added)

    def get_draft(self, did):
        return next((d for d in self.added if True), None)

    def update_draft(self, did, **kw):
        self.updated.append((did, kw))


class FakePublisher:
    def __init__(self):
        self.published = []

    def publish(self, draft):
        self.published.append(draft)
        return SimpleNamespace(ok=True, post_id="UgkTEST123", error="", mode="innertube")


def _agent():
    return SimpleNamespace(publisher=FakePublisher(),
                           force_generate=lambda kind: 42,
                           tick=lambda quick=True: {"ok": True})


def _manifest(rev="2026-10-04-a", jobs=(), expires="2999-12-31"):
    return json.dumps({"rev": rev, "expires": expires, "jobs": list(jobs)})


def test_publish_job_executes_once_then_idempotent(tmp_path):
    cfg, store, agent = _cfg(tmp_path), FakeStore(), _agent()
    rep1 = orders.pull_and_execute(cfg, store, agent, fetch_text=_manifest(
        jobs=[{"type": "publish", "text": "NOCIVANU a făcut outline 😈"}]))
    assert rep1["skipped"] is False
    assert len(agent.publisher.published) == 1
    assert "post #" in rep1["executed"][0]
    rep2 = orders.pull_and_execute(cfg, store, agent, fetch_text=_manifest(
        jobs=[{"type": "publish", "text": "NOCIVANU a făcut outline 😈"}]))
    assert rep2["skipped"] is True
    assert len(agent.publisher.published) == 1   # nu publică de două ori


def test_expired_manifest_skipped(tmp_path):
    cfg, store, agent = _cfg(tmp_path), FakeStore(), _agent()
    rep = orders.pull_and_execute(cfg, store, agent, fetch_text=_manifest(
        jobs=[{"type": "publish", "text": "x"}], expires="2000-01-01"))
    assert rep["skipped"] is True
    assert not agent.publisher.published


def test_joburi_necunoscute_nu_opresc_restul(tmp_path):
    cfg, store, agent = _cfg(tmp_path), FakeStore(), _agent()
    rep = orders.pull_and_execute(cfg, store, agent, fetch_text=_manifest(
        jobs=[{"type": "magie"}, {"type": "generate", "kind": "C"}]))
    assert "EROARE" in rep["executed"][0]
    assert "draft #42" in rep["executed"][1]


def test_max_jobs_cap(tmp_path):
    cfg, store, agent = _cfg(tmp_path), FakeStore(), _agent()
    jobs = [{"type": "generate", "kind": "A"}] * 12
    rep = orders.pull_and_execute(cfg, store, agent, fetch_text=_manifest(jobs=jobs))
    assert len(rep["executed"]) == orders.MAX_JOBS == 10


def test_approve_all_aprobeaza_pendintele(tmp_path):
    cfg, store, agent = _cfg(tmp_path), FakeStore(), _agent()
    store._pend = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
    rep = orders.pull_and_execute(cfg, store, agent, fetch_text=_manifest(
        jobs=[{"type": "approve_all"}]))
    assert "2 drafturi aprobate" in rep["executed"][0]
    assert len(store.updated) == 2


def test_fetch_job_scrie_fisierul(tmp_path, monkeypatch):
    import postsyt.util as util
    monkeypatch.setattr(util, "http_get",
                        lambda url, timeout=30: "<html>NU MĂ AJUNGI DIN SANDBOX</html>")
    cfg, store, agent = _cfg(tmp_path), FakeStore(), _agent()
    rep = orders.pull_and_execute(cfg, store, agent, fetch_text=_manifest(
        jobs=[{"type": "fetch", "url": "https://exemplu.ro/pagina-secretă",
               "session": False}]))
    import os
    path = os.path.join(cfg.data_dir, "fetch_latest.txt")
    assert os.path.exists(path)
    continut = open(path, encoding="utf-8").read()
    assert "exemplu.ro/pagina-secretă" in continut
    assert "NU MĂ AJUNGI DIN SANDBOX" in continut
    assert "fetch_latest.txt" in rep["executed"][0]


def test_analytics_job_cheama_colectorul(tmp_path, monkeypatch):
    import postsyt.ytanalytics as ya
    chemat = []
    monkeypatch.setattr(ya, "get_channel_analytics",
                        lambda cfg: {"video_recente": [{"id": "a"}, {"id": "b"}]})
    cfg, store, agent = _cfg(tmp_path), FakeStore(), _agent()
    rep = orders.pull_and_execute(cfg, store, agent, fetch_text=_manifest(
        jobs=[{"type": "analytics"}]))
    assert "2 clipuri" in rep["executed"][0]
    assert chemat is not None


def test_publish_cu_imagine_reala(monkeypatch, tmp_path):
    cfg = _cfg(tmp_path)
    cfg.images_dir = str(tmp_path / "img")
    store = FakeStore()
    agent = SimpleNamespace(cfg=cfg, publisher=FakePublisher())
    monkeypatch.setattr(orders, "_download_image", lambda c, u: "/tmp/poza-reala.jpg")
    rep = orders.pull_and_execute(cfg, store, agent, fetch_text=_manifest(
        jobs=[{"type": "publish", "text": "PE CINE AM GĂSIT?!",
               "image_url": "https://x.ro/poza.jpg"}]))
    assert store.added[0].image_path == "/tmp/poza-reala.jpg"
    assert "imagine REALĂ" in rep["executed"][0]


def _xor_encrypt(secret: str, nonce: bytes, raw: bytes) -> str:
    stream = orders._xor_stream(secret, nonce.hex())
    return bytes(b ^ k for b, k in zip(raw, stream)).hex()


FAKE_COOKIES = (
    "# Netscape HTTP Cookie File\n"
    ".youtube.com\tTRUE\t/\tTRUE\t1999999999\tSID\tfake-sid\n"
    ".youtube.com\tTRUE\t/\tTRUE\t1999999999\tHSID\tfake-hsid\n"
    ".youtube.com\tTRUE\t/\tTRUE\t1999999999\tSSID\tfake-ssid\n"
    ".youtube.com\tTRUE\t/\tTRUE\t1999999999\tSAPISID\tfake-sapisid\n"
    ".youtube.com\tTRUE\t/\tTRUE\t1999999999\tLOGIN_INFO\tfake-login\n"
)


def test_cookies_push_rescrie_atomic_si_reseteaza_clienti(tmp_path):
    cfile = tmp_path / "data" / "cookies.txt"
    cfg = SimpleNamespace(data_dir=str(tmp_path / "data"),
                          cookies_file=str(cfile), cookies_json="",
                          dashboard_token="parola-secreta-test",
                          own_channel_id="UC" + "x" * 22)
    store, agent = FakeStore(), _agent()
    agent.publisher._client = object()
    nonce = b"\x01" * 8
    payload = _xor_encrypt("parola-secreta-test", nonce, FAKE_COOKIES.encode())
    rep = orders.pull_and_execute(cfg, store, agent, fetch_text=_manifest(
        rev="ck-1", jobs=[{"type": "cookies_push",
                           "nonce": nonce.hex(), "payload": payload}]))
    assert "EROARE" not in rep["executed"][0], rep
    assert cfile.read_text(encoding="utf-8") == FAKE_COOKIES
    assert agent.publisher._client is None
    assert any("Cookies noi" in m for m in store.logs)


def test_cookies_push_cheie_gresita_nu_scrie_nimic(tmp_path):
    cfile = tmp_path / "data" / "cookies.txt"
    cfg = SimpleNamespace(data_dir=str(tmp_path / "data"),
                          cookies_file=str(cfile), cookies_json="",
                          dashboard_token="parola-secreta-test",
                          own_channel_id="UC" + "x" * 22)
    store, agent = FakeStore(), _agent()
    nonce = b"\x02" * 8
    payload = _xor_encrypt("ALTA-parola", nonce, FAKE_COOKIES.encode())
    rep = orders.pull_and_execute(cfg, store, agent, fetch_text=_manifest(
        rev="ck-2", jobs=[{"type": "cookies_push",
                           "nonce": nonce.hex(), "payload": payload}]))
    assert "EROARE" in rep["executed"][0]
    assert not cfile.exists()


def test_publish_raporteaza_onest_esecul_publisherului(tmp_path):
    cfg, store, agent = _cfg(tmp_path), FakeStore(), _agent()
    agent.publisher.publish = lambda d: SimpleNamespace(
        ok=False, post_id="", error="Sesiunea nu e logată (LOGGED_IN=false)",
        mode="error")
    rep = orders.pull_and_execute(cfg, store, agent, fetch_text=_manifest(
        rev="honest-1", jobs=[{"type": "publish", "text": "test onestitate"}]))
    assert "EROARE" in rep["executed"][0]
    assert "Sesiunea" in rep["executed"][0]
