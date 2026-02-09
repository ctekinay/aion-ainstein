"""
Pytest configuration and fixtures for AION-AINSTEIN tests.

This conftest.py handles:
- Mocking the elysia package (which requires spacy download) for unit tests
- Setting up common fixtures for tests
"""

import sys
from unittest.mock import MagicMock

# =============================================================================
# Mock elysia package to avoid spacy download issues
# =============================================================================

# Create mock elysia module and its submodules BEFORE any test imports
mock_elysia = MagicMock()
mock_elysia.tool = MagicMock()
mock_elysia.Tree = MagicMock()

# Insert into sys.modules before any imports happen
sys.modules['elysia'] = mock_elysia
sys.modules['elysia.tree'] = MagicMock()
sys.modules['elysia.tree.tree'] = MagicMock()
sys.modules['elysia.tree.objects'] = MagicMock()
sys.modules['elysia.config'] = MagicMock()

# Also mock spacy to prevent any remaining import issues
mock_spacy = MagicMock()
mock_spacy.cli = MagicMock()
mock_spacy.cli.download = MagicMock()
sys.modules['spacy'] = mock_spacy
sys.modules['spacy.cli'] = mock_spacy.cli

import pytest
from pathlib import Path


@pytest.fixture
def project_root():
    """Return the project root directory."""
    return Path(__file__).parent.parent


@pytest.fixture
def test_data_dir(project_root):
    """Return the test data directory."""
    return project_root / "tests" / "data"
