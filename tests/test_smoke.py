"""Smoke tests: the package imports and the configured paths are sane."""
from recipebot import config


def test_project_root_contains_pyproject():
    assert (config.PROJECT_ROOT / "pyproject.toml").is_file()


def test_data_paths_are_inside_project():
    for path in (config.RAW_DIR, config.DB_PATH, config.INDEX_DIR, config.TAXONOMY_DIR):
        assert config.PROJECT_ROOT in path.parents


def test_understanding_backend_is_valid():
    assert config.UNDERSTANDING_BACKEND in config.VALID_BACKENDS
