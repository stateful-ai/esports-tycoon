# Troubleshooting

## 'pytest' is not found
Activate the project venv first or run via `./.venv/bin/python -m pytest`.

## Halftime narration looks generic
Templated default is in effect — check that the LLM backend is enabled
in the content adapter config (`esports_tycoon.content.config`).

## Tests fail after pulling main
The constraints lockfile may have drifted — re-run `pip install -r constraints.txt`.

## Save file rejected on load
Schema-version mismatch. Check the version stamp at the top of the YAML
and migrate if needed via the codepath in `esports_tycoon.saves`.
