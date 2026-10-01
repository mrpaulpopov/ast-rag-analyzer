from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

CONFIG_PATH = PROJECT_ROOT / "config.yaml"

CACHE_DIR = PROJECT_ROOT / "artifacts"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

AST_FUNCTIONS_PATH = CACHE_DIR / "functions_ast.json"
RAW_FUNCTIONS_PATH = CACHE_DIR / "functions_raw.json"
DESCRIBED_FUNCTIONS_PATH = CACHE_DIR / "functions_described.json"
FUNCTIONS_RAG_PATH = CACHE_DIR / "functions_rag.json"


if __name__ == "__main__":
    print(PROJECT_ROOT) # debug