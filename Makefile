# esports-tycoon — developer entrypoints.
#
# `make test` is the canonical, zero-API test command this repo runs in CI
# (`.github/workflows/ci.yml`). It must stay green from a clean clone with no
# API key, and it must fail the build if the committed goldens drift — those
# are the two acceptance bars; everything else here exists to support them.
#
# Defaults can be overridden on the command line:
#   make test PYTHON=python3.11
#   make install PIP_EXTRAS=".[dev,web,vllm]"
PYTHON ?= python3
PIP_EXTRAS ?= .[dev,web]
# The byte-identity contract on the canonical save (``saves/SCHEMA.md``) requires
# the same pydantic / PyYAML / transitive deps on every checkout. ``make install``
# resolves every package through this file (``pip install -c …``), so a clean
# clone on a contributor box, a second machine, or the CI image gets the exact
# set of versions used to bless the committed goldens. Bump alongside a reviewed
# regeneration of the goldens.
CONSTRAINTS ?= constraints.txt

# Empty PYTEST_ARGS lets `make test PYTEST_ARGS="-x -k golden"` drill in on a
# failing run without editing this file.
PYTEST_ARGS ?=

.PHONY: help install test test-golden golden-update clean

help:  ## Show available targets
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-16s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install:  ## Install the package + dev/web extras (no API keys, no GPU needed)
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -c "$(CONSTRAINTS)" -e "$(PIP_EXTRAS)"

# `make test` is what CI runs on every commit. It explicitly unsets
# UPDATE_GOLDEN so a stray export in the developer's shell can never silently
# bless drifted goldens; CI fails the build the moment the committed bytes
# don't match what the engine produces.
test:  ## Run the full test suite (golden + round-trip enforced; no API key required)
	UPDATE_GOLDEN= $(PYTHON) -m pytest $(PYTEST_ARGS)

test-golden:  ## Run only the golden + round-trip determinism tests
	UPDATE_GOLDEN= $(PYTHON) -m pytest tests/test_golden_determinism.py $(PYTEST_ARGS)

# Intended-change escape hatch. Re-emits the committed goldens from the current
# engine output; the diff must be reviewed before commit. Never invoked in CI.
golden-update:  ## Rewrite committed goldens from current engine output (review the diff)
	UPDATE_GOLDEN=1 $(PYTHON) -m pytest tests/test_golden_determinism.py $(PYTEST_ARGS)

clean:  ## Remove caches and build artifacts
	rm -rf build dist *.egg-info .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
