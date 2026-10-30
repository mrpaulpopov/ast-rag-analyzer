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
docker-compose down -vtem strictly validates structure and context, not mathematical or business logic. Logic changes, such as using `>` instead of `>=`, will not be detected.
3. RAG-dependency: if the vector se
```

## Limitations
1. Manual execution: The inference pipeline currently supports only manual file selection for analysis. There's no automated Git or CI integration.
2. Blind to business logic: The sysarch fails to find relevant context, the `[EXISTING RELATED FUNCTIONS FROM REPO]` section will be empty and an LLM query will lack context.
4. Attention degradation: If the generated prompt consists of thousands of lines of code, a 14B model will lose the attention.

## Possible Improvements
1. CI/CD Integration: The inference pipeline should be integrated directly into a CI pipeline to execute automatically on every commit or pull request.
2. AI Agents: The final prompt texts can be sent to AI agents: they have a much greater Precision/Recall ratio rather than a local LLM. Routing the final prompts to specialized AI agents rather than a single local LLM could drastically improve the Precision/Recall ratio for complex codebases.


## Bug Detection Example

I intentionally injected structural and logic bugs into a repository.
The **AST RAG Analyzer** successfully caught context-dependent errors.

**1. The Injected Bugs (Scope & Invalid Arguments)**
A variable was left without a default state, and a non-existent argument (`ignore_errors=True`) was passed to a pandas method.

```diff
  if "TransactionID" in df.columns:
      transaction_ids = df["TransactionID"]
- else:
-     transaction_ids = None

  # 2. Drop useless columns
  X = df.drop(columns=["isFraud", "TransactionID", "TransactionDT",
                       "id_24", "id_25", "id_07", "id_08", "id_21",
-                      "uid1", "card1"], ignore_errors=True)
+                      "uid1", "card1"], errors='ignore')

```

```json
{
  "step1_scope_analysis": {
    "variables_assigned_in_if_or_try_blocks": [
      "engine",
      "df",
      "y",
      "transaction_ids",
      "X"
    ],
    "missing_else_or_except_blocks": "The variable `transaction_ids` is assigned inside an `if` block but does not have an `else` block to handle the case where the column does not exist. This is a potential issue as it could lead to a `NameError` if the column is missing.",
    "typo_check": "None"
  },
  "step2_returns_math": {
    "target_return_counts": "return X, y, transaction_ids",
    "caller_line_exact_match": "NOT FOUND",
    "caller_unpacks_count": "N/A",
    "counts_match": "N_A"
  },
  "step3_calls_validation": {
    "internal_calls_match": "None",
    "external_libraries_check": "The call to `pd.read_sql` with `chunksize=50000` is valid. The call to `df.drop` with `ignore_errors=True` is invalid as `ignore_errors` is not a valid argument for `drop` in pandas. The call to `df.select_dtypes` with `include=['float64']` is valid. The call to `X.astype('float32')` is valid.",
    "issues_found": "The call to `df.drop` with `ignore_errors=True` is invalid."
  },
  "verdict_status": "FAIL",
  "issue_description": "The call to `df.drop` with `ignore_errors=True` is invalid. Additionally, the variable `transaction_ids` is assigned inside an `if` block but does not have an `else` block to handle the case where the column does not exist."
}

```



```diff
- client.log_metric(run_id, f"lgbm_{prefix}_accuracy", accuracy_score(y, y_pred))
+ client.log_metric(run_id, f"lgbm_{prefix}_accuracy", accuracy_score(y_pred))
```

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

```json
{
  "step1_scope_analysis": {
    "variables_assigned_in_if_or_try_blocks": [
      "best_business_threshold"
    ],
    "missing_else_or_except_blocks": "The variable `best_business_threshold` is assigned inside an `if` block but not assigned a default value if the condition is not met. This could lead to a `NameError` if `best_business_threshold` is used later in the function without being defined.",
    "typo_check": "None"
  },
  "step2_returns_math": {
    "target_return_counts": "return final_threshold, best_business_threshold, best_f1_threshold",
    "caller_line_exact_match": "final_threshold, business_thr, f1_thr = find_best_threshold(y_val, y_val_prob, business_fp_target, threshold_strategy, run_id)",
    "caller_unpacks_count": "3",
    "counts_match": "Yes"
  },
  "step3_calls_validation": {
    "internal_calls_match": "All internal calls match the quoted signatures perfectly.",
    "external_libraries_check": "All calls to external libraries are valid. The methods and arguments used are correct.",
    "issues_found": "None"
  },
  "verdict_status": "FAIL",
  "issue_description": "The variable `best_business_threshold` is assigned inside an `if` block but not assigned a default value if the condition is not met. This could lead to a `NameError` if `best_business_threshold` is used later in the function without being defined."
}
```



```diff
- return train_data, valid_data, test_data, X_train, X_val, X_test
+ return train_data, valid_data, test_data, X_train, X_val
```

```diff
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




```json
{
  "step1_scope_analysis": {
    "variables_assigned_in_if_or_try_blocks": "None",
    "missing_else_or_except_blocks": "None",
    "typo_check": "None"
  },
  "step2_returns_math": {
    "target_return_counts": "return model",
    "caller_line_exact_match": "model_lgbm = training_lgbm(train_data, valid_data, config[\"lgbm_params\"])",
    "caller_unpacks_count": "1",
    "counts_match": "Yes"
  },
  "step3_calls_validation": {
    "internal_calls_match": "The call to `lightgbm_model` does not match the signature from the related function. The related function expects `params` as an argument, but `lgbm_params` is passed.",
    "external_libraries_check": "None",
    "issues_found": "The call to `lightgbm_model` does not match the expected signature."
  },
  "verdict_status": "FAIL",
  "issue_description": "The call to `lightgbm_model` does not match the expected signature. The related function expects `params` as an argument, but `lgbm_params` is passed."
}
```



```diff
- optimizer.zero_grad()
+ optimizer.clear_gradients()
```

```diff
- X_val_batch = X_val_batch.to(device)
+ X_val_batch = X_val_batch.send_to(device)
```

```diff
logger.info(
    f"Epoch {epoch + 1}/{n_epochs} | "
    f"train_loss={train_loss:.4f} | "
-     f"val_loss={val_loss:.4f} | "
    f"val_rmse={rmse:.4f} | "    
    f"val_mae={mae:.4f}"
)

```



```json
{
  "step1_scope_analysis": {
    "variables_assigned_in_if_or_try_blocks": [
      "best_model_weights",
      "early_stopping",
      "val_loss",
      "rmse",
      "mae"
    ],
    "missing_else_or_except_blocks": "None",
    "typo_check": "None"
  },
  "step2_returns_math": {
    "target_return_counts": "return val_loss",
    "caller_line_exact_match": "val_loss = train_nn_loop(model, train_loader, val_loader, optimizer, loss_fn, n_epochs, trial=trial)",
    "caller_unpacks_count": "1",
    "counts_match": "Yes"
  },
  "step3_calls_validation": {
    "internal_calls_match": "None",
    "external_libraries_check": "The method `send_to` in PyTorch does not exist. It should be `to` instead.",
    "issues_found": "The method `send_to` in PyTorch does not exist. It should be `to` instead."
  },
  "verdict_status": "FAIL",
  "issue_description": "The method `send_to` in PyTorch does not exist. It should be `to` instead."
}
```
