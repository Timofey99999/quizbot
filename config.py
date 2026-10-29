import os
import re
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


@dataclass(frozen=True)
class Config:
    token: str
    owners: frozenset[int]
    db_path: Path


def load_config() -> Config:
    load_env(BASE_DIR / ".env")

    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("BOT_TOKEN не задан. Скопируй .env.example в .env и впиши туда токен от @BotFather.")

    owners = frozenset(int(x) for x in re.findall(r"\d+", os.getenv("ADMIN_IDS", "")))
    if not owners:
        print("ADMIN_IDS пуст — админ-панель будет недоступна никому. Узнать свой ID можно командой /id.")

    db_path = Path(os.getenv("DB_PATH") or BASE_DIR / "data" / "quiz.db")
    return Config(token=token, owners=owners, db_path=db_path)
