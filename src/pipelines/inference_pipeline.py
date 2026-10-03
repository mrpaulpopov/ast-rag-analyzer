import os
import asyncio
import psycopg2
from dotenv import load_dotenv
from ollama import AsyncClient
import ast

load_dotenv()




# --- Заглушки для твоей будущей логики AST-RAG ---
def extract_functions_from_file(file_content: str) -> dict:
    """Извлекает функции через AST. Возвращает: {'func_name': 'код функции'}"""
    # Имитация AST-парсера
    return {"new_feature_func": file_content[:200]}


def find_called_functions_in_code(code: str) -> list[str]:
    """Анализирует AST кода и возвращает список имен функций, которые он вызывает внутри себя."""
    # Имитация
    return ["helper_func_from_another_file"]


# -------------------------------------------------

async def get_db_dependencies(client, code: str) -> list[tuple]:
    """Ищет связанные функции в PostgreSQL (старый стабильный код)."""
    # В реальном коде здесь будет векторизация и запрос к pgvector
    # Возвращает список: [(func_name, code)]
    return [("old_db_func", "def old_db_func(): pass")]


async def analyze_single_function(client, target_func_name: str, target_code: str, batch_changes: dict):
    """Анализирует одну функцию, учитывая и БД, и соседние измененные файлы."""

    # 1. Какие функции вообще вызывает этот код?
    called_funcs = find_called_functions_in_code(target_code)

    # 2. Ищем зависимости ВНУТРИ текущего списка файлов (In-Memory)
    batch_context = ""
    for called_func in called_funcs:
        if called_func in batch_changes and called_func != target_func_name:
            batch_context += f"--- СОСЕДНЕЕ ИЗМЕНЕНИЕ: {called_func} ---\n```python\n{batch_changes[called_func]}\n```\n\n"

    # 3. Ищем зависимости в PostgreSQL (векторный поиск)
    db_context = ""
    db_deps = await get_db_dependencies(client, target_code)
    for dep_name, dep_code in db_deps:
        # Не добавляем из БД то, что уже обновлено в текущем коммите!
        if dep_name not in batch_changes:
            db_context += f"--- ИЗ БАЗЫ ЗНАНИЙ: {dep_name} ---\n```python\n{dep_code}\n```\n\n"

    # 4. Формируем умный промпт
    validation_prompt = f"""You are a strict automated AI code reviewer.
    A developer modified the function `{target_func_name}`.
    
    [TARGET FUNCTION CODE]
    ```python
    {target_code}
    [OTHER MODIFIED FUNCTIONS IN THIS COMMIT] (Assume these are correct and available) {batch_context or "None"}
    [EXISTING RELATED FUNCTIONS FROM REPO] {db_context or "None"}
    TASK: Analyze if {target_func_name} will break the system or introduce bugs. Output format: STATUS: [PASS or FAIL] ISSUE: [Brief explanation]"""


    response = await client.generate(model=ANALYSIS_MODEL, prompt=validation_prompt)
    return f"🔹 Анализ [{target_func_name}]:\n{response['response']}"


async def process_files(file_paths: list[str]):
    client = AsyncClient(host=os.getenv("OLLAMA_HOST", "http://localhost:11434"))


    print(f"🚀 [PASS 1] Индексация {len(file_paths)} файлов...")
    batch_changes = {}
    for file_path in file_paths:
        if not os.path.exists(file_path):
            continue
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()  # Наполняем глобальный кэш текущих изменений funcs = extract_functions_from_file(content) batch_changes.update(funcs)
    print(f"✅ Найдено {len(batch_changes)} измененных функций. Начинаем анализ...\n")
    print(f"🧠 [PASS 2] Запуск LLM-проверок...")
    final_report = []
    # Можно запускать через asyncio.gather, но для локальной LLM # лучше последовательно, чтобы не убить видеокарту (OOM) for func_name, code in batch_changes.items(): report = await analyze_single_function(client, func_name, code, batch_changes) final_report.append(report)
    print("\n" + "=" * 50)
    print("🎯 ИТОГОВЫЙ ОТЧЕТ IMPACT ANALYZER")
    print("=" * 50)
    for res in final_report: print(res)
    print("-" * 50)


# asyncio.run(process_files(args.files))