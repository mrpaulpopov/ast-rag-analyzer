import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

CACHE_DIR = PROJECT_ROOT / "artifacts"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

META_DATA_PATH = CACHE_DIR / "meta_data.json"
CONFIG_PATH = PROJECT_ROOT / "config.yaml"
PROMPT_PATH = CACHE_DIR / "inference_prompt.txt"

AST_FUNCTIONS_PATH = CACHE_DIR / "functions_ast.json"
RAW_FUNCTIONS_PATH = CACHE_DIR / "functions_raw.json"
DESCRIBED_FUNCTIONS_PATH = CACHE_DIR / "functions_described.json"
RAG_FUNCTIONS_PATH = CACHE_DIR / "functions_rag.json"

AST_FUNCTIONS_UPD_PATH = CACHE_DIR / "functions_ast_upd.json"
RAW_FUNCTIONS_UPD_PATH = CACHE_DIR / "functions_raw_upd.json"
DESCRIBED_FUNCTIONS_UPD_PATH = CACHE_DIR / "functions_described_upd.json"
RAG_FUNCTIONS_UPD_PATH = CACHE_DIR / "functions_rag_upd.json"

DB_PARAMS = {
    "dbname": os.getenv("POSTGRES_DB"),
    "user": os.getenv("POSTGRES_USER"),
    "password": os.getenv("POSTGRES_PASSWORD"),
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": os.getenv("POSTGRES_PORT", "5432")
}


if __name__ == "__main__":
    print(PROJECT_ROOT) # debug