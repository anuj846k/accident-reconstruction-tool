# Oumi Open Source Bug Report: `model_kwargs` Not Passed to `from_pretrained()`

## Issue Summary

`model_params.model_kwargs` (including `cache_dir`, `local_files_only`, etc.) are **not passed** to `transformers_model_class.from_pretrained()` in Oumi's `build_huggingface_model()` function, causing unnecessary model downloads and ignoring cache settings.

## Location

**File:** `oumi/builders/models.py`  
**Function:** `build_huggingface_model()`  
**Lines:** 264-300

## Current Behavior (Bug)

### Line 268 - `model_kwargs` IS used for config loading:
```python
hf_config = find_model_hf_config(
    model_params.model_name,
    trust_remote_code=model_params.trust_remote_code,
    revision=model_params.model_revision,
    **model_params.model_kwargs,  # ✅ Used here
)
```

### Line 291-300 - `model_kwargs` is NOT passed to model loading:
```python
if model_params.load_pretrained_weights:
    model = transformers_model_class.from_pretrained(
        config=hf_config,
        torch_dtype=torch_dtype,
        device_map=device_map,
        trust_remote_code=model_params.trust_remote_code,
        pretrained_model_name_or_path=model_params.model_name,
        quantization_config=quantization_config,
        attn_implementation=model_params.attn_implementation,
        revision=model_params.model_revision,
        **kwargs,  # ❌ model_kwargs NOT included!
    )
```

## Expected Behavior

`model_params.model_kwargs` should be merged into the `from_pretrained()` call so that parameters like `cache_dir`, `local_files_only`, etc. are properly passed to transformers.

## Impact

1. **Cache settings ignored**: `cache_dir` specified in `model_kwargs` is not used during model loading
2. **Unnecessary downloads**: `local_files_only=True` is ignored, causing downloads even when models are cached
3. **Other `model_kwargs` ignored**: Any custom kwargs passed via `ModelParams.model_kwargs` are not applied to model loading

## Reproduction Steps

```python
from oumi.core.configs import ModelParams
from oumi.inference import NativeTextInferenceEngine

# Set model_kwargs with cache settings
model_params = ModelParams(
    model_name="Qwen/Qwen2-VL-2B-Instruct",
    model_kwargs={
        "cache_dir": "/path/to/cache",
        "local_files_only": True,  # Should prevent downloads
    }
)

# Even with local_files_only=True, model will try to download
engine = NativeTextInferenceEngine(model_params)
```

**Expected:** Model loads from cache without downloading  
**Actual:** Model attempts to download from HuggingFace Hub

## Expected Fix

Merge `model_params.model_kwargs` into the `from_pretrained()` call:

```python
if model_params.load_pretrained_weights:
    model = transformers_model_class.from_pretrained(
        config=hf_config,
        torch_dtype=torch_dtype,
        device_map=device_map,
        trust_remote_code=model_params.trust_remote_code,
        pretrained_model_name_or_path=model_params.model_name,
        quantization_config=quantization_config,
        attn_implementation=model_params.attn_implementation,
        revision=model_params.model_revision,
        **{**model_params.model_kwargs, **kwargs},  # ✅ Merge model_kwargs with kwargs
    )
```

## Workaround (Current Implementation)

Since we cannot modify Oumi's internal code, we use the **direct snapshot path** as `model_name` when cache exists:

```python
# Instead of: model_name="Qwen/Qwen2-VL-2B-Instruct"
# Use: model_name="/path/to/cache/models--Qwen--Qwen2-VL-2B-Instruct/snapshots/<commit-hash>"
```

This forces Oumi to load from the local filesystem path instead of trying to download from HuggingFace Hub.

## Environment

- **Oumi version:** (check with `pip show oumi`)
- **Python version:** 3.9
- **Transformers version:** (check with `pip show transformers`)
- **OS:** macOS (M4)

## Additional Context

This issue affects users who:
- Use external storage (SSD) for model cache
- Want to force local-only loading (`local_files_only=True`)
- Need to pass custom kwargs to `from_pretrained()`

The issue is in the Oumi library code, not user code. The `model_kwargs` parameter should be passed through to the transformers model loading call.

## Related Code

### Our Implementation (Workaround)
See: `src/services/oumi_vlm.py` - `_initialize()` method

### Oumi Source Code
File: `venv/lib/python3.9/site-packages/oumi/builders/models.py`  
Function: `build_huggingface_model()` (lines 228-320)

## GitHub Issue Template

When reporting to Oumi's GitHub:

```markdown
## Bug: model_kwargs not passed to from_pretrained()

### Description
`ModelParams.model_kwargs` are not passed to `transformers_model_class.from_pretrained()` in `build_huggingface_model()`, causing cache settings and other kwargs to be ignored.

### Code Location
`oumi/builders/models.py:291-300`

### Expected Behavior
`model_kwargs` should be merged into `from_pretrained()` call.

### Actual Behavior
Only `**kwargs` is passed, ignoring `model_params.model_kwargs`.

### Reproduction
[Use reproduction steps above]

### Proposed Fix
[Use expected fix above]
```

## Status

- **Bug Reported:** Not yet (to be reported to Oumi GitHub)
- **Workaround Implemented:** Yes (in `src/services/oumi_vlm.py`)
- **Workaround Status:** Working (uses direct snapshot path when cache exists)

