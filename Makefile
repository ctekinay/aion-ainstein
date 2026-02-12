# AION-AINSTEIN Makefile
# Common development targets

.PHONY: rollback-map test test-routing test-chunking help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

rollback-map: ## Regenerate docs/dev/rollback_map.md
	bash scripts/dev/commit_overview.sh

test: ## Run all unit tests
	python -m pytest tests/ -v --tb=short

test-routing: ## Run routing-related tests
	python -m pytest tests/test_intent_router.py tests/test_routing_policy_flags.py -v --tb=short

test-chunking: ## Run chunking experiment tests
	python -m pytest tests/test_full_doc_indexing.py tests/test_experiment_report_generation.py -v --tb=short
