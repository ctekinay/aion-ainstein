# AInstein Test Gates
#
# Usage:
#   make test-unit        Pre-commit: pure-logic tests, no services (<30s)
#   make test-functional  Pre-push: needs Weaviate + Ollama (~3-4 min)
#   make test-full        CI/nightly: everything including benchmarks (~10-15 min)
#   make test             Alias for test-unit

.PHONY: test test-unit test-functional test-full

test: test-unit

test-unit:
	pytest -m "not functional and not ingestion and not generation and not benchmark" \
		--timeout=30 -q

test-functional:
	pytest -m "functional or ingestion or generation" \
		--timeout=60 -v

test-full:
	pytest --timeout=120 -v
