import logging
import os
import re
import sys
import time

import psycopg2
from httpx import RequestError
from ollama import Client

from src.ast_parser import extract_functions_from_file
from src.filesystem_utils import process_incoming_files
from src.ollama_utils import analyze_function
from src.rag import filter_modified_functions
from src.settings import DB_PARAMS, REPORT_PATH

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    stream=sys.stdout
)

logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

OLLAMA_HOST = os.getenv('OLLAMA_HOST')
VECTOR_MODEL = os.getenv('VECTOR_MODEL')
ANALYSIS_MODEL = os.getenv('ANALYSIS_MODEL')
TARGET_DIR = os.getenv('TARGET_DIR') or ""

def inference_pipeline(file_paths: list[tuple[str, str]]):
    logger.info('Starting inference pipeline...')
    start = time.time()
    client = Client(host=OLLAMA_HOST)

    logger.info(f"Extracting functions from {len(file_paths)} files...")
    extracted_functions = {}
    extracted_ast = {}

    for abs_path, rel_path in file_paths:
        ast_data, raw_funcs = extract_functions_from_file(abs_path, rel_path, TARGET_DIR)

        if ast_data:
            extracted_ast[rel_path] = ast_data

        extracted_functions.update(raw_funcs)

    try:
        conn = psycopg2.connect(**DB_PARAMS)
    except psycopg2.Error as e:
        logger.error(f"Error during connecting to the DB: {e}")
        return
    cursor = conn.cursor()

    batch_changes = filter_modified_functions(cursor, extracted_functions)

    logger.info("Running LLM checks...")
    results_data = []

    for i, (key, codes) in enumerate(batch_changes.items(), 1):
        logger.info(f"[{i}/{len(batch_changes)}] {key}")

        new_code = codes.get("new", "")
        old_code = codes.get("old", "")

        try:
            result = analyze_function(
                client, cursor, key, new_code, old_code,
                batch_changes, extracted_functions, extracted_ast
            )

            match = re.search(r'["\']verdict_status["\']\s*:\s*["\'](PASS|FAIL)["\']', str(result), re.IGNORECASE)
            status = match.group(1).upper() if match else "UNKNOWN"

            results_data.append((key, result, status))

        except (psycopg2.Error, RequestError) as e:
            logger.error(f"Error during analyzing {key}: {e}")
            conn.rollback()

    cursor.close()
    conn.close()

    report_lines = []

    for key, result, _ in results_data:
        report_lines.append(f"[{key}]\n{result}")
        report_lines.append("-" * 50)

    report_lines.extend([
        "=" * 50,
        "IMPACT ANALYZER REPORT (SUMMARY)",
        "=" * 50
    ])

    for key, _, status in results_data:
        report_lines.append(f"{status} — [{key}]")

    final_report_text = "\n".join(report_lines)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(final_report_text)

    print("\n" + final_report_text + "\n")

    logger.info(f"Inference completed in {time.time() - start:.4f}s")


if __name__ == "__main__":
    inference_pipeline(process_incoming_files())