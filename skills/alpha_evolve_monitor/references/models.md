# Generation Models

`--models` passes model names straight through to the AlphaEvolve API, which
validates them. Use the API **model name** (e.g. `gemini-3.5-flash`), not the
old preset enum. The legacy singular `model` flag is **deprecated** — use
`--models`.

## Syntax

`--models` is repeatable (one flag per model). Each value is either a bare name
or a comma-separated `key=value` spec:

```bash
# Single model (weight defaults to 1.0)
--models gemini-3.5-flash

# Weighted mixture (relative weights)
--models name=gemini-3.5-flash,weight=0.9 \
  --models name=gemini-3.1-pro-preview,weight=0.1
```

Same syntax on `ae config --models=...` and `ae experiment create --models ...`.

## Recommended models

Model name               | Regions        | Notes
------------------------ | -------------- | ------------------------------
`gemini-3.5-flash`       | global, us, eu | Recommended default
`gemini-3.1-pro-preview` | global         | Higher quality; mix with flash


## Notes

-   `weight` is optional and **relative** (ratios, not sum-to-1); omit it for a
    single model — the API defaults a missing weight to 1.0.
-   At most two models may be combined in one experiment.
-   Model names and weights are validated by the API (it returns
    `INVALID_ARGUMENT` for an unknown name or unavailable region). The CLI keeps
    no model allowlist of its own, so it never goes stale.
