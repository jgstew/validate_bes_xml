"""
Tests for ValidationResult.status and .inferred_schema (issue #17, step 2).

tests/conftest.py puts the local src first on sys.path.
"""

import concurrent.futures
import json

import pytest
from result_cases import CASE_IDS, CASES

import validate_bes_xml  # pylint: disable=import-error

Status = getattr(validate_bes_xml, "Status", None)
ValidationResult = validate_bes_xml.ValidationResult

EXPECTED_STATUS = {
    "valid_bes": "valid",
    "schema_invalid": "invalid",
    "empty_bytes": "syntax_error",
    "whitespace_only": "syntax_error",
    "comment_only": "syntax_error",
    "pi_only": "syntax_error",
    "truncated": "syntax_error",
    "bogus_encoding": "syntax_error",
    "undefined_entity": "syntax_error",
    "external_entity": "syntax_error",
    "unknown_root": "no_schema",
    "namespaced_root": "no_schema",
    "xsi_location": "no_schema",
    "no_matching_schema_path": "no_schema",
    "missing_file": "error",
    # libxml2 2.9 (Python 3.8 lxml wheels) gives syntax_error, see below
    "directory": "error",
    "tree_without_root": "error",
    "uncompilable_schema": "error",
}


def test_status_is_exported():
    """Status is importable from the package and listed in __all__."""
    assert Status is not None
    assert Status is validate_bes_xml.validate_bes_xml.Status
    # the package has no __all__ of its own; it re-exports the module's
    assert "Status" in validate_bes_xml.validate_bes_xml.__all__
    assert Status.NO_SCHEMA == "no_schema"


def test_status_values():
    """Status has exactly the five documented values."""
    assert [member.value for member in Status] == [
        "valid",
        "invalid",
        "syntax_error",
        "no_schema",
        "error",
    ]


@pytest.mark.parametrize("member", list(Status or []), ids=str)
def test_status_formats_as_its_value(member):
    """Str(), f-strings, %s and json all give the bare value on every Python."""
    assert str(member) == member.value
    assert f"{member}" == member.value
    assert "%s" % member == member.value
    assert json.dumps(member) == '"%s"' % member.value


def test_every_case_has_a_status():
    """The case list and the expected statuses cover the same inputs."""
    assert set(CASE_IDS) == set(EXPECTED_STATUS)


@pytest.mark.parametrize("case_id, make_kwargs", CASES, ids=CASE_IDS)
def test_status_for_each_input(case_id, make_kwargs, tmp_path):
    """Each input gets the status from the table in issue #17."""
    result = validate_bes_xml.validate_bes(**make_kwargs(tmp_path))
    assert isinstance(result.status, Status)
    expected = EXPECTED_STATUS[case_id]
    if case_id == "directory" and result.errors[0][0] is not None:
        # libxml2 2.9 reads a directory as an empty document
        expected = "syntax_error"
    assert result.status == expected


@pytest.mark.parametrize("case_id, make_kwargs", CASES, ids=CASE_IDS)
def test_status_agrees_with_valid(
    case_id, make_kwargs, tmp_path
):  # pylint: disable=unused-argument
    """Status is VALID exactly when the result is valid and truthy."""
    result = validate_bes_xml.validate_bes(**make_kwargs(tmp_path))
    assert (result.status is Status.VALID) == result.valid == bool(result)


@pytest.mark.parametrize("case_id, make_kwargs", CASES, ids=CASE_IDS)
def test_schema_and_inferred_schema_by_status(case_id, make_kwargs, tmp_path):
    """
    Schema is set only once a schema was selected.

    inferred_schema is set whenever the document parsed.
    """
    result = validate_bes_xml.validate_bes(**make_kwargs(tmp_path))
    if result.status in (Status.VALID, Status.INVALID):
        assert result.schema is not None
        assert result.inferred_schema is not None
    elif result.status is Status.NO_SCHEMA:
        assert result.schema is None
        assert result.inferred_schema is not None
    elif result.status is Status.SYNTAX_ERROR:
        assert result.schema is None
        assert result.inferred_schema is None
    elif case_id == "uncompilable_schema":
        # a schema was selected, then failed to compile
        assert result.schema is not None
        assert result.inferred_schema == "BES.xsd"
    else:
        assert result.schema is None
        assert result.inferred_schema is None


@pytest.mark.parametrize(
    "kwargs, inferred_schema",
    [
        ({"source": b"<Foo/>"}, "Foo.xsd"),
        # records today's behavior for namespaced roots, not an endorsement
        ({"source": b'<a xmlns="urn:x"/>'}, "{urn:x}a.xsd"),
        (
            {
                "source": b'<BES xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
                b' xsi:noNamespaceSchemaLocation="../siteConfig.xsd"/>'
            },
            "siteConfig.xsd",
        ),
        ({"source": b"<BES/>", "filename": "x.ojo"}, "BESOJO.xsd"),
        ({"source": b"<BES/>", "filename": "x.BESDomain"}, "BESDomain.xsd"),
        ({"source": b"<BES/>"}, "BES.xsd"),
        ({"source": b"<BES><Task>"}, None),
        ({"path": "does_not_exist.bes"}, None),
    ],
    ids=[
        "unknown_root",
        "namespaced_root",
        "xsi_location_path",
        "ojo_filename",
        "besdomain_filename",
        "bes_root",
        "syntax_error",
        "missing_file",
    ],
)
def test_inferred_schema(kwargs, inferred_schema):
    """Inferred_schema is the bare schema file name that was looked up."""
    assert validate_bes_xml.validate_bes(**kwargs).inferred_schema == inferred_schema


def test_constructed_result_derives_status_from_valid():
    """A result built by a caller without status gets VALID or INVALID."""
    assert ValidationResult(valid=True).status is Status.VALID
    assert ValidationResult(valid=False).status is Status.INVALID
    assert ValidationResult(valid=True).inferred_schema is None


def test_constructed_result_accepts_a_status_string():
    """A status given as a string is converted to the Status member."""
    result = ValidationResult(valid=False, status="no_schema")
    assert result.status is Status.NO_SCHEMA


def test_constructed_result_rejects_contradicting_status():
    """Status VALID must go with valid=True, and the reverse."""
    with pytest.raises(ValueError):
        ValidationResult(valid=True, status=Status.INVALID)
    with pytest.raises(ValueError):
        ValidationResult(valid=False, status=Status.VALID)


def test_constructed_result_rejects_unknown_status():
    """A status that is not a Status value raises ValueError."""
    with pytest.raises(ValueError):
        ValidationResult(valid=False, status="bogus")


def test_no_schema_is_falsy():
    """No_schema stays falsy, so `if not validate_bes(...)` is unchanged."""
    result = validate_bes_xml.validate_bes(b"<Foo/>")
    assert result.status is Status.NO_SCHEMA
    assert not result


def test_concurrent_statuses_match_serial_statuses(tmp_path):
    """Validating in threads gives the same status and errors as serially."""
    kwargs_list = [
        make_kwargs(tmp_path)
        for case_id, make_kwargs in CASES
        if case_id in ("valid_bes", "schema_invalid", "unknown_root", "truncated")
    ]
    expected = [
        (result.status, result.inferred_schema, result.errors)
        for result in (validate_bes_xml.validate_bes(**kw) for kw in kwargs_list)
    ]
    jobs = kwargs_list * 25
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        results = list(
            executor.map(lambda kw: validate_bes_xml.validate_bes(**kw), jobs)
        )
    for index, result in enumerate(results):
        assert (result.status, result.inferred_schema, result.errors) == expected[
            index % len(kwargs_list)
        ]
