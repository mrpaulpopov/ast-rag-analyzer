import logging
import os
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
    for abs_path, rel_path in file_paths:
        extracted_functions.update(extract_functions_from_file(abs_path, rel_path, TARGET_DIR))

    try:
        conn = psycopg2.connect(**DB_PARAMS)
    except psycopg2.Error as e:
        logger.error(f"Error during connecting to the DB: {e}")
        return
    cursor = conn.cursor()

    batch_changes = filter_modified_functions(cursor, extracted_functions)

    logger.info("Running LLM checks...")
    report = []
    for i, (key, code) in enumerate(batch_changes.items(), 1):
        logger.info(f"[{i}/{len(batch_changes)}] {key}")
        try:
            result = analyze_function(client, cursor, key, code, batch_changes, extracted_functions)

            # Filtering FAIL-only issues
            if "STATUS: PASS" in str(result).upper():
                report.append(f"[{key}]\nSTATUS: PASS")
            else:
                report.append(f"[{key}]\n{result}")

        except (psycopg2.Error, RequestError) as e:
            logger.error(f"Error during analyzing {key}: {e}")
            conn.rollback()

    cursor.close()
    conn.close()

    report_lines = [
        "=" * 50,
        "IMPACT ANALYZER REPORT",
        "=" * 50
    ]

    for res in report:
        report_lines.append(res)
        report_lines.append("-" * 50)

    final_report_text = "\n".join(report_lines)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(final_report_text)

    print("\n" + final_report_text)

    logger.info(f"Inference completed in {time.time() - start:.4f}s")


if __name__ == "__main__":
    inference_pipeline(process_incoming_files())