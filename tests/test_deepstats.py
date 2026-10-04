"""Teste deepstats — watch page, transcript XML, disecția clipului cu fake-uri."""
import json
import os

from postsyt.config import Config
from postsyt import deepstats as ds

PLAYER = {
    "videoDetails": {"title": "POKECITY Ep.1 NOUL SMP",
                     "shortDescription": "Episodul 1 cu pokemoni\nDiscord in descriere",
                     "keywords": ["minecraft", "pokecity", "pokemon"],
                     "lengthSeconds": "2153", "isLiveContent": False},
    "microformat": {"playerMicroformatRenderer": {
        "publishDate": "2026-09-01", "category": "Gaming", "likeCount": "123"}},
    "captions": {"playerCaptionsTracklistRenderer": {"captionTracks": [
        {"baseUrl": "https://captions.example/en", "languageCode": "en", "kind": "asr"},
        {"baseUrl": "https://captions.example/ro", "languageCode": "ro"},
    ]}},
}

PLAYER_FARA_CAPTIONS = {"videoDetails": {"title": "X", "shortDescription": "y",
                                         "lengthSeconds": "60"},
                        "microformat": {"playerMicroformatRenderer": {}}}

TRANSCRIPT_XML = ('<transcript><text start="0.0" dur="1.2">Salutare tuturor</text>'
                  '<text start="1.2" dur="2.0">si bine ati venit la</text>'
                  '<text start="3.2" dur="1.5">POKE CITY</text></transcript>')

WATCH_PAGE = ("<html><script>var ytInitialPlayerResponse = "
              + json.dumps(PLAYER) + ";</script></html>")


def _getter(url, headers=None, timeout=None):
    if "/watch?v=" in url:
        return WATCH_PAGE
    if "captions.example/ro" in url:
        return TRANSCRIPT_XML
    raise AssertionError(f"URL neașteptat: {url}")


class _FakeCommenter:
    def video_threads(self, vid, titlu="", max_pages=1):
        return [
            {"comment_id": "a", "autor": "@Ion", "text": "cand episodul 2?",
             "likes": 12, "owner_a_raspuns": False},
            {"comment_id": "b", "autor": "@Ana", "text": "cel mai bun smp",
             "likes": 30, "owner_a_raspuns": False},
        ]


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


class TestParsare:
    def test_player_details(self):
        d = ds.parse_player_details(PLAYER)
        assert d["titlu"].startswith("POKECITY")
        assert d["taguri"] == ["minecraft", "pokecity", "pokemon"]
        assert d["durata_secunde"] == 2153
        assert d["likes"] == 123
        assert d["publicat"] == "2026-09-01"
        assert d["este_live"] is False

    def test_transcript_prefera_ro_manual(self):
        tr = ds.get_transcript(PLAYER, getter=_getter)
        assert tr is not None
        assert tr["limba"] == "ro" and tr["automat"] is False
        assert tr["text"] == "Salutare tuturor si bine ati venit la POKE CITY"
        assert tr["caractere_totale"] == len("Salutare tuturor si bine ati venit la POKE CITY")

    def test_fara_captions(self):
        assert ds.get_transcript(PLAYER_FARA_CAPTIONS, getter=_getter) is None


class TestDepthScan:
    def test_disectie_completa(self, tmp_path):
        cfg = _cfg(tmp_path)
        rez = ds.depth_scan(cfg, [{"id": "v" * 11, "titlu": "EP1"}],
                            commenter=_FakeCommenter(), getter=_getter,
                            progres=lambda *a, **k: None)
        assert rez["total"] == 1 and rez["cu_transcript"] == 1
        v = rez["videoclipuri"][0]
        assert v["titlu"].startswith("POKECITY")
        assert v["transcript"]["limba"] == "ro"
        # top comentarii sortate desc după likes — Ana (30) înainte de Ion (12)
        assert v["top_comentarii"][0]["autor"] == "@Ana"
        assert v["top_comentarii"][1]["intrebare"] is True
        assert rez["intebari_in_top_comentarii"] == 1
        assert os.path.exists(rez["salvat_in"])
        saved = json.load(open(rez["salvat_in"], encoding="utf-8"))
        assert saved["videoclipuri"][0]["descriere"].startswith("Episodul 1")

    def test_clip_cazut_nu_opreste(self, tmp_path):
        cfg = _cfg(tmp_path)

        def getter_gr(url, headers=None, timeout=None):
            raise ConnectionError("pagina indisponibila")

        rez = ds.depth_scan(cfg, [{"id": "v" * 11, "titlu": "BAD"}],
                            commenter=_FakeCommenter(), getter=getter_gr,
                            progres=lambda *a, **k: None)
        assert rez["total"] == 1
        assert rez["erori"]  # eroarea e documentată, scanarea a supraviețuit

    def test_summary(self, tmp_path):
        cfg = _cfg(tmp_path)
        rez = ds.depth_scan(cfg, [{"id": "v" * 11, "titlu": "EP1"}],
                            commenter=_FakeCommenter(), getter=_getter,
                            progres=lambda *a, **k: None)
        txt = ds.format_summary(rez)
        assert "🔬 DEEP STATS" in txt and "POKECITY" in txt and "❓" in txt
