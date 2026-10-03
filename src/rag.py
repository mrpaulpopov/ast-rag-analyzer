import ast
import json
import logging
import os

import psycopg2
from dotenv import load_dotenv
from ollama import AsyncClient

load_dotenv()

DB_PARAMS = {
    "dbname": os.getenv('POSTGRES_DB'),
    "user": os.getenv('POSTGRES_USER'),
    "password": os.getenv('POSTGRES_PASSWORD'),
    "host": os.getenv('POSTGRES_HOST'),
    "port": os.getenv('POSTGRES_PORT')
}

OLLAMA_HOST = os.getenv('OLLAMA_HOST')
VECTOR_MODEL = os.getenv('VECTOR_MODEL')

logger = logging.getLogger(__name__)


async def export_to_rag(raw_functions_path, rag_functions_path):
    try:
        raw_functions = json.loads(raw_functions_path.read_text(encoding="utf-8"))
        rag_functions = json.loads(rag_functions_path.read_text(encoding="utf-8"))
        for code in raw_functions.values():
            ast.parse(code)
    except FileNotFoundError as e:
         logger.error(f"Error during loading files: {e}")
         return

    client = AsyncClient(host=OLLAMA_HOST)

    try:
        conn = psycopg2.connect(**DB_PARAMS)
        cursor = conn.cursor()
    except psycopg2.Error as e:
        logger.error(f"Error during connecting to the DB: {e}")
        return

    logger.info("Starting generating vectors and sending to DB...")

    for file_path, file_info in rag_functions.items():
        # Обработка обычных функций
        for func_name, docstring in file_info.get("functions", {}).items():
             if not docstring:
                 continue
             await process_item(client, cursor, file_path, func_name, docstring, raw_functions)

        # Обработка методов классов
        for cls_name, cls_info in file_info.get("classes", {}).items():
            for method_name, docstring in cls_info.get("methods", {}).items():
                if not docstring:
                    continue
                func_fullname = f"{cls_name}.{method_name}"
                await process_item(client, cursor, file_path, func_fullname, docstring, raw_functions)

    conn.commit()
    cursor.close()
    conn.close()
    logger.info("Successfully updated vector database.")


async def process_item(client, cursor, file_path, func_name, docstring, raw_functions):
    unique_key = f"{file_path}::{func_name}"
    raw_code = raw_functions.get(unique_key, "The code is not found")

    try:
        # generating vector
        response = await client.embeddings(
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
        logger.info(f"Upserted (Inserted/Updated): {unique_key}")

    except Exception as e: # noqa: BLE001
         logger.error(f"Error during processing {unique_key}: {e}")
