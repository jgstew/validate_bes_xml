"""
This python module defines tests for pytest

run `pytest -v` at the root to get results
"""

import glob
import os.path
import subprocess
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

import lxml.etree  # pylint: disable=import-error,wrong-import-position

import validate_bes_xml  # pylint: disable=import-error,wrong-import-position

vbx = validate_bes_xml.validate_bes_xml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOOD_EXAMPLES_DIR = os.path.join(REPO_ROOT, "tests", "examples", "good")
BAD_EXAMPLES_DIR = os.path.join(REPO_ROOT, "tests", "examples", "bad")
SCHEMAS_DIR = os.path.join(REPO_ROOT, "src", "validate_bes_xml", "schemas")

GOOD_EXAMPLE_FILES = sorted(glob.glob(os.path.join(GOOD_EXAMPLES_DIR, "*")))
BAD_EXAMPLE_FILES = sorted(glob.glob(os.path.join(BAD_EXAMPLES_DIR, "*")))


# ---------------------------------------------------------------------------
# module / package sanity
# ---------------------------------------------------------------------------


def test_module_location():
    """check for only 'src' so it will work on windows and non-windows"""
    assert "src" in validate_bes_xml.__file__


def test_version_is_defined():
    """__version__ should exist and look like a semantic version"""
    assert hasattr(validate_bes_xml, "__version__")
    parts = validate_bes_xml.__version__.split(".")
    assert len(parts) == 3
    for part in parts:
        assert part.isdigit()


def test_example_fixtures_exist():
    """sanity check that the fixture folders used below are not empty"""
    assert len(GOOD_EXAMPLE_FILES) > 0
    assert len(BAD_EXAMPLE_FILES) > 0


# ---------------------------------------------------------------------------
# find_schema_files()
# ---------------------------------------------------------------------------


def test_schemas_found():
    """must be 4 valid schema files:"""
    assert len(vbx.find_schema_files()) == 4


def test_schemas_found_are_files_ending_in_xsd():
    """every returned schema path should exist and end in .xsd"""
    for schema_path in vbx.find_schema_files():
        assert schema_path.lower().endswith(".xsd")
        assert os.path.isfile(schema_path)


def test_schema_files_global_matches_function_default():
    """the module-level SCHEMA_FILES cache should match a fresh call"""
    assert vbx.SCHEMA_FILES == vbx.find_schema_files()


def test_find_schema_files_nonexistent_folder(tmp_path):
    """a folder_path that doesn't exist should be ignored, not raise"""
    bogus_folder = str(tmp_path / "does_not_exist")
    assert not os.path.isdir(bogus_folder)
    assert len(vbx.find_schema_files(bogus_folder)) == 4


def test_find_schema_files_dedupes_module_schema_dir():
    """passing the real schemas folder again should not create duplicates"""
    assert len(vbx.find_schema_files(SCHEMAS_DIR)) == 4


def test_find_schema_files_ignores_invalid_xsd(tmp_path, capsys):
    """well-formed xml that isn't a valid schema should be skipped, not raise"""
    bad_xsd = tmp_path / "Bad.xsd"
    bad_xsd.write_text("<notxsd>this is well-formed xml but not a schema</notxsd>")

    result = vbx.find_schema_files(str(tmp_path))

    captured = capsys.readouterr()
    assert "did not parse" in captured.out
    assert str(bad_xsd) not in result
    # the 4 real schemas (found via the module's own directory) are still there
    assert len(result) == 4


def test_find_schema_files_includes_valid_extra_schema(tmp_path):
    """a valid extra .xsd file in folder_path should be added to the set"""
    extra_schema = tmp_path / "Extra.xsd"
    extra_schema.write_text(
        (
            lxml.etree.tostring(lxml.etree.parse(os.path.join(SCHEMAS_DIR, "BES.xsd")))
        ).decode("utf-8")
    )

    result = vbx.find_schema_files(str(tmp_path))

    assert str(extra_schema) in result
    assert len(result) == 5


def test_find_schema_files_scans_schemas_subfolder(tmp_path):
    """a 'schemas' subfolder of folder_path should also be scanned"""
    schemas_subfolder = tmp_path / "schemas"
    schemas_subfolder.mkdir()
    extra_schema = schemas_subfolder / "Extra.xsd"
    extra_schema.write_text(
        (
            lxml.etree.tostring(lxml.etree.parse(os.path.join(SCHEMAS_DIR, "BES.xsd")))
        ).decode("utf-8")
    )

    result = vbx.find_schema_files(str(tmp_path))

    assert str(extra_schema) in result


# ---------------------------------------------------------------------------
# infer_xml_schema()
# ---------------------------------------------------------------------------


def test_infer_xml_schema_from_schema_location_attribute():
    """should prefer the xsi:noNamespaceSchemaLocation attribute value"""
    xml_doc = lxml.etree.fromstring(
        b'<BES xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        b'xsi:noNamespaceSchemaLocation="BES.xsd"></BES>'
    ).getroottree()
    assert vbx.infer_xml_schema(xml_doc) == "BES.xsd"


def test_infer_xml_schema_from_root_tag():
    """without a schema location attribute, use '<root tag>.xsd'"""
    xml_doc = lxml.etree.fromstring(b"<SomeCustomRoot></SomeCustomRoot>").getroottree()
    assert vbx.infer_xml_schema(xml_doc) == "SomeCustomRoot.xsd"


def test_infer_xml_schema_falls_back_to_default(capsys):
    """an object with no getroot() at all should fall back to BES.xsd"""
    assert vbx.infer_xml_schema(None) == "BES.xsd"
    captured = capsys.readouterr()
    assert "couldn't fine root tag" in captured.out


# ---------------------------------------------------------------------------
# validate_xml()
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("file_path", GOOD_EXAMPLE_FILES)
def test_validate_xml_good_examples(file_path):
    """every file under tests/examples/good should validate successfully"""
    assert vbx.validate_xml(file_path) is True


@pytest.mark.parametrize("file_path", BAD_EXAMPLE_FILES)
def test_validate_xml_bad_examples(file_path):
    """every file under tests/examples/bad should fail validation"""
    assert vbx.validate_xml(file_path) is False


def test_validate_xml_missing_file(tmp_path, capsys):
    """a nonexistent file path should be reported as an invalid file"""
    missing = str(tmp_path / "does_not_exist.bes")
    assert vbx.validate_xml(missing) is False
    captured = capsys.readouterr()
    assert "Invalid File" in captured.out


def test_validate_xml_malformed_xml(tmp_path, capsys):
    """malformed xml should be caught as a syntax error, not raise"""
    bad_file = tmp_path / "malformed.bes"
    bad_file.write_text("<BES><Task></BES>")

    assert vbx.validate_xml(str(bad_file)) is False
    captured = capsys.readouterr()
    assert "XML Syntax Error" in captured.out


def test_validate_xml_unknown_schema_warns(tmp_path, capsys):
    """a root tag with no matching schema should warn and return False"""
    unknown_file = tmp_path / "unknown.bes"
    unknown_file.write_text("<TotallyUnknownRootTag></TotallyUnknownRootTag>")

    assert vbx.validate_xml(str(unknown_file)) is False
    captured = capsys.readouterr()
    assert "no schema to validate" in captured.out
    # the warning should say which schema name it looked for
    assert "TotallyUnknownRootTag.xsd" in captured.out


def test_validate_xml_schema_failure_reports_details(capsys):
    """a schema validation failure should say which schema was used,
    which file failed, and the line and reason for each error"""
    bad_file = os.path.join(BAD_EXAMPLES_DIR, "example_bes.bes")

    assert vbx.validate_xml(bad_file) is False
    captured = capsys.readouterr()
    assert f"Schema Validation Error in: {bad_file}" in captured.out
    assert "validated against schema:" in captured.out
    assert "BES.xsd" in captured.out
    # the <BES> root tag is on line 2 of example_bes.bes
    assert "Line 2:" in captured.out
    assert "Missing child element(s)" in captured.out


def test_validate_xml_ojo_extension_is_case_insensitive(tmp_path):
    """'.ojo' detection in the file path should not be case sensitive"""
    source = os.path.join(GOOD_EXAMPLES_DIR, "minimal_wizard.ojo")
    with open(source, encoding="utf-8") as source_file:
        copy_path = tmp_path / "copy.OJO"
        copy_path.write_text(source_file.read())

    assert vbx.validate_xml(str(copy_path)) is True


def test_validate_xml_empty_schema_pathnames_falls_back_to_default():
    """an empty/falsy schema_pathnames should fall back to SCHEMA_FILES"""
    good_file = os.path.join(GOOD_EXAMPLES_DIR, "FixletDebugger.bes")
    assert vbx.validate_xml(good_file, schema_pathnames=[]) == vbx.validate_xml(
        good_file
    )


def test_validate_xml_custom_schema_pathnames_override_default(tmp_path, capsys):
    """an explicit schema_pathnames that has no matches should warn"""
    good_file = os.path.join(GOOD_EXAMPLES_DIR, "FixletDebugger.bes")
    bogus_schema = str(tmp_path / "Nonmatching.xsd")

    assert vbx.validate_xml(good_file, schema_pathnames=[bogus_schema]) is False
    captured = capsys.readouterr()
    assert "no schema to validate" in captured.out


def test_validate_xml_custom_schema_pathnames_can_still_pass():
    """passing the real schema explicitly should behave like the default"""
    good_file = os.path.join(GOOD_EXAMPLES_DIR, "FixletDebugger.bes")
    bes_schema = os.path.join(SCHEMAS_DIR, "BES.xsd")

    assert vbx.validate_xml(good_file, schema_pathnames=[bes_schema]) is True


# ---------------------------------------------------------------------------
# validate_all_files()
# ---------------------------------------------------------------------------


def test_validate_all_files_default():
    """should be EXPECTED_ERROR_COUNT errors currently:"""
    assert vbx.validate_all_files() == EXPECTED_ERROR_COUNT


def test_validate_all_files_good_folder_has_no_errors():
    """scanning only the 'good' examples folder should report zero errors"""
    assert vbx.validate_all_files(GOOD_EXAMPLES_DIR) == 0


def test_validate_all_files_bad_folder_all_errors():
    """scanning only the 'bad' examples folder should report all as errors"""
    assert vbx.validate_all_files(BAD_EXAMPLES_DIR) == len(BAD_EXAMPLE_FILES)


def test_validate_all_files_respects_file_extensions():
    """restricting file_extensions should only scan matching files"""
    ojo_files = [f for f in GOOD_EXAMPLE_FILES if f.lower().endswith(".ojo")]
    count_errors = vbx.validate_all_files(GOOD_EXAMPLES_DIR, file_extensions=(".ojo",))
    assert count_errors == 0
    assert len(ojo_files) > 0


def test_validate_all_files_reports_correct_totals(capsys):
    """the printed summary line should reflect files scanned and errors found"""
    vbx.validate_all_files(GOOD_EXAMPLES_DIR)
    captured = capsys.readouterr()
    expected = f"{0} errors found in {len(GOOD_EXAMPLE_FILES)} xml files"
    assert expected in captured.out


def test_validate_all_files_empty_folder_has_no_files(tmp_path):
    """an empty folder should report zero files and zero errors"""
    assert vbx.validate_all_files(str(tmp_path)) == 0


def test_validate_all_files_nonexistent_folder(tmp_path):
    """os.walk on a nonexistent folder yields nothing, so no errors"""
    bogus_folder = str(tmp_path / "does_not_exist")
    assert vbx.validate_all_files(bogus_folder) == 0


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------


def test_main_default_exit_code():
    """test main exit code = EXPECTED_ERROR_COUNT"""
    with pytest.raises(SystemExit) as wrapped_error:
        vbx.main()
    # https://medium.com/python-pandemonium/testing-sys-exit-with-pytest-10c6e5f7726f
    assert wrapped_error.value.code == EXPECTED_ERROR_COUNT


def test_main_good_folder_exit_code_zero():
    """main() against only good examples should exit 0"""
    with pytest.raises(SystemExit) as wrapped_error:
        vbx.main(GOOD_EXAMPLES_DIR)
    assert wrapped_error.value.code == 0


def test_main_bad_folder_exit_code_matches_error_count():
    """main() against only bad examples should exit with the error count"""
    with pytest.raises(SystemExit) as wrapped_error:
        vbx.main(BAD_EXAMPLES_DIR)
    assert wrapped_error.value.code == len(BAD_EXAMPLE_FILES)


def test_main_custom_file_extensions():
    """main() should honor a custom file_extensions tuple"""
    with pytest.raises(SystemExit) as wrapped_error:
        vbx.main(GOOD_EXAMPLES_DIR, file_extensions=(".ojo",))
    assert wrapped_error.value.code == 0


# ---------------------------------------------------------------------------
# command-line entry point (`python -m validate_bes_xml`)
# ---------------------------------------------------------------------------


def test_cli_entry_point_exit_code():
    """running the package as a script should exit with the error count"""
    env = dict(os.environ)
    env["PYTHONPATH"] = (
        os.path.join(REPO_ROOT, "src") + os.pathsep + env.get("PYTHONPATH", "")
    )
    result = subprocess.run(
        [sys.executable, "-m", "validate_bes_xml"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == EXPECTED_ERROR_COUNT


# ---------------------------------------------------------------------------
# lint / style checks (kept from the original test suite)
# ---------------------------------------------------------------------------


def test_isort():
    """test isort results"""
    assert ret_code_isort == 0


def test_flakes():
    """test pyflakes results"""
    assert ret_code_flakes == 0
