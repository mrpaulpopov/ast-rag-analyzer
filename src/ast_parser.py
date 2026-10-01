import ast
import json
import os
import logging
import sys
from src.paths import AST_PATH, ALL_RAW_FUNCTIONS, IGNORED_DIRS
from collections.abc import Iterator

logger = logging.getLogger(__name__)


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



def iter_python_files(target_dir: str) -> Iterator[str]:
    for root, dirs, files in os.walk(target_dir):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]

        for file in files:
            if file.endswith('.py') and not file.startswith('_'):
                yield os.path.join(root, file)


def extract_ast_code_data(source: str, file_path: str, project_root: str):
    tree = ast.parse(source)
    extractor = CodeExtractor(
        project_root=project_root,
        file_content=source,
        file_path=file_path,
    )
    extractor.visit(tree)
    return extractor.data, extractor.raw_functions


def extract_ast_project_data(target_dir: str) -> tuple[dict, dict]:
    ast_dict = {}
    raw_functions = {}

    for file_path in iter_python_files(target_dir):
        with open(file_path, "r", encoding="utf-8") as f:
            source = f.read()

        try:
            ast_data, raw = extract_ast_code_data(source, file_path, target_dir)
        except SyntaxError as e:
            logger.warning(f'Error in {file_path}: {e}')
            continue

        ast_dict[file_path] = ast_data
        raw_functions.update(raw)
    logger.info("AST Parsing Complete")
    return ast_dict, raw_functions
