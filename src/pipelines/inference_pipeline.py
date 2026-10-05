import ast
import asyncio
import logging
import os
import textwrap

import psycopg2
from ollama import AsyncClient

from src.ast_parser import extract_ast_code_structure
from src.filesystem_utils import iter_python_files

logger = logging.getLogger(__name__)

OLLAMA_HOST = os.getenv('OLLAMA_HOST')
VECTOR_MODEL = os.getenv('VECTOR_MODEL')
ANALYSIS_MODEL = os.getenv('ANALYSIS_MODEL')
TARGET_DIR = os.getenv('TARGET_DIR')

DB_PARAMS = {
    "dbname": os.getenv('POSTGRES_DB'),
    "user": os.getenv('POSTGRES_USER'),
    "password": os.getenv('POSTGRES_PASSWORD'),
    "host": os.getenv('POSTGRES_HOST'),
    "port": os.getenv('POSTGRES_PORT')
}




def extract_functions_from_file(abs_path: str, rel_path: str, target_dir: str) -> dict:
    """Возвращает {'file::func': 'код функции'}, используя правильный относительный путь."""
    with open(abs_path, "r", encoding="utf-8") as f:
        source = f.read()

    try:
        _, raw_functions = extract_ast_code_structure(source, rel_path, target_dir)
    except SyntaxError as e:
        logger.warning(f"Error in {rel_path}: {e}")
        return {}

    return raw_functions


def find_called_functions_in_code(code: str) -> list[str]:
    """Возвращает имена функций, которые вызываются внутри кода."""
    try:
        tree = ast.parse(textwrap.dedent(code))
    except SyntaxError:
        return []

    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):         # foo()
                names.append(node.func.id)
            elif isinstance(node.func, ast.Attribute):  # self.foo()
                names.append(node.func.attr)
    return names


async def get_db_dependencies(client, cursor, code: str) -> list[tuple]:
    """Ищет похожие функции в PostgreSQL. Возвращает [('file::func', code)]."""
    response = await client.embeddings(model=VECTOR_MODEL, prompt=code)

    cursor.execute(
        """
        SELECT file_path, func_name, raw_code
        FROM code_knowledge_base
        ORDER BY embedding <=> %s::vector
        LIMIT 5
        """,
        (str(response["embedding"]),),
    )
    return [(f"{file_path}::{func_name}", raw_code)
            for file_path, func_name, raw_code in cursor.fetchall()]


async def analyze_single_function(client, cursor, target_key: str, target_code: str, batch_changes: dict) -> str:
    """Один запрос к LLM: функция + контекст проекта + контекст других новых функций."""
    project_context = await get_project_context(client, cursor, target_code, batch_changes)
    batch_context = get_batch_context(target_key, target_code, batch_changes)

    prompt = f"""You are a strict automated AI code reviewer.
A developer modified the function `{target_key}`.

[TARGET FUNCTION CODE]
```python
{target_code}
```

[EXISTING RELATED FUNCTIONS FROM REPO]
{project_context}

[OTHER MODIFIED FUNCTIONS IN THIS COMMIT] (assume they are correct)
{batch_context}

TASK: Analyze if the target function will break the system or introduce bugs,
considering both the existing functions and the other modified functions.
Output format:
STATUS: PASS or FAIL
ISSUE: brief explanation"""

    response = await client.generate(model=ANALYSIS_MODEL, prompt=prompt)
    return response["response"]


async def get_project_context(client, cursor, target_code: str, batch_changes: dict) -> str:
    """Связанные функции из существующего проекта (БД)."""
    db_context = ""
    for key, code in await get_db_dependencies(client, cursor, target_code):
        if key not in batch_changes:  # версии изменённых функций в БД устарели
            db_context += f"--- FROM KNOWLEDGE BASE: {key} ---\n{code}\n\n"

    return db_context or "No related functions found in the existing codebase."


def get_batch_context(target_key: str, target_code: str, batch_changes: dict) -> str:
    """Другие новые функции, которые вызывает целевая функция."""
    batch_context = ""
    for called_func in find_called_functions_in_code(target_code):
        for key, code in batch_changes.items():
            if key != target_key and key.endswith((f"::{called_func}", f".{called_func}")):
                batch_context += f"--- SIBLING CHANGE: {key} ---\n{code}\n\n"

    return batch_context or "None"


async def process_files(file_paths: list[tuple[str, str]]):
    logger.info('Starting inference pipeline...')
    client = AsyncClient(host=OLLAMA_HOST)

    # Индексация: достаём функции из изменённых файлов
    logger.info(f"Indexing {len(file_paths)} files...")
    batch_changes = {}
    for abs_path, rel_path in file_paths:
        batch_changes.update(extract_functions_from_file(abs_path, rel_path, TARGET_DIR))
    logger.info(f"Found {len(batch_changes)} changed functions")

    try:
        conn = psycopg2.connect(**DB_PARAMS)
    except psycopg2.Error as e:
        logger.error(f"Error during connecting to the DB: {e}")
        return
    cursor = conn.cursor()

    # Последовательно, чтобы не перегрузить локальную модель
    logger.info("Running LLM checks...")
    report = []
    for key, code in batch_changes.items():
        try:
            result = await analyze_single_function(client, cursor, key, code, batch_changes)
            report.append(f"[{key}]\n{result}")
        except Exception as e:
            logger.error(f"Error during analyzing {key}: {e}")
            conn.rollback()

    cursor.close()
    conn.close()

    print("\n" + "=" * 50)
    print("IMPACT ANALYZER REPORT")
    print("=" * 50)
    for res in report:
        print(res)
        print("-" * 50)


def process_incoming_files():
    incoming_dir = "/app/incoming" # docker-relative folder
    ignored_folders = {"venv", ".venv", "__pycache__", ".git"}

    files_to_check = []
    for abs_path in iter_python_files(incoming_dir, ignored_folders):
        rel_path = os.path.relpath(abs_path, incoming_dir)
        files_to_check.append((abs_path, rel_path))

    return files_to_check


if __name__ == "__main__":
    asyncio.run(process_files(process_incoming_files()))