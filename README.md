# AST RAG Analyzer
![CI](https://github.com/mrpaulpopov/ast-rag-analyzer/actions/workflows/ci.yml/badge.svg) [Русская версия](README.ru.md) | English version

This project is an AI code reviewer designed to analyze a Python codebase. Based on a RAG architecture, the system:
1. Extracts code structures via AST parsing (with a fallback mechanism for Python 2).
2. Generates docstrings for each function via LLM.
3. Encodes and stores docstring information (the meaning and purpose of the function) via embeddings in PostgreSQL. This builds a searchable knowledge base of project imports, classes, and function docstrings.


During inference, the pipeline collects:
- **related functions from the RAG database**,
- other functions from submitted files,
- variables and attributes,
- return statement counts.

This guarantees the detection of **scope errors, structural mismatches, and invalid calls**.

Finally, the assembled context is sent as a prompt to a local LLM (e.g., Qwen2.5-Coder).

## Data Flow Diagrams

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/DFD_Dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="docs/DFD_Light.svg">
  <img alt="Training Data Flow Diagram" src="docs/DFD_Light.svg" width="100%">
</picture>

## How to Run

#### First Launch (Run Docker Containers, Download Models)
```
docker-compose up -d
```

#### Training, Update, Inference Launch (with GPU)
```
docker-compose -f docker-compose.yml -f docker-compose.gpu.yml run --rm --build app python src/pipelines/training_pipeline.py
docker-compose -f docker-compose.yml -f docker-compose.gpu.yml run --rm --build app python src/pipelines/update_pipeline.py
docker-compose -f docker-compose.yml -f docker-compose.gpu.yml run --rm --build app python src/pipelines/inference_pipeline.py
```

#### Adminer Interface (Explore Database)
```
localhost:8080
```

#### Delete All (Database and Downloaded Models)
```
docker-compose down -v
```

## Limitations
1. Manual execution: The inference pipeline currently supports only manual file selection for analysis. There's no automated Git or CI integration.
2. Blind to business logic: The system strictly validates structure and context, not mathematical or business logic. Logic changes, such as using `>` instead of `>=`, will not be detected.
3. RAG-dependency: if the vector search fails to find relevant context, the `[EXISTING RELATED FUNCTIONS FROM REPO]` section will be empty and an LLM query will lack context.
4. Attention degradation: If the generated prompt consists of thousands of lines of code, a 14B model will lose the attention.

## Possible Improvements
1. CI/CD Integration: The inference pipeline should be integrated directly into a CI pipeline to execute automatically on every commit or pull request.
2. AI Agents: The final prompt texts can be sent to AI agents: they have a much greater Precision/Recall ratio rather than a local LLM. Routing the final prompts to specialized AI agents rather than a single local LLM could drastically improve the Precision/Recall ratio for complex codebases.