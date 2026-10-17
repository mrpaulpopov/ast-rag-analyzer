import ast
import json
import logging
import os
import subprocess
import sys
import tempfile
import textwrap
import time
from typing import Any

from dotenv import load_dotenv

from src.filesystem_utils import iter_python_files, read_file_safely
from src.settings import (
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
            "methods": [],
            "class_vars": []
        }

        class_vars = set()
        for stmt in node.body:
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Name):
                        class_vars.add(target.id)
            elif isinstance(stmt, ast.AnnAssign):
                if isinstance(stmt.target, ast.Name):
                    class_vars.add(stmt.target.id)

        if class_vars:
            # Прячем переменные в raw_functions под спец. ключом для передачи дальше
            unique_key = f'{self.file_path}::{node.name}.__class_vars__'
            self.raw_functions[unique_key] = ",".join(class_vars)

        self.data["classes"][node.name]["class_vars"] = list(class_vars)

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


def extract_ast_code_structure(source: str, file_path: str, project_root: str) -> tuple[dict[str, Any], dict[str, str]]:
    tree, used_source = parse_python_source(source, file_path)

    if tree is None:
        logger.warning(f"File {file_path} is skipped: can't process AST.")
        return {"imports": [], "classes": {}, "functions": []}, {}

    extractor = CodeExtractor(
        project_root=project_root,
        file_content=used_source,
        file_path=file_path,
    )
    extractor.visit(tree)
    return extractor.data, extractor.raw_functions


def extract_project_ast_code_structure(updated_files=None) -> None:
    target_dir = "/app/data"  # docker-relative folder

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


def merge_ast_and_docs(ast_functions_path, described_functions_path, rag_functions_path) -> None:
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


def run_2to3(source: str, file_path: str) -> str | None:
    """Converts code from Python 2 to Python 3. Returns text or None"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as tmp:
        tmp.write(source)
        tmp_path = tmp.name

    try:
        subprocess.run(
            [sys.executable, "-W", "ignore", "-m", "lib2to3", "-w", "-n", "--no-diffs", tmp_path],
            capture_output=True, check=True, text=True,
        )
        with open(tmp_path, 'r', encoding='utf-8') as f:
            return f.read()
    except subprocess.CalledProcessError as e:
        last_line = e.stderr.strip().splitlines()[-1] if e.stderr and e.stderr.strip() else ""
        logger.info(f"2to3 failed for {file_path}: {last_line}")
        return None
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def parse_python_source(source: str, file_path: str) -> tuple[ast.Module | None, str]:
    """
    Returns (tree, source).
    1. Parses Python 3 code.
    2. In failure, sends it to 2to3.
    3. In failure, converts tabs to spaces Python 2 (1 tab = 8 spaces) and runs 2to3 again.
    If nothing works, returns (None, source).
    """
    source = textwrap.dedent(source)

    try:
        return ast.parse(source), source
    except SyntaxError:
        pass

    for candidate in (source, source.expandtabs(8)):
        converted = run_2to3(candidate, file_path)
        if converted is None:
            continue

        converted = converted.replace('async=', 'is_async=').replace('async =', 'is_async =')

        try:
            return ast.parse(converted), converted
        except SyntaxError as e:
            logger.info(f"Converted code of {file_path} still doesn't parse: {e}")

    logger.error(f"Fatal parse error in {file_path}: can't convert to Python 3")
    return None, source


def parse_code_safely(source: str, file_path: str) -> ast.Module | None:
    tree, _ = parse_python_source(source, file_path)
    return tree


def extract_functions_from_file(abs_path: str, rel_path: str, target_dir: str) -> tuple[dict, dict]:
    """Возвращает (ast_data, raw_functions)."""
    source = read_file_safely(abs_path)

    try:
        ast_data, raw_functions = extract_ast_code_structure(source, rel_path, target_dir)
    except SyntaxError as e:
        logger.warning(f"Error in {rel_path}: {e}")
        return {}, {}

    return ast_data, raw_functions


def find_called_functions_in_code(code: str) -> list[str]:
    """Возвращает имена функций, которые вызываются внутри кода."""
    try:
        tree = ast.parse(textwrap.dedent(code))
    except SyntaxError:
        return []

    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name): # functions
                names.append(node.func.id)
            elif isinstance(node.func, ast.Attribute):  # attributes
                names.append(node.func.attr)
    return names


def extract_class_attributes(target_key: str, target_code: str, all_functions: dict, all_ast: dict) -> tuple[set, set]:
    """ Attributes handling. """
    file_path, name = target_key.rsplit("::", 1)
    known_attrs: set[str] = set()
    used_attrs: set[str] = set()

    if "." not in name: # if it's not a class
        return known_attrs, used_attrs

    cls_name = name.split('.')[0]

    # 1. Достаем переменные уровня класса из AST
    file_ast = all_ast.get(file_path, {})
    cls_info = file_ast.get("classes", {}).get(cls_name, {})
    known_attrs.update(cls_info.get("class_vars", []))

    # 2. Достаем переменные из методов (self.x = ...)
    class_prefix = f"{file_path}::{cls_name}."
    for key, code in all_functions.items():
        if not key.startswith(class_prefix):
            continue
        known_attrs.add(key[len(class_prefix):])
        try:
            tree = ast.parse(textwrap.dedent(code))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                    and node.value.id == "self" and isinstance(node.ctx, ast.Store)):
                known_attrs.add(node.attr)

    # 3. Что читает проверяемая функция через self.x
    try:
        for node in ast.walk(ast.parse(textwrap.dedent(target_code))):
            if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                    and node.value.id == "self" and isinstance(node.ctx, ast.Load)):
                used_attrs.add(node.attr)
    except SyntaxError:
        pass

    return known_attrs, used_attrs
