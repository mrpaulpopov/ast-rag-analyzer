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
