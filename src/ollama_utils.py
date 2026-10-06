import ast
import json
import logging
import os
import time

import psycopg2
import yaml
from dotenv import load_dotenv
from ollama import AsyncClient

from src.ast_parser import parse_code_safely
from src.paths import CONFIG_PATH

load_dotenv()

DB_PARAMS = {
    "dbname": os.getenv("POSTGRES_DB"),
    "user": os.getenv("POSTGRES_USER"),
    "password": os.getenv("POSTGRES_PASSWORD"),
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": os.getenv("POSTGRES_PORT", "5432")
}

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
ANALYSIS_MODEL = os.getenv("ANALYSIS_MODEL")

logger = logging.getLogger(__name__)


class OllamaGenerator:
    def __init__(self, model_name=ANALYSIS_MODEL):
        self.model_name = model_name
        self.host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.client = AsyncClient(host=self.host)

    async def generate_docstring(self, raw_code: str) -> str:

        prompt = f"""
        Analyze the following Python function:
        {raw_code}
        
        Task: You are an expert Senior Python Developer. Write a concise technical description for the function above.
        
        CRITICAL RULES:
        1. Limit the description to exactly 1-2 sentences. STRICTLY NO BULLET POINTS.
        2. Use strictly English.
        3. State exactly what the function does, its core inputs, and its expected return value.
        4. Output ONLY the raw text description. NO conversational filler, NO greetings, NO breakdown of components.
        """

        try:
            response = await self.client.generate(
                model=self.model_name,
                prompt=prompt,
                stream=False,
                options={
                    "temperature": 0.0, # no warmth
                    "top_p": 0.9,
                }
            )
            return response['response'].strip()

        except Exception as e: # noqa: BLE001
            logger.error(f"Error during connection to Ollama: {e}")
            return "Error during connection to Ollama."


async def create_docstrings(raw_functions_path, described_functions_path) -> dict:
    raw_functions = json.loads(raw_functions_path.read_text(encoding="utf-8"))
    for key, code in raw_functions.items():
        tree = parse_code_safely(source=code, file_path=key)
        if tree is None:
            logger.warning(f"Function {key} is skipped: unsupported syntaxis.")
            continue

    start = time.time()
    ollama_dict = {}

    generator = OllamaGenerator()

    total = len(raw_functions)
    current = 1

    for key, func_code in raw_functions.items():
        print(f"[{current}/{total}] Generating docstring for: {key}")

        description = await generator.generate_docstring(func_code)
        ollama_dict[key] = description

        current += 1

        with open(described_functions_path, "w", encoding="utf-8") as f:
            json.dump(ollama_dict, f, indent=4, ensure_ascii=False)

    logger.info(f"Docstrings were successfully created in {time.time() - start:.4f}s")
    return ollama_dict


async def analyze_impact(changed_func_name: str, new_code: str):
    client = AsyncClient(host=OLLAMA_HOST)
    cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    NUM_CTX = cfg["inference"]["num_ctx"]


    logger.info(f"🔄 Анализ влияния для измененной функции: {changed_func_name}...")

    # 1. Векторизуем измененный код
    embed_response = await client.embeddings(
        model='nomic-embed-text',
        prompt=new_code
    )
    code_vector = embed_response['embedding']

    # 2. Ищем связанный код в базе знаний (исключая саму эту функцию, если она там есть)
    conn = psycopg2.connect(**DB_PARAMS)
    cursor = conn.cursor()

    query = """
        SELECT file_path, func_name, raw_code 
        FROM code_knowledge_base 
        WHERE func_name != %s
        ORDER BY embedding <=> %s::vector 
        LIMIT 5;
    """

    cursor.execute(query, (changed_func_name, code_vector))
    results = cursor.fetchall()

    cursor.close()
    conn.close()

    if not results:
        print("Зависимый или связанный код не найден. Изменение безопасно.")
        return

    # 3. Формируем контекст из связанного кода
    related_code_context = ""
    for row in results:
        file_path, func_name, raw_code = row
        related_code_context += f"--- Dependency: {func_name} (Файл: {file_path}) ---\n"
        related_code_context += f"{raw_code}\n"

    # 4. Жесткий промпт для валидации поломок
    validation_prompt = f"""You are a strict automated AI code reviewer and impact analyzer.
    A developer modified the function `{changed_func_name}`.

    [NEW CODE OF THE FUNCTION]
    ```python
    {new_code}
    ```

    [DEPENDENT OR RELATED FUNCTIONS FROM THE CODEBASE] (they may call this function or share its data structures)
    ```python
    {related_code_context}
    ```

    TASK: Decide whether the new code of `{changed_func_name}` breaks the related functions or introduces a critical logical bug.
    Check these points one by one:
    1. Interface: for every related function that calls `{changed_func_name}`, compare the call (number, order and names of arguments)
       with the new signature, and compare how the result is used with what the new code really returns (type, structure, None).
    2. Data structures: dictionary keys or object attributes that related functions read but the new code no longer provides,
       or that the new code reads but related functions do not provide.
    3. Logic: array slicing, indices, boundary conditions, thresholds, math operations or state changes that make
       the related functions receive incorrect, shifted or overlapping data.
    Report only problems you can show with specific lines from the code above.
    If no related function uses `{changed_func_name}`, do not report interface problems.
    Do not guess about code you cannot see. Do not use markdown in your answer.

    Answer in exactly this format:
    CHECKS: one short line for each of the 3 points
    STATUS: PASS or FAIL
    ISSUE: if FAIL, quote the exact line and describe what will break; if PASS, write "No conflicts detected."
    """

    logger.info("Выполняю кросс-проверку логики через LLM...\n")
    response = await client.generate(
        model=ANALYSIS_MODEL,
        prompt=validation_prompt,
        options={
            "num_ctx": NUM_CTX,
            "temperature": 0,
            "seed": 42
        }
    )
    print(response['response'])
