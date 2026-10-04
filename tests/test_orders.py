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
