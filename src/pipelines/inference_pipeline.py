import ast
import asyncio
import logging
import os
import sys
import textwrap
import time

import psycopg2
import yaml
from ollama import AsyncClient

from src.ast_parser import extract_ast_code_structure
from src.filesystem_utils import iter_python_files, read_file_safely
from src.paths import CONFIG_PATH

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    stream=sys.stdout
)

logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

CFG = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))

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
    source = read_file_safely(abs_path)

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
    MAX_COSINE_DISTANCE = float(CFG["inference"]["max_cosine_distance"])
    TOP_K = int(CFG["inference"]["top_k"])

    safe_code = code[:4000] # RAG limits
    response = await client.embeddings(model=VECTOR_MODEL, prompt=safe_code)
    query_vector = str(response["embedding"])

    cursor.execute(
        """
        SELECT file_path, func_name, raw_code, embedding <=> %s::vector AS distance
        FROM code_knowledge_base
        WHERE embedding <=> %s::vector < %s
        ORDER BY distance
        LIMIT %s
        """,
        (query_vector, query_vector, MAX_COSINE_DISTANCE, TOP_K),
    )
    rows = cursor.fetchall()

    for file_path, func_name, _, distance in rows:
        logger.debug(f"{file_path}::{func_name} distance={distance:.3f}")

    return [(f"{file_path}::{func_name}", raw_code)
            for file_path, func_name, raw_code, _ in rows]


async def analyze_function(client, cursor, target_key: str, target_code: str, batch_changes: dict, all_functions: dict) -> str:
    """Один запрос к LLM: функция + контекст проекта + контекст других новых функций."""

    # Attributes handling
    file_path, name = target_key.rsplit("::", 1)
    known_attrs, used_attrs = set(), set()

    if "." in name:  # это метод класса
        class_prefix = f"{file_path}::{name.split('.')[0]}."

        # Что известно о классе: имена методов и всё, что присваивается через self.x = ...
        for key, code in all_functions.items():
            if not key.startswith(class_prefix):
                continue
            known_attrs.add(key[len(class_prefix):])
            try:
                tree = ast.parse(textwrap.dedent(code))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                        and node.value.id == "self" and isinstance(node.ctx, ast.Store)):
                    known_attrs.add(node.attr)

        # Что читает проверяемая функция через self.x
        for node in ast.walk(ast.parse(textwrap.dedent(target_code))):
            if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                    and node.value.id == "self" and isinstance(node.ctx, ast.Load)):
                used_attrs.add(node.attr)

    unknown_attrs = used_attrs - known_attrs

    cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    NUM_CTX = cfg["inference"]["num_ctx"]

    project_context = await get_project_context(client, cursor, target_code, batch_changes)
    batch_context = get_batch_context(target_key, target_code, batch_changes)

    prompt = f"""You are a strict automated AI code reviewer.
    A developer modified the function `{target_key}`.

    [TARGET FUNCTION CODE]
    ```python
    {target_code}
    ```
    
    [CLASS METHODS AND ATTRIBUTES ASSIGNED IN OTHER METHODS]
    {", ".join(sorted(known_attrs)) or "None"}
    
    [ATTRIBUTES READ IN THIS FUNCTION BUT NEVER ASSIGNED IN THE CLASS]
    {", ".join(sorted(unknown_attrs)) or "None"}

    [EXISTING RELATED FUNCTIONS FROM REPO]
    {project_context}

    [OTHER MODIFIED FUNCTIONS IN THIS COMMIT] (assume they are correct)
    {batch_context}

    TASK: Check the target function for bugs that would break the system. Go through these checks one by one:
    1. Parameters: every parameter in the signature (except self, cls, *args, **kwargs) must be used in the function body.
       An unused parameter is a FAIL: it is either left over by mistake or callers do not pass it.
       If a parameter is used in the body, assume that all callers were updated, unless the provided context shows a broken call.
    2. Names and Scope:
    - Local variables: Every variable read inside the function body MUST be assigned beforehand within the same function
    or passed as a parameter. Using an undefined local variable (e.g. returning `parent_node` when 
    only `parents` was assigned) is a strict FAIL (NameError).
    - Class attributes (`self.`): look at the last section above. Report an attribute from it ONLY if it is spelled
    similarly to a name in the known list (e.g. `anim_dir_path` vs `animation_dir`).
    Otherwise do not report it: it may be inherited from a base class.
    3. Return value: compare what the function returns with how the related functions use its result.
    A different type or structure (list instead of dict, tuple instead of one value, None instead of a value) is a FAIL.
    4. Calls: calls to other functions must match their signatures in the provided context (number and names of arguments).
    Report only problems you can point to in the code above. Do not guess about code you cannot see. Ignore style and comments.

    Answer in exactly this format:
    CHECKS: one short line for each of the 4 checks
    STATUS: PASS or FAIL
    ISSUE: if FAIL, quote the exact line and explain what is wrong; if PASS, write "No problems detected."
    """

    response = await client.generate(model=ANALYSIS_MODEL,
                                     prompt=prompt,
                                     options={
                                         "num_ctx": NUM_CTX,
                                         "temperature": 0,
                                         "seed": 42
                                     }
                                     )
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


async def inference_pipeline(file_paths: list[tuple[str, str]]):
    logger.info('Starting inference pipeline...')
    start = time.time()
    client = AsyncClient(host=OLLAMA_HOST)

    # 1. Индексация: достаём ВСЕ функции из затронутых файлов
    logger.info(f"Extracting functions from {len(file_paths)} files...")
    extracted_functions = {}
    for abs_path, rel_path in file_paths:
        extracted_functions.update(extract_functions_from_file(abs_path, rel_path, TARGET_DIR))

    try:
        conn = psycopg2.connect(**DB_PARAMS)
    except psycopg2.Error as e:
        logger.error(f"Error during connecting to the DB: {e}")
        return
    cursor = conn.cursor()

    logger.info("Comparing with database to skip unmodified functions...")
    batch_changes = {}
    same = different = not_in_db = 0

    for key, new_code in extracted_functions.items():
        file_path, func_name = key.split("::", 1) if "::" in key else (key, "")

        # В БД путь может быть абсолютным (/app/data/...), а у нас относительный,
        # поэтому сравниваем по окончанию пути
        cursor.execute(
            """
            SELECT raw_code FROM code_knowledge_base
            WHERE func_name = %s AND right(file_path, %s) = %s
            LIMIT 1
            """,
            (func_name, len(file_path), file_path),
        )
        db_result = cursor.fetchone()

        if db_result is None:
            not_in_db += 1
            batch_changes[key] = new_code
        elif db_result[0].strip() != new_code.strip():
            different += 1
            batch_changes[key] = new_code
        else:
            same += 1

    logger.info(f"Unchanged: {same}, changed: {different}, not found in DB: {not_in_db}")
    logger.info(f"Found {len(batch_changes)} ACTUALLY modified/new functions for LLM analysis.")

    logger.info("Running LLM checks...")
    report = []
    for key, code in batch_changes.items():
        try:
            result = await analyze_function(client, cursor, key, code, batch_changes, extracted_functions)

            # Filtering FAIL-only issues: проверяем текущий result, а не весь список report
            if "STATUS: PASS" in str(result).upper():
                report.append(f"[{key}]\nSTATUS: PASS")
            else:
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
    logger.info(f"Inference completed in {time.time() - start:.4f}s")


def process_incoming_files():
    incoming_dir = "/app/incoming" # docker-relative folder
    ignored_folders = {"venv", ".venv", "__pycache__", ".git"}

    files_to_check = []
    for abs_path in iter_python_files(incoming_dir, ignored_folders):
        rel_path = os.path.relpath(abs_path, incoming_dir)
        files_to_check.append((abs_path, rel_path))

    return files_to_check


if __name__ == "__main__":
    asyncio.run(inference_pipeline(process_incoming_files()))