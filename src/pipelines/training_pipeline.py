import asyncio
import logging
import sys
import time

from src.ast_parser import extract_project_ast_code_structure, merge_ast_and_docs
from src.filesystem_utils import save_last_run
from src.ollama_utils import create_docstrings
from src.paths import (
    AST_FUNCTIONS_PATH,
    DESCRIBED_FUNCTIONS_PATH,
    RAG_FUNCTIONS_PATH,
    RAW_FUNCTIONS_PATH,
)
from src.rag import export_to_rag

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    stream=sys.stdout
)

logger = logging.getLogger(__name__)


def training_pipeline():
    logger.info('Make sure to get the latest revision. Starting in 7 seconds...')
    time.sleep(7)

    save_last_run()
    extract_project_ast_code_structure()
    asyncio.run(create_docstrings(RAW_FUNCTIONS_PATH, DESCRIBED_FUNCTIONS_PATH))
    merge_ast_and_docs(AST_FUNCTIONS_PATH, DESCRIBED_FUNCTIONS_PATH, RAG_FUNCTIONS_PATH)
    asyncio.run(export_to_rag(RAW_FUNCTIONS_PATH, RAG_FUNCTIONS_PATH))
    logger.info('Training pipeline was successfully finished.')

if __name__ == "__main__":
    training_pipeline()

