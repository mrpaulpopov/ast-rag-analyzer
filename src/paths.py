from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

CONFIG_PATH = PROJECT_ROOT / "config.yaml"

CACHE_DIR = PROJECT_ROOT / "artifacts"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

AST_PATH = PROJECT_ROOT/ "artifacts/ast_test.json"
ALL_RAW_FUNCTIONS = PROJECT_ROOT / "artifacts/all_raw_functions.txt"



if __name__ == "__main__":
    print(PROJECT_ROOT) # debug