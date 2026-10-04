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
