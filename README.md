# AST RAG Analyzer
![CI](https://github.com/mrpaulpopov/ast-rag-analyzer/actions/workflows/ci.yml/badge.svg) [Русская версия](README.ru.md) | English version

This project is an AI code reviewer designed to analyze a Python codebase. Based on a RAG architecture, the system:
- Extracts code structures via AST parsing (with a fallback mechanism for Python 2).
- Generates docstrings for each function via LLM.
- Encodes and stores docstring information (the meaning and purpose of the function) via embeddings in PostgreSQL. This builds a searchable knowledge base of project imports, classes, and function docstrings.


During inference, the pipeline collects:
- **Related functions from the RAG database**.
- Other functions from submitted files.
- Variables and attributes.
- Return statement counts.

This ensures the detection of **scope errors, structural mismatches, and invalid calls**.

Finally, the assembled context is sent as a prompt to a local LLM (e.g., Qwen2.5-Coder).

## Data Flow Diagrams

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/DFD_Dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="docs/DFD_Light.svg">
  <img alt="Training Data Flow Diagram" src="docs/DFD_Light.svg" width="100%">
</picture>

## Detection Examples

I intentionally injected structural and logic bugs into a repository to test the analyzer. Here are examples (red change is the original version, green change is the injected bug):

### 1. Out of Scope Error
The AI detects when a variable might remain unassigned if a specific condition isn't met.

```diff
if not good_precisions.empty:
    # Sort Recall in descending order and get the first (maximum) row
    best_row = good_precisions.sort_values(by='recall', ascending=False).iloc[0]
    best_business_threshold = best_row['threshold']
    logger.info(f"Business Target Precision {business_target_precision} achieved at threshold: {best_business_threshold}")
- else:
-   best_business_threshold = best_f1_threshold  # fallback
-   logger.warning("Business Target Precision is unreachable. Using best f1 threshold.")

client.log_param(run_id, "best_business_threshold", best_business_threshold)
```
#### Response

```jsonc
{
  "step0_diff_analysis": {
    "code_changes": "The main change is the removal of the fallback mechanism for `best_business_threshold` when `good_precisions` is empty. The previous version used `best_f1_threshold` as a fallback, while the current version does not handle this case explicitly.",
    "signature_and_returns_diff": "No"
  },
  "step1_scope_analysis": {
    "variables_assigned_in_if_or_try_blocks": [
      "best_business_threshold"
    ],
    "missing_else_or_except_blocks": "Yes, there is no `else` block to handle the case when `good_precisions` is empty. This could lead to `best_business_threshold` being undefined if `good_precisions` is empty.",
    "typo_check": "None"
  },
// ...
  "verdict_status": "FAIL",
  "issue_description": "The function does not handle the case when `good_precisions` is empty, leading to `best_business_threshold` being undefined. This could cause a runtime error."
}
```

### 2. Error in Function Signatures
The AI can either compare the old and the new versions to find a change in the expected arguments or check the related function in the RAG context to find the missing parameters.

```diff
def lightgbm_model(train_data: lgb.Dataset, valid_data: lgb.Dataset, params: dict[str, Any]) -> lgb.Booster:
...

def training_lgbm(train_data: lgb.Dataset, valid_data: lgb.Dataset, lgbm_params: dict[str, Any]) -> lgb.Booster:
    start = time.time()
-    model = lightgbm_model(train_data, valid_data, lgbm_params)
+    model = lightgbm_model(train_data, valid_data)
    
    mlflow.lightgbm.log_model(model, name="model")
    mlflow.log_metric("lgbm_best_iteration", model.best_iteration)
    logger.info(f"Training completed in {time.time() - start:.4f}s")
    
    model.save_model(LGBM_MODEL_PATH, num_iteration=model.best_iteration)
    logger.info(f"Model saved to {LGBM_MODEL_PATH}")
    return model
```
#### Response

```jsonc
{
  "step0_diff_analysis": {
    "code_changes": "The `training_lgbm` function now calls `lightgbm_model` without passing the `lgbm_params` argument.",
    "signature_and_returns_diff": "No, the number of expected arguments or the number of returned elements did not change."
  },
// ...
  "step2_signature_and_returns_analysis": {
    "target_return_elements_count": "return model",
    "returns_internally_consistent": "Yes",
    "target_expected_args_count": "3",
    "caller_line_exact_match": "model_lgbm = training_lgbm(train_data, valid_data, config[\"lgbm_params\"])",
    "caller_unpacked_vars_count": "1",
    "caller_passed_args_count": "3",
    "counts_match_or_breaking_change": "No"
  },
  "step3_calls_validation": {
    "internal_calls_match": "No, `lightgbm_model` is called without the `params` argument.",
    "external_libraries_check": "None",
    "issues_found": "The `lightgbm_model` function expects a `params` argument, but it is not provided in the `training_lgbm` function."
  },
  "verdict_status": "FAIL",
  "issue_description": "The `lightgbm_model` function expects a `params` argument, but it is not provided in the `training_lgbm` function. This will cause a TypeError."
}
```

### 3. Missing Library Method
The AI uses its internal knowledge of PyTorch to catch methods that don't exist, which simple AST parsers or regex would miss.

```diff
- optimizer.zero_grad()
+ optimizer.clear_gradients()
...
- X_val_batch = X_val_batch.to(device)
+ X_val_batch = X_val_batch.send_to(device)
```
#### Response

```jsonc
{
  "step0_diff_analysis": {
    "code_changes": "The main changes between the previous version and the target function code are: 1) The method `optimizer.zero_grad()` was replaced with `optimizer.clear_gradients()`, which does not exist in PyTorch. 2) The method `X_val_batch.send_to(device)` was replaced with `X_val_batch.to(device)`, which is the correct method to move tensors to a device in PyTorch.",
    "signature_and_returns_diff": "No, the number of expected arguments and the number of returned elements did not change."
  },
// ...
  "step3_calls_validation": {
    "internal_calls_match": "Yes",
    "external_libraries_check": "The method `send_to` does not exist in PyTorch. The correct method is `to`. The method `optimizer.clear_gradients()` does not exist in PyTorch. The correct method is `zero_grad`.",
    "issues_found": "The method `send_to` does not exist in PyTorch. The correct method is `to`. The method `optimizer.clear_gradients()` does not exist in PyTorch. The correct method is `zero_grad`."
  },
  "verdict_status": "FAIL",
  "issue_description": "The method `send_to` does not exist in PyTorch. The correct method is `to`. The method `optimizer.clear_gradients()` does not exist in PyTorch. The correct method is `zero_grad`."
}
```

### 4. Breaking Changes in Returns
By comparing the new code with the old version, the AI catches the bug even if the caller function isn't provided in the RAG context.

```diff
- return str(transaction["TransactionID"]), is_fraud, fraud_probability, reason
+ return str(transaction["TransactionID"]), is_fraud, fraud_probability
```
#### Response

```jsonc
{
  "step0_diff_analysis": {
    "code_changes": "The previous version of the function included a return statement with four elements: transaction ID, is_fraud, fraud_probability, and reason. The target function now returns only three elements: transaction ID, is_fraud, and fraud_probability.",
    "signature_and_returns_diff": "Yes. The number of returned elements changed from 4 to 3."
  },
 // ...
  "step2_signature_and_returns_analysis": {
    "target_return_elements_count": [
      "return str(transaction[\"TransactionID\"]), is_fraud, fraud_probability"
    ],
    "returns_internally_consistent": "Yes. All return statements output the exact same number of elements.",
    "target_expected_args_count": "3",
    "caller_line_exact_match": "NOT FOUND",
    "caller_unpacked_vars_count": "N_A",
    "caller_passed_args_count": "N_A",
    "counts_match_or_breaking_change": "N_A. The caller line is not found, so we cannot verify the safe update."
  },
// ...
  "verdict_status": "FAIL",
  "issue_description": "The number of returned elements changed from 4 to 3, which is a breaking change. The caller line is not found, so we cannot verify the safe update."
}
```

## Limitations
1. Manual execution: The inference pipeline currently supports only manual file selection for analysis. There's no automated Git or CI integration.
2. Context dependency: If the RAG fails to find relevant context, the `[EXISTING RELATED FUNCTIONS FROM REPO]` section will be empty and an LLM query will lack context.
3. Attention degradation: If the generated prompt consists of thousands of lines of code, a 14B model will lose the attention.

## Possible Improvements
1. CI/CD Integration: The inference pipeline should be integrated directly into a CI pipeline to execute automatically on every commit or pull request.
2. AI Agents: The final prompt texts can be sent to AI agents: they have a much higher Precision/Recall ratio compared to a local LLM.

## How to Run

#### First Launch (Run Docker Containers, Download Models)
```
docker compose up -d
```

#### Training, Update, Inference Launch (with GPU)
```
docker compose -f docker-compose.yml -f docker-compose.gpu.yml run --rm --build app python src/pipelines/training_pipeline.py
docker compose -f docker-compose.yml -f docker-compose.gpu.yml run --rm --build app python src/pipelines/update_pipeline.py
docker compose -f docker-compose.yml -f docker-compose.gpu.yml run --rm --build app python src/pipelines/inference_pipeline.py
```

#### Adminer Interface (Explore Database)
```
localhost:8080
```

#### Delete All (Database and Downloaded Models)
```
docker compose down -v
```
