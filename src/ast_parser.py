import ast
import json
import logging
import os
import subprocess
import tempfile
import time

from dotenv import load_dotenv

from src.filesystem_utils import iter_python_files, read_file_safely
from src.paths import (
    AST_FUNCTIONS_PATH,
    AST_FUNCTIONS_UPD_PATH,
    RAW_FUNCTIONS_PATH,
    RAW_FUNCTIONS_UPD_PATH,
)

logger = logging.getLogger(__name__)

load_dotenv()

IGNORED_DIRS = {'.venv', '__pycache__'}

class CodeExtractor(ast.NodeVisitor):
    def __init__(self, project_root, file_content, file_path):
        self.data = {
            "imports": [],
            "classes": {},
            "functions": []
        }
        self.raw_functions = {}
        self.file_content = file_content
        self.file_path = file_path
        self.project_root = project_root
        self.current_class = None

    def visit_Import(self, node):
        for alias in node.names:
            self.data["imports"].append(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module:
            rel_path = node.module.replace('.', '/')
            possible_file = os.path.join(self.project_root, f'{rel_path}.py')

            if os.path.exists(possible_file):
                self.data["imports"].append(f'{rel_path}.py')
            else:
                self.data["imports"].append(node.module)

        self.generic_visit(node)

    def visit_ClassDef(self, node):
        prev_class = self.current_class
        self.current_class = node.name

        self.data["classes"][node.name] = {
            "methods": []
        }
        self.generic_visit(node)

        self.current_class = prev_class

    def visit_FunctionDef(self, node):
        if self.current_class:
            self.data["classes"][self.current_class]["methods"].append(node.name)
            func_fullname = f'{self.current_class}.{node.name}'
        else:
            self.data["functions"].append(node.name)
            func_fullname = node.name

        raw_code = ast.get_source_segment(self.file_content, node)

        unique_key = f'{self.file_path}::{func_fullname}'
        self.raw_functions[unique_key] = raw_code
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node):
        self.visit_FunctionDef(node)


def extract_ast_code_structure(source: str, file_path: str, project_root: str):
    tree = parse_code_safely(source, file_path)

    if tree is None:
        logger.warning(f"File {file_path} is skipped: can't process AST.")
        return [], {}

    extractor = CodeExtractor(
        project_root=project_root,
        file_content=source,
        file_path=file_path,
    )
    extractor.visit(tree)
    return extractor.data, extractor.raw_functions


def extract_project_ast_code_structure(updated_files=None):
    target_dir = "/app/data" # docker-relative folder

    if updated_files is None:
        file_paths = iter_python_files(target_dir, IGNORED_DIRS)
        ast_path, raw_path = AST_FUNCTIONS_PATH, RAW_FUNCTIONS_PATH
    else:
        file_paths = updated_files
        ast_path, raw_path = AST_FUNCTIONS_UPD_PATH, RAW_FUNCTIONS_UPD_PATH

    start = time.time()
    ast_dict = {}
    raw_functions = {}

    for file_path in file_paths:
        source = read_file_safely(file_path)

        try:
            ast_data, raw = extract_ast_code_structure(source, file_path, target_dir)
        except SyntaxError as e:
            logger.warning(f'Error in {file_path}: {e}')
            continue

        ast_dict[file_path] = ast_data
        raw_functions.update(raw)

    ast_path.write_text(json.dumps(ast_dict, ensure_ascii=False, indent=4), encoding="utf-8")
    raw_path.write_text(json.dumps(raw_functions, ensure_ascii=False, indent=4), encoding="utf-8")

    logger.info(f"AST Parsing completed in {time.time() - start:.4f}s")


def merge_ast_and_docs(ast_functions_path, described_functions_path, rag_functions_path):
    ast_functions = json.loads(ast_functions_path.read_text(encoding="utf-8"))
    docs = json.loads(described_functions_path.read_text(encoding="utf-8"))

    for file_path, file_info in ast_functions.items():
        funcs_list = file_info.get("functions", [])
        file_info["functions"] = {func_name: None for func_name in funcs_list}

        for cls_name, cls_info in file_info.get("classes", {}).items():
            methods_list = cls_info.get("methods", [])
            cls_info["methods"] = {method_name: None for method_name in methods_list}

    for unique_key, docstring in docs.items():
        try:
            file_path, func_fullname = unique_key.split("::")
        except ValueError:
            continue

        if file_path not in ast_functions:
            continue

        if "." in func_fullname:
            cls_name, method_name = func_fullname.split(".", 1)
            if cls_name in ast_functions[file_path]["classes"]:
                ast_functions[file_path]["classes"][cls_name]["methods"][method_name] = docstring
        else:
            if func_fullname in ast_functions[file_path]["functions"]:
                ast_functions[file_path]["functions"][func_fullname] = docstring

    rag_functions_path.write_text(
        json.dumps(ast_functions, indent=4, ensure_ascii=False), encoding="utf-8",
    )


def parse_code_safely(source: str, file_path: str):
    try:
        # 1. Сначала пробуем парсить напрямую (идеально для новых файлов)
        return ast.parse(source)
    except SyntaxError:
        # 2. Сохраняем проблемный код во временный файл
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as tmp:
            tmp.write(source)
            tmp_path = tmp.name

        try:
            subprocess.run(["2to3", "-w", "-n", tmp_path],
                           capture_output=True, check=True, text=True)

            # 4. Читаем сконвертированный Python 3 код и успешно парсим его
            converted_source = read_file_safely(tmp_path)
            return ast.parse(converted_source)

        except subprocess.CalledProcessError as e:
            logger.error(f"2to3 failed for {file_path}: {e.stderr}")
            return None
        except SyntaxError as e:
            logger.error(f"Still SyntaxError after 2to3 conversion in {file_path}: {e}")
            return None
        finally:
            os.remove(tmp_path)  # Очищаем временный файл