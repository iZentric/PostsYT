"""Încărcare configurație (JSON stdlib; YAML dacă pyyaml e instalat)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"


@dataclass
class Config:
    # Canalul propriu
    own_channel_id: str = "UCBoZcTLayAUgYTPsyrStiLg"
    own_handle: str = "@isentric1"
    channel_name: str = "iSentric"
    niche: str = "Minecraft / PokeCity (Pokémoni în Minecraft), gaming funny RO"
    collab_names: list = field(default_factory=lambda: ["Nocivanu"])

    # Competitori urmăriți (feeduri video + postări community)
    competitors: list = field(default_factory=list)

    # Templarul de program (copiem ritmul lui)
    mirror_channel: str = "@JocuriHorrorSky"
    mirror_delay_minutes: int = 45        # postăm la ~45 min după el
    watch_gaming_trending: bool = True

    # Program & limite (sesizate din research: 1-3/zi max, nu spam)
    max_posts_per_day: int = 3
    min_gap_minutes: int = 90
    quiet_hours: list = field(default_factory=lambda: [0, 8])  # între 00:00-08:00 nu postăm
    poll_hours: list = field(default_factory=lambda: [19])      # sondajul zilnic, ~19:00 RO
    meme_hours: list = field(default_factory=lambda: [16])      # meme/relax
    daytime_slots: list = field(default_factory=lambda: [12, 16, 19, 21])
    live_days: list = field(default_factory=lambda: ["marți", "joi", "sâmbătă"])
    live_hour: int = 18

    # LLM (OpenAI-compatibil: OpenAI, Groq, OpenRouter, Ollama)
    llm_enabled: bool = False
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_api_key_env: str = "OPENAI_API_KEY"
    llm_max_chars: int = 900

    # Publicare
    publish_driver: str = "innertube"     # innertube | queue (doar coadă manuală)
    autopublish: bool = False             # implicit: ceri aprobare în dashboard
    experimental_innertube_polls: bool = False
    cookies_file: str = "data/cookies.txt"     # export Netscape (EditThisCookie/Cookie-Editor)
    cookies_json: str = "data/cookies.json"    # alternativ: [{name,value,domain}]

    # Intervale scanare (minute)
    feed_check_minutes: int = 15
    mirror_check_minutes: int = 20
    trend_check_hours: int = 6

    # Diverse
    timezone: str = "Europe/Bucharest"
    data_dir: str = str(DATA_DIR)
    db_path: str = str(DATA_DIR / "postsyt.db")
    images_dir: str = str(DATA_DIR / "images")
    dashboard_port: int = 8787

    @staticmethod
    def default() -> "Config":
        return Config()


def _apply(cfg: Config, data: dict) -> Config:
    valid = {f for f in Config.__dataclass_fields__}
    for k, v in data.items():
        if k in valid:
            setattr(cfg, k, v)
    return cfg


def load_config(path: str | None = None) -> Config:
    """Prioritate: argument explicit > config.yaml > config.json > default."""
    cfg = Config()
    candidates = [path] if path else [
        str(ROOT / "config.yaml"), str(ROOT / "config.json"),
    ]
    for cand in candidates:
        if not cand or not os.path.exists(cand):
            continue
        raw = open(cand, encoding="utf-8").read()
        if cand.endswith((".yaml", ".yml")):
            try:
                import yaml  # type: ignore
                _apply(cfg, yaml.safe_load(raw) or {})
            except ImportError:
                raise RuntimeError("Instalează pyyaml sau folosește config.json")
        else:
            _apply(cfg, json.loads(raw))
        break
    cfg.db_path = os.path.expanduser(cfg.db_path)
    cfg.images_dir = os.path.expanduser(cfg.images_dir)
    os.makedirs(cfg.data_dir, exist_ok=True)
    os.makedirs(cfg.images_dir, exist_ok=True)
    return cfg


def default_config_json() -> str:
    return json.dumps(Config().__dict__, indent=2, ensure_ascii=False)
