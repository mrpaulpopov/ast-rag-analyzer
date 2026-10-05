import json
import logging
import os
import time
from collections.abc import Iterator

from dotenv import load_dotenv

from src.paths import META_DATA_PATH

logger = logging.getLogger(__name__)

load_dotenv()
IGNORED_DIRS = {'.venv', '__pycache__', '.idea'}


def iter_python_files(target_dir: str, ignored_dirs: set[str] | None = None) -> Iterator[str]:
    ignored = ignored_dirs or set()  # protection of None
    for root, dirs, files in os.walk(target_dir):
        dirs[:] = [d for d in dirs if d not in ignored]

        for file in files:
            if file.endswith('.py') and not file.startswith('_'):
                yield os.path.join(root, file)


def iter_modified_files(target_dir: str, since_ts: float, ignored_dirs: set[str] | None = None) -> Iterator[str]:
    for file_path in iter_python_files(target_dir, ignored_dirs):
        if os.path.getmtime(file_path) > since_ts:
            yield file_path


def load_last_run_ts() -> float:
    """
    Bulletproof reading from json file
    """
    try:
        data = json.loads(META_DATA_PATH.read_text(encoding="utf-8"))
        return data.get("last_run_ts", 0.0)
    except (FileNotFoundError, json.JSONDecodeError):
        return 0.0

def save_last_run() -> None:
    META_DATA_PATH.write_text(json.dumps({"last_run_ts": time.time()}), encoding="utf-8")


def get_changed_files():
    target_dir = "/app/data" # docker-relative folder

    last_run_ts = load_last_run_ts()

    for path in iter_modified_files(target_dir, last_run_ts, IGNORED_DIRS):
        logger.info(f"{path} was changed.")

    return list(iter_modified_files(target_dir, last_run_ts, IGNORED_DIRS))


def read_file_safely(file_path: str) -> str:
    """Пробует прочитать файл в разных кодировках. Если не выходит — заменяет битые символы."""
    encodings = ['utf-8', 'windows-1251', 'latin-1']

    for enc in encodings:
        try:
            with open(file_path, 'r', encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue

    # Если ни одна кодировка не подошла, читаем принудительно, заменяя битые символы на "?"
    # Для построения AST-дерева битые буквы в комментариях или строках не имеют значения
    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
        return f.read()