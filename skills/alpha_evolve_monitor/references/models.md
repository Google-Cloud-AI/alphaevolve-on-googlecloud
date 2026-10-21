# Generation Models

`--models` passes model names straight through to the AlphaEvolve API, which
validates them. Use the API **model name** (e.g. `gemini-3.5-flash`), not the
old preset enum. The legacy singular `model` flag is **deprecated** — use
`--models`.

## Default: leave `--models` unset

When neither `--models` nor a profile `[[models]]` section is set, the CLI sends
no model and the API applies its default. The AlphaEvolve team moves that
default to newer GA Gemini models as they are released, so experiments get a
newer Gemini without any skill or CLI change. The "Default model" table in the
AlphaEvolve API reference lists which model applies on which date. The create
response shows the model an experiment got, in `generationSettings.models`. Pin
a model only when the user asks for a specific one or for lower cost.

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
------------------------ | -------------- | -----------------------------------
`gemini-4-argon`         | global, us, eu | Strongest Gemini
`gemini-3.5-flash`       | global, us, eu | Faster and cheaper; high throughput
`gemini-3.1-pro-preview` | global         | Older Pro; mix with flash


## Notes

-   `weight` is optional and **relative** (ratios, not sum-to-1); omit it for a
    single model — the API defaults a missing weight to 1.0.
-   At most two models may be combined in one experiment.
-   Model names and weights are validated by the API (it returns
    `INVALID_ARGUMENT` for an unknown name or unavailable region). The CLI keeps
    no model allowlist of its own, so it never goes stale.
