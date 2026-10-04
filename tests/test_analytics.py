"""Teste ytanalytics — 100% offline, getter/poster injectați cu pagini fix."""
import json
import os

from postsyt.config import Config
from postsyt import ytanalytics as ya

HANDLE = "@isentric1"


def _page(data: dict) -> str:
    return f"<html><body><script>var ytInitialData = {json.dumps(data)};</script></body></html>"


def _vid(vid, title, views, published="acum 2 zile", dur="35:53"):
    return {"content": {"videoRenderer": {
        "videoId": vid,
        "title": {"runs": [{"text": title}]},
        "viewCountText": {"simpleText": views},
        "publishedTimeText": {"simpleText": published},
        "lengthText": {"simpleText": dur}}}}


VIDEOS_PAGE = {
    "header": {"subscriberCountText": {"simpleText": "4,02 K de abonați"},
               "videosCountText": {"runs": [{"text": "812"}]}},
    "grid": {"items": [
        _vid("a" * 11, "POKECITY Ep.1 NOUL SMP", "822 de vizualizări", "acum o lună"),
        _vid("b" * 11, "L-am PRINS pe PIKACHU", "444 de vizualizări", "acum 3 săptămâni", "18:04"),
        # duplicat intenționat — trebuie ignorat
        _vid("a" * 11, "POKECITY Ep.1 NOUL SMP", "822 de vizualizări", "acum o lună"),
    ]},
}

VIDEOS_PAGE_LAYOUT_NOU = {"header": {"pageHeaderRenderer": {"content": {
    "pageHeaderViewModel": {"metadata": {"contentMetadataViewModel": {
        "metadataRows": [{"metadataParts": [
            {"text": {"content": "@isentric1"}},
            {"text": {"content": "4,02 K de abonați"}},
            {"text": {"content": "812 videoclipuri"}},
        ]}]}}}}}}}

ABOUT_PAGE_LAYOUT_NOU = {"about": {"aboutChannelRenderer": {"metadata": {
    "aboutChannelViewModel": {
        "description": "Salut! Eu sunt iZentric",
        "joinedDate": {"content": "S-a înscris la 3 oct. 2020"},
        "viewCount": {"content": "1.234.567 de vizualizări"},
    }}}}}

SHORTS_PAGE = {"shorts": {"lockups": [
    {"shortsLockupViewModel": {
        "entityId": "shorts-shelf-item-" + "c" * 11 + "-0",
        "overlayMetadata": {"primaryText": {"content": "POKEMONUL S-A TRANSFORMAT?!"},
                            "secondaryText": {"content": "6,4 mii de vizualizări"}}}},
    {"shortsLockupViewModel": {
        "entityId": "shorts-shelf-item-" + "d" * 11 + "-0",
        "overlayMetadata": {"primaryText": {"content": "AM PRINS UN LEU"},
                            "secondaryText": {"content": "4,2 mii de vizualizări"}}}},
]}}

ABOUT_PAGE = {"about": {"channelAboutFullMetadataRenderer": {
    "viewCountText": {"simpleText": "1.234.567 de vizualizări"},
    "joinedDateText": {"simpleText": "S-a înscris la 3 oct. 2020"},
    "description": {"simpleText": "Salut! Eu sunt iZentric"}}}}

STUDIO_HOME = ('<html><script>ytcfg.set({"INNERTUBE_API_KEY":"AIzaTEST",'
               '"INNERTUBE_CLIENT_VERSION":"1.20990101.01.00"});</script></html>')

STUDIO_CARDS = json.dumps({"cards": [{"data": {
    "columns": [{"metric": "VIEWS"}, {"metric": "ESTIMATED_WATCH_TIME"},
                {"metric": "SUBSCRIBERS_NET_CHANGE"}],
    "rows": [{"values": [{"doubleValue": 12345.0}, {"doubleValue": 567.0},
                         {"doubleValue": 42.0}]}]}}]})


def _cfg(tmp_path) -> Config:
    cookies = tmp_path / "cookies.txt"
    cookies.write_text(
        ".youtube.com\tTRUE\t/\tTRUE\t1900000000\tSAPISID\tfakesapisid123\n", encoding="utf-8")
    cfg = Config()
    cfg.own_handle = HANDLE
    cfg.cookies_file = str(cookies)
    cfg.cookies_json = str(tmp_path / "nu-exista.json")
    cfg.data_dir = str(tmp_path)
    return cfg


def _getter_factory(studio_page=STUDIO_HOME):
    def getter(url, headers=None, timeout=None):
        if url.startswith(ya.STUDIO_ORIGIN):
            return studio_page
        if url.endswith("/videos"):
            return _page(VIDEOS_PAGE)
        if url.endswith("/shorts"):
            return _page(SHORTS_PAGE)
        if url.endswith("/about"):
            return _page(ABOUT_PAGE)
        raise AssertionError(f"URL neașteptat: {url}")
    return getter


def _poster(url, body=None, headers=None, timeout=None):
    assert "get_creator_analytics" in url
    return STUDIO_CARDS, {}


class TestParseCount:
    def test_sufixe(self):
        assert ya.parse_count_text("1.2K") == 1200
        assert ya.parse_count_text("1,2 K") == 1200
        assert ya.parse_count_text("6,4 mii de vizualizări") == 6400
        assert ya.parse_count_text("2 milioane de abonați") == 2_000_000
        assert ya.parse_count_text("3 miliarde") == 3_000_000_000

    def test_numere_mari_fara_sufix(self):
        assert ya.parse_count_text("4,142") == 4142
        assert ya.parse_count_text("1.234.567 de vizualizări") == 1234567
        assert ya.parse_count_text("876") == 876
        assert ya.parse_count_text("") is None
        assert ya.parse_count_text("fara cifre") is None


class TestParsere:
    def test_videos_dedup_si_tip(self):
        vids = ya.parse_videos(VIDEOS_PAGE)
        assert len(vids) == 2
        assert vids[0]["titlu"].startswith("POKECITY")
        assert vids[0]["vizionari"] == 822
        assert vids[0]["tip"] == "video"
        assert vids[0]["durata"] == "35:53"

    def test_shorts(self):
        shorts = ya.parse_shorts(SHORTS_PAGE)
        assert len(shorts) == 2
        assert shorts[0]["id"] == "c" * 11
        assert shorts[0]["vizionari"] == 6400
        assert all(s["tip"] == "short" for s in shorts)

    def test_header_si_about(self):
        hdr = ya.parse_channel_header(VIDEOS_PAGE)
        assert hdr["abonati"] == 4020
        about = ya.parse_about(ABOUT_PAGE)
        assert about["vizualizari_totale"] == 1234567

    def test_header_layout_nou_metadata(self):
        hdr = ya.parse_channel_header(VIDEOS_PAGE_LAYOUT_NOU)
        assert hdr["abonati"] == 4020
        assert "abon" in hdr["abonati_txt"].lower()
        assert "812" in hdr["videoclipuri_txt"]

    def test_about_layout_nou(self):
        about = ya.parse_about(ABOUT_PAGE_LAYOUT_NOU)
        assert about["vizualizari_totale"] == 1234567


class TestStudioCards:
    def test_parseaza_metrici(self):
        m = ya._parse_studio_cards(STUDIO_CARDS)
        assert m["VIEWS"] == 12345.0
        assert m["SUBSCRIBERS_NET_CHANGE"] == 42.0

    def test_json_rau(self):
        assert ya._parse_studio_cards("not json") == {}
        assert ya._parse_studio_cards('{"altceva": 1}') == {}


class TestEndToEnd:
    def test_pachet_complet(self, tmp_path):
        cfg = _cfg(tmp_path)
        res = ya.get_channel_analytics(cfg, getter=_getter_factory(), poster=_poster)
        assert res["canal"]["abonati"] == 4020
        assert res["canal"]["vizualizari_totale"] == 1234567
        tips = {v["tip"] for v in res["video_recente"]}
        assert tips == {"video", "short"}
        assert len(res["video_recente"]) == 4
        s = res["studio_28zile"]
        assert s["vizualizari"] == 12345.0 and s["abonati_noi"] == 42.0
        assert "studio" in res["surse"]
        assert os.path.exists(os.path.join(str(tmp_path), "analytics_latest.json"))

    def test_studio_picat_nu_omoara_restul(self, tmp_path):
        cfg = _cfg(tmp_path)

        def poster_rau(url, body=None, headers=None, timeout=None):
            raise ConnectionError("studio oprit")

        res = ya.get_channel_analytics(cfg, getter=_getter_factory(), poster=poster_rau)
        assert res["studio_28zile"] is None
        assert any("studio_28zile" in e or "Studio" in e for e in res["erori"])
        assert len(res["video_recente"]) == 4  # datele publice rămân

    def test_summary_se_randareza(self, tmp_path):
        cfg = _cfg(tmp_path)
        res = ya.get_channel_analytics(cfg, getter=_getter_factory(), poster=_poster)
        txt = ya.format_summary(res)
        assert "📊 ANALYTICS @isentric1" in txt
        assert "POKEMONUL S-A TRANSFORMAT" in txt
        assert "12.345" in txt
