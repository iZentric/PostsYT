"""Teste comments — scan + reply, totul prin poster injectat, zero rețea."""
import json
import os

from postsyt import comments as cm
from postsyt.config import Config


def _thread(cid, autor, text, publicat, owner=False, owner_reply=False, with_params=True):
    cr = {"commentId": cid,
          "authorText": {"simpleText": autor},
          "contentText": {"runs": [{"text": text}]},
          "publishedTimeText": {"runs": [{"text": publicat}]},
          "likeCount": "7"}
    if owner:
        cr["authorIsChannelOwner"] = True
    thread: dict = {"comment": {"commentRenderer": cr}}
    if with_params:
        thread["actions"] = {"createCommentReplyEndpoint": {"createReplyParams": f"RP_{cid}"}}
    if owner_reply:
        thread["replies"] = {"commentRepliesRenderer": {"contents": [{
            "commentRenderer": {"commentId": cid + ".r", "authorIsChannelOwner": True,
                                "contentText": {"runs": [{"text": "mersi!"}]}}}]}}
    return {"commentThreadRenderer": thread}


NEXT_RESP = json.dumps({"engagementPanels": [
    {"engagementPanelSectionListRenderer": {
        "identifier": "engagement-panel-ads",
        "content": {"sectionListRenderer": {}}}},
    {"engagementPanelSectionListRenderer": {
        "identifier": "engagement-panel-comments-section",
        "content": {"sectionListRenderer": {"contents": [
            {"itemSectionRenderer": {"sectionIdentifier": "comment-item-section",
             "contents": [{"continuationItemRenderer": {"continuationEndpoint":
                {"continuationCommand": {"token": "TOK1"}}}}]}}]}}}},
]})

BROWSE_P1 = json.dumps({"onResponseReceivedEndpoints": [{"reloadContinuationItemsCommand": {
    "continuationItems": [
        _thread("c1", "@Andrei", "cel mai tare episod", "acum 2 zile"),
        _thread("c2", "@iSentric", "mulțumesc tuturor", "acum 2 zile", owner=True),
        _thread("c3", "@Maria", "când live?", "acum o săptămână", owner_reply=True),
        {"continuationItemRenderer": {"continuationEndpoint":
                                      {"continuationCommand": {"token": "TOK2"}}}},
    ]}}]})

BROWSE_P2 = json.dumps({"onResponseReceivedEndpoints": [{"appendContinuationItemsAction": {
    "continuationItems": [
        _thread("c4", "@VasileDino", "era bun canalul asta", "acum 3 ani"),
    ]}}]})


def _poster_factory(replies_sink: list):
    def poster(endpoint, body):
        if endpoint == "next":
            return NEXT_RESP
        if endpoint == "browse":
            return BROWSE_P1 if body.get("continuation") == "TOK1" else BROWSE_P2
        if endpoint == "comment/create_comment_reply":
            replies_sink.append((body.get("createReplyParams"), body.get("commentText")))
            return '{"actions": [{"createCommentReplyAction": {"commentId": "nou"}}]}'
        raise AssertionError(f"endpoint necunoscut: {endpoint}")
    return poster


def _bad_poster(endpoint, body):
    if endpoint == "comment/create_comment_reply":
        raise RuntimeError("HTTP 429: prea multe cereri")
    return _poster_factory([])(endpoint, body)


class FakeStore:
    def __init__(self):
        self.kv: dict = {}
        self.logs: list = []

    def get_kv(self, key, default=None):
        return self.kv.get(key, default)

    def set_kv(self, key, value):
        self.kv[key] = value

    def log(self, msg, level="INFO"):
        self.logs.append((level, msg))


def _cfg(tmp_path) -> Config:
    cookies = tmp_path / "cookies.txt"
    cookies.write_text(".youtube.com\tTRUE\t/\tTRUE\t1900000000\tSAPISID\tx\n",
                       encoding="utf-8")
    cfg = Config()
    cfg.own_handle = "@isentric1"
    cfg.cookies_file = str(cookies)
    cfg.cookies_json = str(tmp_path / "none.json")
    cfg.data_dir = str(tmp_path)
    return cfg


def _commenter(tmp_path, sink=None, store=None):
    sink = sink if sink is not None else []
    c = cm.Commenter(_cfg(tmp_path), store=store, log=lambda *a, **k: None,
                     sleeper=lambda s: None, poster=_poster_factory(sink))
    return c, sink


def _scan(c):
    return c.scan([{"id": "v" * 11, "titlu": "EPISOD TEST"}], max_pages=5)


class TestParsare:
    def test_token_sectiune(self):
        assert cm.comments_section_token(NEXT_RESP) == "TOK1"
        assert cm.comments_section_token("{}") == ""

    def test_threads_din_pagina(self):
        items = cm.extract_continuation_items(BROWSE_P1)
        threads = cm.parse_threads(items)
        assert len(threads) == 3
        t1 = [t for t in threads if t["comment_id"] == "c1"][0]
        assert t1["autor"] == "@Andrei"
        assert t1["reply_params"] == "RP_c1"
        assert t1["owner_a_raspuns"] is False
        t2 = [t for t in threads if t["comment_id"] == "c2"][0]
        assert t2["autor_e_owner"] is True
        t3 = [t for t in threads if t["comment_id"] == "c3"][0]
        assert t3["owner_a_raspuns"] is True

    def test_paginare_pana_la_capat(self, tmp_path):
        c, _ = _commenter(tmp_path)
        threads = c.video_threads("v" * 11, "EPISOD TEST", max_pages=5)
        ids = {t["comment_id"] for t in threads}
        assert ids == {"c1", "c2", "c3", "c4"}


class TestScan:
    def test_filtre_implicite(self, tmp_path):
        c, _ = _commenter(tmp_path)
        rez = _scan(c)
        ids = [t["comment_id"] for t in rez["threaduri_raspundibile"]]
        assert ids == ["c1"]            # c2=propriul, c3=deja răspuns, c4=prea vechi
        assert os.path.exists(rez["salvat_in"])

    def test_fara_filtru_zile(self, tmp_path):
        c, _ = _commenter(tmp_path)
        rez = c.scan([{"id": "v" * 11, "titlu": "X"}], zile=0)
        assert {t["comment_id"] for t in rez["threaduri_raspundibile"]} == {"c1", "c4"}

    def test_cu_raspuns_flag(self, tmp_path):
        c, _ = _commenter(tmp_path)
        rez = c.scan([{"id": "v" * 11, "titlu": "X"}], doar_fara_raspuns=False)
        assert {t["comment_id"] for t in rez["threaduri_raspundibile"]} == {"c1", "c3"}


class TestReply:
    def test_uscat_nu_posteaza(self, tmp_path):
        c, sink = _commenter(tmp_path)
        rez_scan = _scan(c)
        plan = {"raspunsuri": [{"comment_id": "c1", "text": "Multumesc frate! 🔥"}]}
        rez = c.apply_plan(plan, uscat=True)
        assert rez["postate"] == 0 and sink == []

    def test_posteaza_din_plan(self, tmp_path):
        store = FakeStore()
        c, sink = _commenter(tmp_path, store=store)
        _scan(c)
        plan = {"raspunsuri": [{"comment_id": "c1", "text": "Multumesc frate! 🔥"}]}
        rez = c.apply_plan(plan)
        assert rez["postate"] == 1
        assert sink == [("RP_c1", "Multumesc frate! 🔥")]
        zi = cm.utcnow().strftime("%Y-%m-%d")
        assert int(store.get_kv(f"replies_count_{zi}")) == 1

    def test_limita_zilnica(self, tmp_path):
        store = FakeStore()
        c, sink = _commenter(tmp_path, store=store)
        _scan(c)
        zi = cm.utcnow().strftime("%Y-%m-%d")
        store.set_kv(f"replies_count_{zi}", 40)
        rez = c.apply_plan({"raspunsuri": [{"comment_id": "c1", "text": "x"}]})
        assert rez["postate"] == 0 and sink == []

    def test_id_necunoscut_sarit(self, tmp_path):
        c, _ = _commenter(tmp_path)
        _scan(c)
        rez = c.apply_plan({"raspunsuri": [{"comment_id": "fantoma", "text": "??"}]})
        assert rez["sarite"] == 1 and rez["erori"]

    def test_oprire_la_erori_in_serie(self, tmp_path):
        c = cm.Commenter(_cfg(tmp_path), store=FakeStore(), log=lambda *a, **k: None,
                         sleeper=lambda s: None, poster=_bad_poster)
        c.scan([{"id": "v" * 11, "titlu": "X"}])
        plan = {"raspunsuri": [{"comment_id": "c1", "text": "1"},
                               {"comment_id": "c1", "text": "2"}]}
        rez = c.apply_plan(plan, max_erori_serie=1)
        assert rez["postate"] == 0
        assert len(rez["erori"]) == 1  # s-a oprit după prima eroare
