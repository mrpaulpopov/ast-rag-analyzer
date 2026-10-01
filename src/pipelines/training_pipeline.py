import ast
import asyncio
import json
import logging
import sys

import yaml

from src.ast_parser import extract_ast_project_data
from src.ollama_utils import OllamaGenerator, create_docstrings
from src.paths import ALL_PROC_FUNCTIONS, RAG_DATABASE, AST_PATH, ALL_RAW_FUNCTIONS, CONFIG_PATH

import asyncio
import json


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    stream=sys.stdout
)

logger = logging.getLogger(__name__)


def merge_ast_and_docs(ast_data: dict, ollama_data: dict) -> dict:
    for file_path, file_info in ast_data.items():
        funcs_list = file_info.get("functions", [])
        file_info["functions"] = {func_name: None for func_name in funcs_list}

        for cls_name, cls_info in file_info.get("classes", {}).items():
            methods_list = cls_info.get("methods", [])
            cls_info["methods"] = {method_name: None for method_name in methods_list}


    for unique_key, docstring in ollama_data.items():
        try:
            file_path, func_fullname = unique_key.split("::")
        except ValueError:
            continue

        if file_path not in ast_data:
            continue

        if "." in func_fullname:
            cls_name, method_name = func_fullname.split(".", 1)
            if cls_name in ast_data[file_path]["classes"]:
                ast_data[file_path]["classes"][cls_name]["methods"][method_name] = docstring
        else:
            if func_fullname in ast_data[file_path]["functions"]:
                ast_data[file_path]["functions"][func_fullname] = docstring

        with open(RAG_DATABASE, "w", encoding="utf-8") as f:
            json.dump(ast_data, f, indent=4, ensure_ascii=False)

    return ast_data


def main():
    # Loading config
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    TARGET_DIR = config.get("TARGET_DIR")
    IGNORED_DIRS = set(config.get("IGNORED_DIRS") or [])

    ast_dict, raw_functions = extract_ast_project_data(TARGET_DIR, IGNORED_DIRS)

    json_str = json.dumps(ast_dict, indent=4)
    with open(AST_PATH, "w") as f:
        f.write(json_str)

    json_str = json.dumps(raw_functions, indent=4)
    with open(ALL_RAW_FUNCTIONS, "w") as f:
        f.write(json_str)

    # ollama_dict = asyncio.run(create_docstrings(raw_functions))

    # DEBUG
    # with open(AST_PATH, "r", encoding="utf-8") as f:
    #     file_content = f.read()
    #     ast_dict = ast.literal_eval(file_content)
    #
    # with open(ALL_PROC_FUNCTIONS, "r", encoding="utf-8") as f:
    #     file_content = f.read()
    #     ollama_dict = ast.literal_eval(file_content)

    # merge_ast_and_docs(ast_dict, ollama_dict)


if __name__ == "__main__":
    main()