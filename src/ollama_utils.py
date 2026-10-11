import json
import logging
import os
import time

from dotenv import load_dotenv
from ollama import AsyncClient

from src.ast_parser import extract_class_attributes, parse_code_safely
from src.rag import get_batch_context, get_project_context
from src.settings import CFG, PROMPT_PATH

load_dotenv()

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


async def analyze_function(client, cursor, target_key: str, target_code: str, batch_changes: dict, all_functions: dict) -> str:
    """LLM query: function + project context + context of other new functions"""

    known_attrs, used_attrs = extract_class_attributes(target_key, target_code, all_functions)
    unknown_attrs = used_attrs - known_attrs

    NUM_CTX = CFG["inference"]["num_ctx"]

    project_context = await get_project_context(client, cursor, target_code, batch_changes)
    batch_context = get_batch_context(target_key, target_code, batch_changes)

    prompt = f"""You are a strict automated AI code reviewer.
    A developer modified the function `{target_key}`.

    [TARGET FUNCTION CODE]
    ```python
    {target_code}
    ```
    
    [CLASS METHODS AND ATTRIBUTES ASSIGNED IN OTHER METHODS]
    {", ".join(sorted(known_attrs)) or "None"}
    
    [ATTRIBUTES READ IN THIS FUNCTION BUT NEVER ASSIGNED IN THE CLASS]
    {", ".join(sorted(unknown_attrs)) or "None"}

    [EXISTING RELATED FUNCTIONS FROM REPO]
    {project_context}

    [OTHER MODIFIED FUNCTIONS IN THIS COMMIT] (assume they are correct)
    {batch_context}

    TASK: Check the target function for bugs that would break the system. Go through these checks one by one:
    1. Parameters: every parameter in the signature (except self, cls, *args, **kwargs) must be used in the function body.
       An unused parameter is a FAIL: it is either left over by mistake or callers do not pass it.
       If a parameter is used in the body, assume that all callers were updated, unless the provided context shows a broken call.
    2. Names and Scope:
    - Local variables: Every variable read inside the function body MUST be assigned beforehand within the same function
    or passed as a parameter. Using an undefined local variable (e.g. returning `parent_node` when 
    only `parents` was assigned) is a strict FAIL (NameError).
    - Class attributes (`self.`): look at the last section above. Report an attribute from it ONLY if it is spelled
    similarly to a name in the known list (e.g. `anim_dir_path` vs `animation_dir`).
    Otherwise do not report it: it may be inherited from a base class.
    3. Return value: compare what the function returns with how the related functions use its result.
    A different type or structure (list instead of dict, tuple instead of one value, None instead of a value) is a FAIL.
    4. Calls: calls to other functions must match their signatures in the provided context (number and names of arguments).
    Report only problems you can point to in the code above. Do not guess about code you cannot see. Ignore style and comments.

    Answer in exactly this format:
    CHECKS: one short line for each of the 4 checks
    STATUS: PASS or FAIL
    ISSUE: if FAIL, quote the exact line and explain what is wrong; if PASS, write "No problems detected."
    """

    # DEBUG: Write prompt to file
    with open(PROMPT_PATH, "w", encoding="utf-8") as f:
        f.write(prompt)

    response = await client.generate(model=ANALYSIS_MODEL,
                                     prompt=prompt,
                                     options={
                                         "num_ctx": NUM_CTX,
                                         "temperature": 0,
                                         "seed": 42
                                     }
                                     )
    return response["response"]
