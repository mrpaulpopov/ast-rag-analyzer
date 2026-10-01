import json
import asyncio
import os

import psycopg2
from ollama import AsyncClient
from dotenv import load_dotenv

from src.paths import FUNCTIONS_RAG_PATH, RAW_FUNCTIONS_PATH

load_dotenv()

DB_PARAMS = {
    "dbname": os.getenv('POSTGRES_DB'),
    "user": os.getenv('POSTGRES_USER'),
    "password": os.getenv('POSTGRES_PASSWORD'),
    "host": os.getenv('POSTGRES_HOST'),
    "port": os.getenv('POSTGRES_PORT')
}

OLLAMA_HOST = os.getenv('OLLAMA_HOST')


async def process_and_save():
    try:
        with open(FUNCTIONS_RAG_PATH, "r", encoding="utf-8") as f:
            rag_data = json.load(f)
        with open(RAW_FUNCTIONS_PATH, "r", encoding="utf-8") as f:
            raw_functions = json.load(f)
    except FileNotFoundError as e:
         print(f"Ошибка загрузки файлов: {e}")
         return

    client = AsyncClient(host=OLLAMA_HOST)

    try:
        conn = psycopg2.connect(**DB_PARAMS)
        cursor = conn.cursor()
    except psycopg2.Error as e:
        print(f"Ошибка подключения к БД: {e}")
        return

    print("Начинаем генерацию векторов и сохранение в БД...")

    # 4. Обработка и сохранение данных
    for file_path, file_info in rag_data.items():
        # Обработка функций
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

    # 5. Коммит транзакции и закрытие соединения
    conn.commit()
    cursor.close()
    conn.close()
    print("Процесс успешно завершен!")

async def process_item(client, cursor, file_path, func_name, docstring, raw_functions):
    unique_key = f"{file_path}::{func_name}"
    raw_code = raw_functions.get(unique_key, "Код не найден")

    try:
        # Получение эмбеддинга от Ollama
        response = await client.embeddings(
            model='nomic-embed-text',
            prompt=docstring
        )
        embedding = response['embedding']

        # Сохранение в БД
        insert_query = """
            INSERT INTO code_knowledge_base (file_path, func_name, raw_code, docstring, embedding)
            VALUES (%s, %s, %s, %s, %s)
        """
        cursor.execute(insert_query, (file_path, func_name, raw_code, docstring, embedding))
        print(f"Сохранено: {unique_key}")

    except Exception as e:
         print(f"Ошибка при обработке {unique_key}: {e}")

if __name__ == "__main__":
    asyncio.run(process_and_save())
