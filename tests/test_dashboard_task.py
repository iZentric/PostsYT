from types import SimpleNamespace

import pytest
from postsyt.dashboard import run_task


class FakeStore:
    def __init__(self):
        self._pend = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
        self._drafts = {1: SimpleNamespace(id=1, text="a"), 2: SimpleNamespace(id=2, text="b")}
        self.updated, self.logs = [], []

    def drafts(self, status=None, limit=50):
        return self._pend if status == "draft" else ([] if status == "approved" else [])

    def get_draft(self, did):
        return self._drafts.get(did)

    def update_draft(self, did, **kw):
        self.updated.append((did, kw))

    def log(self, m, level="INFO"):
        self.logs.append(m)


def _agent():
    return SimpleNamespace(publisher=SimpleNamespace(published=[], publish=lambda d: None),
                           tick=lambda quick=True: {"ok": 1},
                           force_generate=lambda k: 7)


def test_status_raporteaza_numerele():
    rez = run_task(None, FakeStore(), _agent(), "status", {})
    assert "drafturi în așteptare: 2" in rez
    assert "op=analytics" in rez  # mini-ajutor inclus


def test_approve_all_si_publish_pe_id():
    store = FakeStore()
    pub = []
    agent = _agent()
    agent.publisher.publish = pub.append
    rez = run_task(None, store, agent, "approve_all", {})
    assert rez.startswith("2 drafturi aprobate")
    assert len(store.updated) == 2
    rez2 = run_task(None, store, agent, "publish", {"id": "1"})
    assert "post #1 zburat" in rez2
    assert len(pub) == 1


def test_publish_id_inexistent_nu_crapa_ci_raporteaza():
    rez = run_task(None, FakeStore(), _agent(), "publish", {"id": "99"})
    assert "inexistent" in rez


def test_op_necunoscut_ridica_clar():
    with pytest.raises(ValueError, match="op necunoscut"):
        run_task(None, FakeStore(), _agent(), "magie", {})


import json as _json
import os as _os
import postsyt.dashboard as dash


class _Store2(FakeStore):
    def __init__(self):
        super().__init__()
        self.added = []

    def add_draft(self, d):
        self.added.append(d)
        return 900 + len(self.added)

    def get_draft(self, did):
        return next((d for d in self.added if True), None)


class _Pub:
    def __init__(self):
        self.published = []

    def publish(self, d):
        self.published.append(d)
        return SimpleNamespace(ok=True, post_id="UgkXYZ", error="", mode="innertube")


def _cfg(tmp_path):
    return SimpleNamespace(data_dir=str(tmp_path / "data"),
                           cookies_file="data/cookies.txt",
                           cookies_json="data/cookies.json",
                           own_channel_id="UC" + "x" * 22)


def test_agent_action_publish_foloseste_motorul_ordinelor(tmp_path):
    cfg, store = _cfg(tmp_path), _Store2()
    agent = SimpleNamespace(publisher=_Pub(), cfg=cfg)
    rez = dash.agent_action(cfg, store, agent, "publish",
                            {"text": "CAT IN THE HAT pe PokeCity?! 🐱",
                             "poll_options": ["DA", "NU"]})
    assert rez["ok"] and "post #" in rez["detail"] and "sondaj" in rez["detail"]
    assert len(agent.publisher.published) == 1


def test_agent_action_publish_este_onest_la_esec(tmp_path):
    cfg, store = _cfg(tmp_path), _Store2()
    pub = _Pub()
    pub.publish = lambda d: SimpleNamespace(ok=False, post_id="",
                                            error="Sesiunea nu e logată", mode="error")
    agent = SimpleNamespace(publisher=pub, cfg=cfg)
    try:
        dash.agent_action(cfg, store, agent, "publish", {"text": "x"})
        assert False, "trebuia să ridice"
    except RuntimeError as e:
        assert "Sesiunea" in str(e)


def test_agent_action_comments_scan_si_reply(tmp_path, monkeypatch):
    cfg, store = _cfg(tmp_path), _Store2()
    agent = SimpleNamespace(publisher=_Pub(), cfg=cfg)
    _os.makedirs(cfg.data_dir)
    with open(_os.path.join(cfg.data_dir, "comments.json"), "w", encoding="utf-8") as f:
        f.write("[{\"autor\": \"Vianu\", \"text\": \"goooood\"}]")

    import postsyt.cli as cli
    import postsyt.comments as comments
    monkeypatch.setattr(cli, "_videoclipuri_pentru_scan",
                        lambda c, n: [{"id": "abc", "titlu": "t"}])

    class FakeCommenter:
        def __init__(self, c, store=None): pass

        def scan(self, vids, zile=30, max_pages=3, doar_fara_raspuns=True):
            return {"total": 2, "erori": [], "salvat_in": "comments.json"}

        def apply_plan(self, plan, limita_zilnica=15, uscat=False):
            return {"postate": 3, "sarite": 1, "erori": []}

    monkeypatch.setattr(comments, "Commenter", FakeCommenter)
    scan = dash.agent_action(cfg, store, agent, "comments_scan",
                             {"zile": 60, "max_videos": 5})
    assert "2 de răspuns" in scan["detail"] and "Vianu" in scan["continut"]
    rep = dash.agent_action(cfg, store, agent, "comment_reply",
                            {"plan": {"abc": {"y": "bravo frate"}}, "limita": 5})
    assert "postate 3" in rep["detail"]


def test_agent_action_necunoscut_ridica():
    try:
        dash.agent_action(None, None, None, "hackeraș", {})
        assert False
    except ValueError as e:
        assert "hackeraș" in str(e)
