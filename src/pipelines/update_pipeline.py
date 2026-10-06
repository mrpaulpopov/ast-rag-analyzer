import asyncio
import logging
import sys

from src.ast_parser import extract_project_ast_code_structure, merge_ast_and_docs
from src.filesystem_utils import get_changed_files, save_last_run
from src.ollama_utils import create_docstrings
from src.paths import (
    AST_FUNCTIONS_UPD_PATH,
    DESCRIBED_FUNCTIONS_UPD_PATH,
    RAG_FUNCTIONS_UPD_PATH,
    RAW_FUNCTIONS_UPD_PATH,
)
from src.rag import export_to_rag

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    stream=sys.stdout
)

logger = logging.getLogger(__name__)

def update_pipeline():
    updated_files = get_changed_files()
    if not updated_files:
        logger.info("No changes detected. Stopping pipeline.")
        return

    save_last_run()
    extract_project_ast_code_structure(updated_files)
    asyncio.run(create_docstrings(RAW_FUNCTIONS_UPD_PATH, DESCRIBED_FUNCTIONS_UPD_PATH))
    merge_ast_and_docs(AST_FUNCTIONS_UPD_PATH, DESCRIBED_FUNCTIONS_UPD_PATH, RAG_FUNCTIONS_UPD_PATH)
    asyncio.run(export_to_rag(RAW_FUNCTIONS_UPD_PATH, RAG_FUNCTIONS_UPD_PATH))
    logger.info('Update pipeline was successfully finished.')

if __name__ == "__main__":
    update_pipeline()