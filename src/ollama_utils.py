import json
import logging
import os
import time

from dotenv import load_dotenv
from ollama import Client

from src.ast_parser import extract_class_attributes, parse_code_safely
from src.rag import get_batch_context, get_project_context
from src.settings import CFG, TRAINING_PROMPT_PATH, INFERENCE_PROMPT_PATH, DEBUG_PROMPTS_DIR

load_dotenv()

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
ANALYSIS_MODEL = os.getenv("ANALYSIS_MODEL")

logger = logging.getLogger(__name__)


class OllamaGenerator:
    """A generator that maintains a connection to the Ollama"""
    def __init__(self, model_name=ANALYSIS_MODEL):
        self.model_name = model_name
        self.host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.client = Client(host=self.host)

    def generate_docstring(self, raw_code: str) -> str:
        # Reading prompt from txt
        prompt_template = TRAINING_PROMPT_PATH.read_text(encoding="utf-8")
        prompt = prompt_template.format(raw_code=raw_code)

        try:
            response = self.client.generate(
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


def create_docstrings(raw_functions_path, described_functions_path) -> dict:
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

        description = generator.generate_docstring(func_code)
        ollama_dict[key] = description

        current += 1

        with open(described_functions_path, "w", encoding="utf-8") as f:
            json.dump(ollama_dict, f, indent=4, ensure_ascii=False)

    logger.info(f"Docstrings were successfully created in {time.time() - start:.4f}s")
    return ollama_dict


def analyze_function(client, cursor, target_key: str, target_code: str, batch_changes: dict, batch_functions: dict, batch_ast: dict) -> str:
    """LLM query: function + project context + context of other new functions"""

    known_attrs, used_attrs = extract_class_attributes(target_key, target_code, batch_functions, batch_ast)
    unknown_attrs = used_attrs - known_attrs

    NUM_CTX = CFG["inference"]["num_ctx"]

    project_context = get_project_context(client, cursor, target_key, target_code, batch_changes)
    batch_context = get_batch_context(target_key, target_code, batch_changes)
    known_attrs_str = ", ".join(sorted(known_attrs)) or "None"
    unknown_attrs_str = ", ".join(sorted(unknown_attrs)) or "None"

    # Reading prompt from txt
    prompt_template = INFERENCE_PROMPT_PATH.read_text(encoding="utf-8")
    prompt = prompt_template.format(
        target_key=target_key,
        target_code=target_code,
        known_attrs_str=known_attrs_str,
        unknown_attrs_str=unknown_attrs_str,
        project_context=project_context,
        batch_context=batch_context
    )

    # DEBUG: Write prompt to file
    safe_filename = target_key.replace("/", "_").replace("\\", "_").replace("::", "__") + ".txt"
    current_debug_path = DEBUG_PROMPTS_DIR / safe_filename
    with open(current_debug_path, "w", encoding="utf-8") as f:
        f.write(prompt)

    response = client.generate(model=ANALYSIS_MODEL,
                               prompt=prompt,
                               options={
                                   "num_ctx": NUM_CTX,
                                   "temperature": 0,
                                   "seed": 42
                               }
                               )
    return response["response"]
