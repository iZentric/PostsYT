"""Teste uploader — fluxul Studio complet, fără rețea (transport injectat)."""
import json
import os

import pytest

from postsyt.config import Config
from postsyt import uploader


def _cfg(tmp_path, size=12) -> tuple:
    cookies = tmp_path / "cookies.txt"
    cookies.write_text(
        ".youtube.com\tTRUE\t/\tTRUE\t1900000000\tSAPISID\tfakesapisid123\n", encoding="utf-8")
    video = tmp_path / "episod nou.mp4"
    video.write_bytes(bytes(range(256))[:size] * (size // size or 1) * size)
    cfg = Config()
    cfg.cookies_file = str(cookies)
    cfg.cookies_json = str(tmp_path / "nope.json")
    cfg.data_dir = str(tmp_path)
    return cfg, str(video)


def _silent(*a, **k):
    pass


class TestValidari:
    def test_fisier_lipsa(self, tmp_path):
        cfg, _ = _cfg(tmp_path)
        res = uploader.upload_video(cfg, str(tmp_path / "nu-am.mp4"),
                                    transport=_silent, log=_silent)
        assert res["ok"] is False and res["etapa"] == "validare"
        assert "nu există" in res["eroare"]

    def test_privacy_invalid(self, tmp_path):
        cfg, video = _cfg(tmp_path)
        res = uploader.upload_video(cfg, video, privacy="secret",
                                    transport=_silent, log=_silent)
        assert res["ok"] is False
        assert "privacy" in res["eroare"]

    def test_titlu_default_din_fisier(self, tmp_path):
        cfg, video = _cfg(tmp_path)

        def transport(method, url, headers, body):
            if method == "POST":
                payload = json.loads(body.decode())
                assert payload["initialMetadata"]["title"] == "episod nou"
                return 200, {"X-Goog-Upload-URL": "https://u.example/s/1"}, "{}"
            return 200, {}, '{"videoId": "' + "x" * 11 + '"}'

        res = uploader.upload_video(cfg, video, transport=transport, log=_silent)
        assert res["ok"] is True


class TestFluxComplet:
    def test_upload_chunked(self, tmp_path, monkeypatch):
        cfg, video = _cfg(tmp_path)
        size = os.path.getsize(video)
        monkeypatch.setattr(uploader, "CHUNK_SIZE", 10)  # forțăm mai multe bucăți

        calls = []

        def transport(method, url, headers, body):
            calls.append((method, headers.get("X-Goog-Upload-Command"),
                          headers.get("X-Goog-Upload-Offset"), len(body)))
            if method == "POST":
                assert headers["X-Goog-Upload-Command"] == "start"
                assert headers["X-Goog-Upload-Header-Content-Length"] == str(size)
                assert "SAPISIDHASH" in headers["Authorization"]
                payload = json.loads(body.decode())
                assert payload["initialMetadata"]["privacy"] == "UNLISTED"
                return 200, {"X-Goog-Upload-URL": "https://u.example/ses/9"}, \
                    '{"status": "uploadStarted"}'
            # PUT: intermediarele 308 (Resume Incomplete), ultima 200 cu videoId
            if "finalize" in headers["X-Goog-Upload-Command"]:
                return 200, {}, '{"videoId": "abc123XYZ-_"}'
            return 308, {"Range": "bytes=0-9"}, ""

        res = uploader.upload_video(cfg, video, title="TEST UP", privacy="unlisted",
                                    transport=transport, log=_silent)
        assert res["ok"] is True
        assert res["video_id"] == "abc123XYZ-_"
        assert res["url"] == "https://youtu.be/abc123XYZ-_"
        # verificăm succesiunea: start, apoi bucăți cu offset crescător, finalize la final
        puts = [c for c in calls if c[0] == "PUT"]
        assert puts[0][2] == "0"
        assert "finalize" in puts[-1][1]
        total_trimis = sum(c[3] for c in puts)
        assert total_trimis == size
        assert os.path.exists(res["debug_path"])

    def test_start_respins(self, tmp_path):
        cfg, video = _cfg(tmp_path)

        def transport(method, url, headers, body):
            return 403, {}, '{"error": {"message": "forbidden"}}'

        res = uploader.upload_video(cfg, video, transport=transport, log=_silent)
        assert res["ok"] is False and res["etapa"] == "start"
        assert "403" in res["eroare"]

    def test_fara_video_id_dar_ok(self, tmp_path):
        cfg, video = _cfg(tmp_path)

        def transport(method, url, headers, body):
            if method == "POST":
                return 200, {"X-Goog-Upload-URL": "https://u.example/s/2"}, "{}"
            return 200, {}, '{"status": "STATUS_VIDEO_PROCESSING"}'

        res = uploader.upload_video(cfg, video, transport=transport, log=_silent)
        assert res["ok"] is True
        assert res["video_id"] == ""
        assert "Studio" in res["eroare"]  # mesajul "apare în Studio→Conținut"

    def test_chunk_esuat(self, tmp_path, monkeypatch):
        cfg, video = _cfg(tmp_path)
        monkeypatch.setattr(uploader, "CHUNK_SIZE", 5)

        def transport(method, url, headers, body):
            if method == "POST":
                return 200, {"X-Goog-Upload-URL": "https://u.example/s/3"}, "{}"
            return 500, {}, "boom"

        res = uploader.upload_video(cfg, video, transport=transport, log=_silent)
        assert res["ok"] is False and res["etapa"] == "bucăți"
        assert "500" in res["eroare"]


class TestHelpers:
    def test_extract_video_id(self):
        assert uploader.extract_video_id('{"videoId": "a1B2c3D4e5F"}') == "a1B2c3D4e5F"
        assert uploader.extract_video_id('{"encryptedVideoId": "a1B2c3D4e5F"}') == "a1B2c3D4e5F"
        assert uploader.extract_video_id('{"status": "processing"}') is None

    def test_header_ci(self):
        assert uploader._h({"x-goog-upload-URL": "u"}, "X-Goog-Upload-Url") == "u"
        assert uploader._h({}, "X-Nope") == ""
