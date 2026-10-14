"""
Characterization tests for ValidationResult (issue #17, step 1).

These pin what validate_bes(), validate_xml() and ValidationResult do in 2.2.1,
so adding fields to ValidationResult cannot change the existing ones.

tests/conftest.py puts the local src first on sys.path.
"""

import concurrent.futures
import dataclasses
import os.path

import pytest
from example_paths import BAD_EXAMPLES_DIR, GOOD_BES
from result_cases import CASE_IDS, CASES

import validate_bes_xml  # pylint: disable=import-error

# case_id: (valid, schema file name, line of errors[0], substring of errors[0])
# a line of "no errors" means errors is empty
EXPECTED = {
    "valid_bes": (True, "BES.xsd", "no errors", None),
    "schema_invalid": (False, "BES.xsd", 1, "Nope"),
    "empty_bytes": (False, None, 1, "Document is empty"),
    "whitespace_only": (False, None, 2, "Start tag expected"),
    "comment_only": (False, None, 1, "Start tag expected"),
    "pi_only": (False, None, 1, "Start tag expected"),
    "truncated": (False, None, 1, "Premature end of data"),
    "bogus_encoding": (False, None, 1, "bogus"),
    "undefined_entity": (False, None, 1, "nope"),
    "external_entity": (False, None, 2, "'x'"),
    "unknown_root": (
        False,
        None,
        None,
        "no schema to validate <xml> (inferred schema name: Foo.xsd)",
    ),
    "namespaced_root": (
        False,
        None,
        None,
        "no schema to validate <xml> (inferred schema name: {urn:x}a.xsd)",
    ),
    "xsi_location": (
        False,
        None,
        None,
        "no schema to validate <xml> (inferred schema name: mine.xsd)",
    ),
    "no_matching_schema_path": (
        False,
        None,
        None,
        "no schema to validate <xml> (inferred schema name: BES.xsd)",
    ),
    "missing_file": (False, None, None, "Invalid File: does_not_exist.bes"),
    # see DIRECTORY_ON_OLD_LIBXML2 for the other outcome
    "directory": (False, None, None, "Invalid File: ."),
    "tree_without_root": (False, None, None, "XML document has no root element"),
    "uncompilable_schema": (False, "BES.xsd", None, "nope"),
}

# libxml2 2.9 (in the Python 3.8 lxml wheels) reads a directory as an empty
# document, newer libxml2 raises OSError; both outcomes are existing behavior
DIRECTORY_ON_OLD_LIBXML2 = (False, None, 1, "Document is empty")

BAD_SCHEMA_BES = os.path.join(BAD_EXAMPLES_DIR, "example_bes_schema.bes")


def _basename(schema):
    return None if schema is None else os.path.basename(schema)


@pytest.mark.parametrize("case_id, make_kwargs", CASES, ids=CASE_IDS)
def test_existing_fields_are_unchanged(case_id, make_kwargs, tmp_path):
    """Valid, bool(), schema and errors[0] stay as they were in 2.2.1."""
    valid, schema, line, substring = EXPECTED[case_id]
    result = validate_bes_xml.validate_bes(**make_kwargs(tmp_path))
    if case_id == "directory" and result.errors[0][0] is not None:
        valid, schema, line, substring = DIRECTORY_ON_OLD_LIBXML2
    assert result.valid is valid
    assert bool(result) is valid
    assert _basename(result.schema) == schema
    if line == "no errors":
        assert result.errors == []
    else:
        assert result.errors[0][0] == line
        assert substring in result.errors[0][1]


def test_every_case_has_an_expectation():
    """The case list and the expectations cover the same inputs."""
    assert set(CASE_IDS) == set(EXPECTED)


@pytest.mark.parametrize("case_id, make_kwargs", CASES, ids=CASE_IDS)
def test_validate_xml_still_returns_a_bool(case_id, make_kwargs, tmp_path):
    """Validate_xml() returns a plain bool for every input and never raises."""
    kwargs = make_kwargs(tmp_path)
    source = kwargs.get("source", kwargs.get("path"))
    result = validate_bes_xml.validate_xml(
        source, schema_pathnames=kwargs.get("schema_pathnames"), verbose=False
    )
    assert type(result) is bool  # pylint: disable=unidiomatic-typecheck
    assert result is EXPECTED[case_id][0]


def test_unsupported_source_type_still_raises():
    """An unsupported source type is a caller error, not an invalid result."""
    with pytest.raises(TypeError):
        validate_bes_xml.validate_bes(12345)


@pytest.mark.parametrize(
    "kwargs",
    [{}, {"source": b"<BES/>", "xml": b"<BES/>"}, {"xml": "<BES/>", "path": "x"}],
    ids=["none", "source_and_xml", "xml_and_path"],
)
def test_not_exactly_one_source_still_raises(kwargs):
    """Validate_bes() needs exactly one of source, xml= and path=."""
    with pytest.raises(TypeError):
        validate_bes_xml.validate_bes(**kwargs)


def test_verbose_output_for_a_valid_file(capsys):
    """A valid file prints nothing."""
    assert validate_bes_xml.validate_xml(GOOD_BES) is True
    assert capsys.readouterr().out == ""


def test_verbose_output_for_a_schema_invalid_file(capsys):
    """A schema failure prints the file, the schema, and each error line."""
    assert validate_bes_xml.validate_xml(BAD_SCHEMA_BES) is False
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "Schema Validation Error in: %s" % BAD_SCHEMA_BES
    assert lines[1].startswith("  validated against schema: ")
    assert os.path.basename(lines[1]) == "BES.xsd"
    assert lines[2] == (
        "  Line 1: Element 'BES': Missing child element(s). Expected is one of "
        "( Fixlet, Task, Analysis, SingleAction, SourcedFixletAction, "
        "MultipleActionGroup, Baseline, ComputerGroup, CustomSite, ActionSite )."
    )
    assert len(lines) == 3


def test_verbose_output_for_a_syntax_error(tmp_path, capsys):
    """A syntax error prints the file, then lxml's message."""
    bes_path = tmp_path / "broken.bes"
    bes_path.write_bytes(b"<BES><Task>")
    assert validate_bes_xml.validate_xml(str(bes_path)) is False
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "XML Syntax Error in: %s" % bes_path
    assert "Premature end of data" in lines[1]
    assert len(lines) == 2


def test_result_still_constructs_the_old_ways():
    """Positional and keyword construction from 2.2.1 keep working."""
    assert validate_bes_xml.ValidationResult(True).valid is True
    result = validate_bes_xml.ValidationResult(False, "BES.xsd")
    assert result.valid is False
    assert result.schema == "BES.xsd"
    assert result.errors == []
    result = validate_bes_xml.ValidationResult(valid=True, schema="x", errors=[])
    assert bool(result) is True
    field_names = [field.name for field in dataclasses.fields(result)]
    assert field_names[:3] == ["valid", "schema", "errors"]


def test_concurrent_results_match_serial_results(tmp_path):
    """Validating in threads gives the same results as one at a time."""
    kwargs_list = [
        make_kwargs(tmp_path)
        for case_id, make_kwargs in CASES
        if case_id in ("valid_bes", "schema_invalid", "unknown_root", "truncated")
    ]
    expected = [
        (result.valid, result.schema, result.errors)
        for result in (validate_bes_xml.validate_bes(**kw) for kw in kwargs_list)
    ]
    jobs = kwargs_list * 25
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        results = list(
            executor.map(lambda kw: validate_bes_xml.validate_bes(**kw), jobs)
        )
    for index, result in enumerate(results):
        assert (result.valid, result.schema, result.errors) == expected[
            index % len(kwargs_list)
        ]
