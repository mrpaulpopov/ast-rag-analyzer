from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

CONFIG_PATH = PROJECT_ROOT / "config.yaml"

CACHE_DIR = PROJECT_ROOT / "artifacts"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

AST_PATH = PROJECT_ROOT/ "artifacts/ast_functions.json"
ALL_RAW_FUNCTIONS = PROJECT_ROOT / "artifacts/raw_functions.json"
ALL_PROC_FUNCTIONS = PROJECT_ROOT / "artifacts/proc_functions.json"
RAG_DATABASE = PROJECT_ROOT / "artifacts/ready_for_rag.json"

IGNORED_DIRS = {'.venv', '__pycache__'}

if __name__ == "__main__":
    print(PROJECT_ROOT) # debug