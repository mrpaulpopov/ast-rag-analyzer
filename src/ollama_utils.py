import ast
import json
import logging
import os
import time

import psycopg2
from dotenv import load_dotenv
from ollama import AsyncClient

from src.ast_parser import parse_code_safely

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
        print(description)
        ollama_dict[key] = description

        current += 1

        with open(described_functions_path, "w", encoding="utf-8") as f:
            json.dump(ollama_dict, f, indent=4, ensure_ascii=False)

    logger.info(f"Docstrings were successfully created in {time.time() - start:.4f}s")
    return ollama_dict


async def analyze_impact(changed_func_name: str, new_code: str):
    client = AsyncClient(host=OLLAMA_HOST)


    print(f"🔄 Анализ влияния для измененной функции: {changed_func_name}...")

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
    A developer has modified the function `{changed_func_name}`. 
    
    Here is the NEW code for this function:
    {new_code}
    
    Below are the dependent or closely related functions from the rest of the codebase (they may call this function or share the same data structures): {related_code_context}
    TASK: Analyze whether the new code in {changed_func_name} will break the execution of the provided related functions OR introduce critical logical bugs into the pipeline. Don't use markdown.
    Pay special attention to:
    1. Interface changes: missing/added arguments or altered return types.
    2. Data structure alterations: removal of dictionary keys or expected object attributes.
    3. LOGICAL BUGS: changes in array slicing, boundary conditions (e.g., indices, thresholds), mathematical operations, or state modifications that will cause the related functions to receive incorrect, shifted, or overlapping data.
    Output your report STRICTLY in the exact format below:
    STATUS: [PASS or FAIL]
    ISSUE: [If FAIL, precisely describe what will break. If PASS, write "No conflicts detected."]
    """

    print("Выполняю кросс-проверку логики через LLM...\n")
    response = await client.generate(
        model=ANALYSIS_MODEL,
        prompt=validation_prompt
    )
    print(response['response'])
