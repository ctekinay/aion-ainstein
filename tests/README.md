# Implementation Quality Tests

Comprehensive test suite for validating the transparency-first retrieval implementation.

## What It Tests

### Test Suite 1: Skills Injection ✅
- Base agent description exists and is properly configured
- Elysia Tree initialized with agent description
- Skills dynamically injected for "list" queries
- Response formatting (numbered lists, statistics, follow-ups)

### Test Suite 2: DAR Filtering ✅
- Decision Approval Records properly excluded from "list all" queries
- ADR count in expected range (18-20 without DARs, or 54-60 with chunking)
- No DAR indicators (e.g., "ADR.21D") in responses

### Test Suite 3: Principle Number Extraction ✅
- Principle numbers populated in at least 80% of documents
- Specific principle queries work (e.g., "What is PCP.10?")
- Principle numbering consistent in chunked mode

### Test Suite 4: Chunking Quality ✅
- Detects if chunking is enabled (checks for section suffixes in titles)
- Section-specific queries return relevant content only
- Precision improvement with chunked retrieval

### Test Suite 5: Transparency & Counts ✅
- Responses include "X of Y" or "X total" transparency indicators
- Collection count accuracy (actual count matches mentioned count)
- Proper transparency even when results are truncated

---

## Usage

### Quick Test (with re-ingestion)
```bash
# From project root
python tests/test_implementation_quality.py
```

This will:
1. Re-ingest all data with chunking enabled (~2-3 minutes)
2. Run all 5 test suites
3. Display pass/fail results
4. Exit with code 0 (all pass) or 1 (some fail)

### Fast Test (skip re-ingestion)
```bash
# Use existing data (faster, but may not reflect latest changes)
python tests/test_implementation_quality.py --skip-ingestion
```

### Save Results to JSON
```bash
python tests/test_implementation_quality.py --output results.json
```

---

## Expected Output

```
╭─────────────────────────────────────────────╮
│ Test Harness                                │
│                                             │
│ AION-AINSTEIN Implementation Quality Tests  │
│                                             │
│ Validates: Skills injection, DAR filtering, │
│ chunking, principle numbers, transparency   │
╰─────────────────────────────────────────────╯

Setting up test environment...
✓ Environment ready

╭─────────────────────────────────────╮
│ Test Suite 1: Skills Injection     │
╰─────────────────────────────────────╯
  ✓ Base description configured
  ✓ Tree properly initialized
  ✓ Response has rich formatting (latency: 8234ms)

╭─────────────────────────────────────╮
│ Test Suite 2: DAR Filtering        │
╰─────────────────────────────────────╯
  ✓ DARs properly excluded (found 18 ADRs, latency: 9133ms)
  ✓ Found 54 ADR objects

... (more test output) ...

╭──────────────╮
│ Test Summary │
╰──────────────╯
┏━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━┓
┃ Suite                ┃ Tests ┃ Passed ┃ Failed ┃ Pass Rate ┃ Status ┃
┡━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━┩
│ Skills Injection     │     3 │      3 │      0 │    100.0% │ ✓ PASS │
│ DAR Filtering        │     2 │      2 │      0 │    100.0% │ ✓ PASS │
│ Principle Numbers    │     2 │      2 │      0 │    100.0% │ ✓ PASS │
│ Chunking Quality     │     2 │      2 │      0 │    100.0% │ ✓ PASS │
│ Transparency         │     2 │      2 │      0 │    100.0% │ ✓ PASS │
└──────────────────────┴───────┴────────┴────────┴───────────┴────────┘

Overall: 11/11 tests passed (100.0%)

✓ ALL TESTS PASSED - Implementation validated!
```

---

## Interpreting Results

### ✓ All Tests Pass
- Implementation is validated and production-ready
- Skills are properly injected
- DAR filtering works correctly
- Chunking (if enabled) is functional
- Transparency features working

### ✗ Some Tests Fail

**Common Issues:**

1. **Skills Injection Fails**
   - Check if `_base_agent_description` exists in ElysiaRAGSystem
   - Verify `change_agent_description()` is called before queries
   - Check logs for "Injected skills into Elysia agent description"

2. **DAR Filtering Fails**
   - Verify `build_document_filter()` is called in Elysia tools
   - Check thresholds.yaml has correct exclude_doc_types
   - Expected: 18-20 ADRs (no DARs), or ~54-60 with chunking

3. **Principle Numbers Fail**
   - Check if principle_number extraction is implemented in chunked mode
   - Verify regex `r'(\d{4})'` extracts from filename
   - Look for principle_number field in Weaviate

4. **Chunking Quality Fails**
   - Verify ingestion used `enable_chunking=True`
   - Check if `load_adrs_chunked()` is called
   - Look for titles with " - " suffix (e.g., "ADR.21: Title - Context")

5. **Transparency Fails**
   - Check if `get_collection_count()` is called
   - Verify context includes "COLLECTION COUNTS" section
   - Look for "showing X of Y" in responses

---

## Exit Codes

- `0` - All tests passed ✅
- `1` - Some tests failed ❌

Use in CI/CD:
```bash
python tests/test_implementation_quality.py || exit 1
```

---

## Requirements

- Weaviate running on localhost:8080
- Ollama with nomic-embed-text-v2-moe model
- All dependencies installed (`pip install -r requirements.txt`)
- Data files in `data/` directory

---

## Troubleshooting

### "Elysia not available" Error
```bash
pip install elysia-ai
```

### "Connection refused" Error
```bash
# Start Weaviate
docker compose up -d

# Verify it's running
docker ps | grep weaviate
```

### "No module named 'src'" Error
```bash
# Run from project root, not tests/ directory
cd /path/to/aion-ainstein
python tests/test_implementation_quality.py
```

### Test Timeouts
- Local Ollama models are slow (expect 5-15s per query)
- Tests may take 5-10 minutes total with re-ingestion
- Use `--skip-ingestion` for faster runs during development

---

## Development

### Adding New Tests

```python
async def test_new_feature(self) -> TestSuite:
    """Test description."""
    console.print(Panel("[bold]Test Suite X: Feature Name[/bold]"))
    results = []

    test_name = "X.1 Test Case Name"
    try:
        # Your test logic
        passed = True
        message = "✓ Test passed"
        results.append(TestResult(test_name, passed, message))
        console.print(f"  {message}")
    except Exception as e:
        results.append(TestResult(test_name, False, f"✗ Error: {e}"))
        console.print(f"  ✗ Error: {e}")

    return TestSuite("Feature Name", results)
```

### Running Individual Suites
Modify `run_all_tests()` to comment out suites you don't want to run.

---

## CI/CD Integration

### GitHub Actions Example
```yaml
name: Implementation Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Start Weaviate
        run: docker compose up -d

      - name: Run tests
        run: python tests/test_implementation_quality.py --output results.json

      - name: Upload results
        uses: actions/upload-artifact@v3
        with:
          name: test-results
          path: results.json
```

---

## Contact

For issues or questions about the test suite, refer to the main project documentation or create an issue in the repository.
