- `summary`: retain `actions/ai-inference` `@v2` pin permanently to preserve custom endpoint support.
  Evaluation in gha#835 confirmed upstream v3 removed configurable OpenAI-compatible endpoint support
  in favor of a Copilot-CLI-only provider requiring extra credentials and installation steps.
  The `@v2` pin is preserved permanently so callers can continue to supply their own `endpoint`, `model`, and `API_KEY`.
