import ast
import json
import logging
import os
import textwrap

import psycopg2
from dotenv import load_dotenv
from ollama import Client

from src.ast_parser import find_called_functions_in_code
from src.settings import CFG, DB_PARAMS

load_dotenv()

OLLAMA_HOST = os.getenv('OLLAMA_HOST')
VECTOR_MODEL = os.getenv('VECTOR_MODEL')

logger = logging.getLogger(__name__)


def export_to_rag(raw_functions_path, rag_functions_path):
    try:
        raw_functions = json.loads(raw_functions_path.read_text(encoding="utf-8"))
        rag_functions = json.loads(rag_functions_path.read_text(encoding="utf-8"))
        for code in raw_functions.values():
            try:
                ast.parse(textwrap.dedent(code))
            except SyntaxError:
                pass
    except FileNotFoundError as e:
         logger.error(f"Error during loading files: {e}")
         return

    client = Client(host=OLLAMA_HOST)

    try:
        conn = psycopg2.connect(**DB_PARAMS)
        cursor = conn.cursor()
    except psycopg2.Error as e:
        logger.error(f"Error during connecting to the DB: {e}")
        return

    logger.info("Starting generating vectors and sending to DB...")

    for file_path, file_info in rag_functions.items():
        # Functions
        for func_name, docstring in file_info.get("functions", {}).items():
            if not docstring:
                continue
            process_item(client, cursor, file_path, func_name, docstring, raw_functions)

        # Methods
        for cls_name, cls_info in file_info.get("classes", {}).items():
            for method_name, docstring in cls_info.get("methods", {}).items():
                if not docstring:
                    continue
                func_fullname = f"{cls_name}.{method_name}"
                process_item(client, cursor, file_path, func_fullname, docstring, raw_functions)

    conn.commit()
    cursor.close()
    conn.close()
    logger.info("Successfully updated vector database.")


def process_item(client, cursor, file_path, func_name, docstring, raw_functions):
    unique_key = f"{file_path}::{func_name}"
    raw_code = raw_functions.get(unique_key, "The code is not found")

    try:
        # generating vector
        response = client.embeddings(
            model=VECTOR_MODEL,
            prompt=docstring
        )
        embedding = response['embedding']

        upsert_query = """
            INSERT INTO code_knowledge_base (file_path, func_name, raw_code, docstring, embedding)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (file_path, func_name) 
            DO UPDATE SET 
                raw_code = EXCLUDED.raw_code,
                docstring = EXCLUDED.docstring,
                embedding = EXCLUDED.embedding;
        """
        cursor.execute(upsert_query, (file_path, func_name, raw_code, docstring, embedding))

    except Exception as e: # noqa: BLE001
         logger.error(f"Error during processing {unique_key}: {e}")


def get_db_dependencies(client, cursor, code: str) -> list[tuple]:
    """Find similar functions in RAG PostgreSQL. Returns [('file::func', code)]."""
    MAX_COSINE_DISTANCE = float(CFG["inference"]["max_cosine_distance"])
    TOP_K = int(CFG["inference"]["top_k"])

    safe_code = code[:4000] # RAG limits
    response = client.embeddings(model=VECTOR_MODEL, prompt=safe_code)
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


def get_project_context(client, cursor, target_code: str, batch_changes: dict) -> str:
    """Related existing functions from DB."""
    db_context = ""

    for key, code in get_db_dependencies(client, cursor, target_code):
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

def filter_modified_functions(cursor, extracted_functions: dict) -> dict:
    logger.info("Comparing with database to skip unmodified functions...")
    batch_changes = {}
    same = different = not_in_db = 0

    for key, new_code in extracted_functions.items():
        file_path, func_name = key.split("::", 1) if "::" in key else (key, "")

        # comparing only the endings of strings
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
    return batch_changes