import ast
import json
import os
import logging
import sys
from src.paths import AST_PATH, ALL_RAW_FUNCTIONS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    stream=sys.stdout
)

logger = logging.getLogger(__name__)

raw_functions = {}

class CodeExtractor(ast.NodeVisitor):
    def __init__(self, project_root, file_content, file_path):
        self.data = {
            "imports": [],
            "classes": {},
            "functions": []
        }
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
        raw_functions[unique_key] = raw_code
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node):
        self.visit_FunctionDef(node)



def ast_parsing(target_dir):
    final_data = {}

    for root, dirs, files in os.walk(target_dir):
        dirs[:] = [d for d in dirs if d not in ['.venv', '__pycache__']]

        for file in files:
            if file.endswith('.py') and not file.startswith('_'):
                full_path = os.path.join(root, file)
                with open(full_path, "r", encoding="utf-8") as f:
                    file_content = f.read()
                    try:
                        tree = ast.parse(file_content)
                        visitor = CodeExtractor(project_root=target_dir, file_content=file_content, file_path=full_path)
                        visitor.visit(tree)

                        final_data.update({full_path: visitor.data})
                    except SyntaxError as e:
                        print(f'Error in {full_path}: {e}')

    json_str = json.dumps(final_data, indent=4)
    with open(AST_PATH, "w") as f:
        f.write(json_str)

    with open(ALL_RAW_FUNCTIONS, "a") as f:
        f.write(raw_functions)

    logger.info("AST Parsing Complete")
    logger.info("Starting Ollama...")

if __name__ == '__main__':
    ast_parsing('/Users/paul/PycharmProjects/online-payment-fraud-detection')





