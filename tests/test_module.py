"""
This python module defines tests for pytest

run `pytest -v` at the root to get results
"""

import os.path
import sys

import pytest

ret_code_isort = pytest.main(["--isort"])
ret_code_flakes = pytest.main(["--flakes"])

EXPECTED_ERROR_COUNT = 2

# add module folder to import paths for testing local src
sys.path.append(
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
)
# reverse the order so we make sure to get the local src module, not pip package
sys.path.reverse()

import validate_bes_xml  # pylint: disable=import-error,wrong-import-position


def test_module_location():
    """check for only 'src' so it will work on windows and non-windows"""
    assert "src" in validate_bes_xml.__file__


def test_schemas_found():
    """must be 4 valid schema files:"""
    assert len(validate_bes_xml.validate_bes_xml.find_schema_files()) == 4


def test_examples():
    """should be EXPECTED_ERROR_COUNT errors currently:"""
    assert (
        validate_bes_xml.validate_bes_xml.validate_all_files() == EXPECTED_ERROR_COUNT
    )


def test_main():
    """test main exit code = EXPECTED_ERROR_COUNT"""
    with pytest.raises(SystemExit) as wrapped_error:
        validate_bes_xml.validate_bes_xml.main()
    # https://medium.com/python-pandemonium/testing-sys-exit-with-pytest-10c6e5f7726f
    assert wrapped_error.value.code == EXPECTED_ERROR_COUNT


def test_validate_xml():
    """test single xml files"""
    assert (
        validate_bes_xml.validate_bes_xml.validate_xml(
            "tests/examples/good/FixletDebugger.bes"
        )
        is True
    )
    assert (
        validate_bes_xml.validate_bes_xml.validate_xml(
            "tests/examples/bad/example_bes.bes"
        )
        is False
    )


def test_isort():
    """test isort results"""
    assert ret_code_isort == 0


def test_flakes():
    """test pyflakes results"""
    assert ret_code_flakes == 0
