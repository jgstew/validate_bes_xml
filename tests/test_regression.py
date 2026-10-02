"""
Regression tests for behavior downstream consumers may depend on.

These pin the public API as released (2.1.1): names, signatures, return types,
printed output, and scanning rules. They must pass against both the released code
and any new version, so they only use the original API.

tests/conftest.py puts the local src first on sys.path.

run `pytest -v` at the root to get results
"""

import inspect
import os.path
import re
import shutil
import subprocess
import sys

import example_paths as paths
import lxml.etree  # pylint: disable=import-error
import pytest

import validate_bes_xml  # pylint: disable=import-error

vbx = validate_bes_xml.validate_bes_xml


BUNDLED_SCHEMAS = {"BES.xsd", "BESAPI.xsd", "BESDomain.xsd", "BESOJO.xsd"}


def read_bytes(file_path):
    """Return the raw bytes of a file."""
    with open(file_path, "rb") as file_obj:
        return file_obj.read()


def bundled_schema_path(name):
    """Return the SCHEMA_FILES entry with this base name."""
    matches = [s for s in vbx.SCHEMA_FILES if os.path.basename(s) == name]
    assert len(matches) == 1
    return matches[0]


# ---------------------------------------------------------------------------
# public names
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "SCHEMA_FILES",
        "find_schema_files",
        "infer_xml_schema",
        "main",
        "validate_all_files",
        "validate_xml",
    ],
)
def test_public_name_exported_from_package(name):
    """`import validate_bes_xml; validate_bes_xml.<name>` keeps working."""
    assert getattr(validate_bes_xml, name) is getattr(vbx, name)


def test_submodule_still_reachable_from_package():
    """`validate_bes_xml.validate_bes_xml` is still the implementation module."""
    assert (
        validate_bes_xml.validate_bes_xml.__name__
        == "validate_bes_xml.validate_bes_xml"
    )


def test_from_import_star_exports_public_api():
    """`from validate_bes_xml import *` still provides the original names."""
    namespace = {}
    exec("from validate_bes_xml import *", namespace)  # pylint: disable=exec-used
    for name in (
        "SCHEMA_FILES",
        "find_schema_files",
        "infer_xml_schema",
        "main",
        "validate_all_files",
        "validate_xml",
    ):
        assert name in namespace


# ---------------------------------------------------------------------------
# signatures: original parameters keep their names, order, kind and defaults;
# any new parameters must come after them and be optional
# ---------------------------------------------------------------------------

ORIGINAL_SIGNATURES = {
    "infer_xml_schema": [("xml_doc_obj", inspect.Parameter.empty)],
    "find_schema_files": [("folder_path", None)],
    "validate_xml": [
        ("file_pathname", inspect.Parameter.empty),
        ("schema_pathnames", None),
    ],
    "validate_all_files": [
        ("folder_path", "."),
        ("file_extensions", (".bes", ".ojo")),
    ],
    "main": [("folder_path", "."), ("file_extensions", (".bes", ".ojo"))],
}


@pytest.mark.parametrize("func_name", sorted(ORIGINAL_SIGNATURES))
def test_signature_is_backward_compatible(func_name):
    """Positional and keyword calls written for 2.1.1 keep working."""
    params = list(inspect.signature(getattr(vbx, func_name)).parameters.values())
    original = ORIGINAL_SIGNATURES[func_name]

    assert len(params) >= len(original)
    for param, (name, default) in zip(params, original):
        assert param.name == name
        assert param.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD
        assert param.default == default

    for extra in params[len(original) :]:
        assert extra.default is not inspect.Parameter.empty, extra.name


def test_validate_xml_keyword_call():
    """Callers that name the arguments keep working."""
    assert (
        vbx.validate_xml(
            file_pathname=paths.GOOD_BES, schema_pathnames=vbx.SCHEMA_FILES
        )
        is True
    )


# ---------------------------------------------------------------------------
# SCHEMA_FILES / find_schema_files()
# ---------------------------------------------------------------------------


def test_schema_files_is_set_of_str_paths():
    """SCHEMA_FILES is a set of str paths to the bundled schemas."""
    assert isinstance(vbx.SCHEMA_FILES, set)
    for schema_path in vbx.SCHEMA_FILES:
        assert isinstance(schema_path, str)
        assert os.path.isabs(schema_path)
    assert {os.path.basename(s) for s in vbx.SCHEMA_FILES} == BUNDLED_SCHEMAS


def test_find_schema_files_picks_up_cwd(tmp_path, monkeypatch):
    """.xsd files in the cwd, and its 'schemas' folder, are found (README)."""
    (tmp_path / "schemas").mkdir()
    shutil.copy(os.path.join(paths.SCHEMAS_DIR, "BES.xsd"), tmp_path / "CwdExtra.xsd")
    shutil.copy(
        os.path.join(paths.SCHEMAS_DIR, "BES.xsd"), tmp_path / "schemas" / "Sub.xsd"
    )
    monkeypatch.chdir(tmp_path)

    found = {os.path.basename(s) for s in vbx.find_schema_files()}

    assert found == BUNDLED_SCHEMAS | {"CwdExtra.xsd", "Sub.xsd"}


def test_find_schema_files_matches_xsd_extension_case_insensitively(tmp_path):
    """An .XSD file name is found too."""
    shutil.copy(os.path.join(paths.SCHEMAS_DIR, "BES.xsd"), tmp_path / "Upper.XSD")
    assert str(tmp_path / "Upper.XSD") in vbx.find_schema_files(str(tmp_path))


# ---------------------------------------------------------------------------
# infer_xml_schema()
# ---------------------------------------------------------------------------


def tree(xml_bytes):
    """Parse bytes into an ElementTree."""
    return lxml.etree.fromstring(xml_bytes).getroottree()


def test_infer_xml_schema_returns_attribute_value_verbatim():
    """The .xsd attribute value is returned as-is, case and path included."""
    assert vbx.infer_xml_schema(tree(b'<a loc="dir/Foo.XSD"/>')) == "dir/Foo.XSD"


def test_infer_xml_schema_attribute_wins_over_root_tag():
    """A .xsd attribute takes priority over the root tag name."""
    assert vbx.infer_xml_schema(tree(b'<BESAPI loc="BES.xsd"/>')) == "BES.xsd"


def test_infer_xml_schema_uses_first_xsd_attribute():
    """With several .xsd attributes, the first one wins."""
    assert vbx.infer_xml_schema(tree(b'<a x="One.xsd" y="Two.xsd"/>')) == "One.xsd"


def test_infer_xml_schema_ignores_non_xsd_attributes():
    """Attributes that don't mention .xsd don't affect the result."""
    assert vbx.infer_xml_schema(tree(b'<BESAPI a="1" b="x.xml"/>')) == "BESAPI.xsd"


def test_infer_xml_schema_namespaced_root_tag():
    """A namespaced root tag keeps lxml's {namespace}tag form."""
    assert vbx.infer_xml_schema(tree(b'<a xmlns="urn:x"/>')) == "{urn:x}a.xsd"


# ---------------------------------------------------------------------------
# validate_xml(): return type and inputs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "file_path, expected",
    [
        (paths.GOOD_BES, True),
        (paths.GOOD_OJO, True),
        (paths.BAD_BES, False),
        (os.path.join(paths.REPO_ROOT, "does_not_exist.bes"), False),
        (paths.GOOD_EXAMPLES_DIR, False),  # a directory, not a file
    ],
)
def test_validate_xml_returns_plain_bool(file_path, expected):
    """The validate_xml() result is exactly True or False, not a truthy object."""
    result = vbx.validate_xml(file_path)
    assert type(result) is bool  # pylint: disable=unidiomatic-typecheck
    assert result is expected


def test_validate_xml_relative_path(monkeypatch):
    """A path relative to the cwd works."""
    monkeypatch.chdir(paths.GOOD_EXAMPLES_DIR)
    assert vbx.validate_xml("FixletDebugger.bes") is True


def test_validate_xml_utf8_bom_file(tmp_path):
    """A file starting with a UTF-8 BOM validates."""
    bom_file = tmp_path / "bom.bes"
    bom_file.write_bytes(b"\xef\xbb\xbf" + read_bytes(paths.GOOD_BES))
    assert vbx.validate_xml(str(bom_file)) is True


def test_validate_xml_non_utf8_encoding_declaration(tmp_path):
    """A file is decoded using its own encoding declaration."""
    text = read_bytes(paths.GOOD_BES).decode("utf-8")
    text = text.replace('encoding="UTF-8"', 'encoding="windows-1252"', 1)
    text = text.replace("<Title>", "<Title>r\u00e9sum\u00e9 ", 1)
    assert 'encoding="windows-1252"' in text
    cp_file = tmp_path / "cp1252.bes"
    cp_file.write_bytes(text.encode("cp1252"))
    assert vbx.validate_xml(str(cp_file)) is True


def test_validate_xml_non_ascii_file_name(tmp_path):
    """A non-ASCII file name works."""
    odd_file = tmp_path / "r\u00e9sum\u00e9 \u00fcber.bes"
    odd_file.write_bytes(read_bytes(paths.GOOD_BES))
    assert vbx.validate_xml(str(odd_file)) is True


@pytest.mark.parametrize("container", [list, tuple, set, frozenset])
def test_validate_xml_schema_pathnames_any_iterable(container):
    """The schema_pathnames argument can be any collection of paths."""
    schemas = container(vbx.SCHEMA_FILES)
    assert vbx.validate_xml(paths.GOOD_BES, schemas) is True
    assert vbx.validate_xml(paths.BAD_BES, schemas) is False


def test_validate_xml_uses_schema_from_custom_location(tmp_path, capsys):
    """A schema elsewhere is used when its path contains the inferred name."""
    custom = tmp_path / "custom"
    custom.mkdir()
    custom_schema = str(custom / "BES.xsd")
    shutil.copy(os.path.join(paths.SCHEMAS_DIR, "BES.xsd"), custom_schema)

    assert vbx.validate_xml(paths.BAD_BES, [custom_schema]) is False
    assert f"  validated against schema: {custom_schema}\n" in capsys.readouterr().out
    assert vbx.validate_xml(paths.GOOD_BES, [custom_schema]) is True


def test_validate_xml_ojo_file_uses_besojo_schema(tmp_path, capsys):
    """A file with .ojo in its name is checked against BESOJO.xsd."""
    ojo_file = tmp_path / "bad.ojo"
    ojo_file.write_text("<BES/>")
    assert vbx.validate_xml(str(ojo_file)) is False
    out = capsys.readouterr().out
    assert f"  validated against schema: {bundled_schema_path('BESOJO.xsd')}\n" in out


# ---------------------------------------------------------------------------
# validate_xml(): exact printed output
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("file_path", [paths.GOOD_BES, paths.GOOD_OJO])
def test_validate_xml_valid_file_prints_nothing(file_path, capsys):
    """A valid file produces no output at all."""
    assert vbx.validate_xml(file_path) is True
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_validate_xml_missing_file_exact_output(tmp_path, capsys):
    """Exact output for a file that can't be read."""
    missing = str(tmp_path / "missing.bes")
    vbx.validate_xml(missing)
    assert capsys.readouterr().out == f"Invalid File: {missing}\n"


def test_validate_xml_syntax_error_exact_output(tmp_path, capsys):
    """Exact output for malformed XML: a header, then lxml's error text."""
    bad_file = tmp_path / "malformed.bes"
    bad_file.write_text("<BES><Task></BES>")
    vbx.validate_xml(str(bad_file))

    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == f"XML Syntax Error in: {bad_file}"
    assert len(lines) == 2
    assert lines[1].startswith("Opening and ending tag mismatch: Task line 1 and BES")


def test_validate_xml_no_schema_exact_output(tmp_path, capsys):
    """Exact output when no schema matches."""
    unknown = tmp_path / "unknown.bes"
    unknown.write_text("<TotallyUnknownRootTag/>")
    vbx.validate_xml(str(unknown))
    assert capsys.readouterr().out == (
        f"WARNING: no schema to validate {unknown} "
        "(inferred schema name: TotallyUnknownRootTag.xsd)\n"
    )


def test_validate_xml_schema_error_exact_output(capsys):
    """Exact output layout for schema errors: header, schema, one line per error."""
    vbx.validate_xml(paths.BAD_BES)
    lines = capsys.readouterr().out.splitlines()

    assert lines[0] == f"Schema Validation Error in: {paths.BAD_BES}"
    assert lines[1] == f"  validated against schema: {bundled_schema_path('BES.xsd')}"
    assert len(lines) >= 3
    for line in lines[2:]:
        assert re.fullmatch(r"  Line \d+: .+", line), line
    assert lines[2].startswith("  Line 2: Element 'BES': Missing child element(s).")


def test_validate_xml_reports_every_schema_error(tmp_path, capsys):
    """Each schema error gets its own line."""
    bad_file = tmp_path / "two_errors.bes"
    bad_file.write_text("<BES>\n<Bogus1/>\n<Bogus2/>\n</BES>")
    assert vbx.validate_xml(str(bad_file)) is False
    error_lines = [
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("  Line ")
    ]
    assert len(error_lines) >= 1
    assert error_lines[0].startswith("  Line 2: ")


# ---------------------------------------------------------------------------
# validate_all_files()
# ---------------------------------------------------------------------------


@pytest.fixture(name="content_tree")
def fixture_content_tree(tmp_path):
    """A small content folder: nested good/bad files plus files to ignore."""
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    shutil.copy(paths.GOOD_BES, tmp_path / "good.bes")
    shutil.copy(paths.GOOD_OJO, nested / "good.ojo")
    shutil.copy(paths.BAD_BES, nested / "bad.bes")
    shutil.copy(paths.BAD_BES, tmp_path / "UPPER.BES")  # extension match ignores case
    (tmp_path / "notes.xml").write_text("<not even close")  # not scanned
    (tmp_path / "readme.txt").write_text("ignore me")  # not scanned
    return tmp_path


def test_validate_all_files_returns_int_error_count(content_tree):
    """Returns the number of failing files as an int, scanning subfolders."""
    count = vbx.validate_all_files(str(content_tree))
    assert type(count) is int  # pylint: disable=unidiomatic-typecheck
    assert count == 2


def test_validate_all_files_exact_summary_line(content_tree, capsys):
    """The last printed line is the exact summary."""
    vbx.validate_all_files(str(content_tree))
    lines = capsys.readouterr().out.splitlines()
    assert lines[-1] == "2 errors found in 4 xml files"


def test_validate_all_files_prints_report_per_failing_file(content_tree, capsys):
    """Each failing file gets its own report before the summary."""
    vbx.validate_all_files(str(content_tree))
    out = capsys.readouterr().out
    assert out.count("Schema Validation Error in: ") == 2
    assert (
        "Schema Validation Error in: " + os.path.join(str(content_tree), "UPPER.BES")
        in out
    )


def test_validate_all_files_single_string_extension(content_tree):
    """The file_extensions argument can be a single str, as str.endswith allows."""
    assert vbx.validate_all_files(str(content_tree), ".ojo") == 0
    assert vbx.validate_all_files(str(content_tree), ".bes") == 2


def test_validate_all_files_custom_extension(content_tree, capsys):
    """Other extensions can be scanned when asked for."""
    count = vbx.validate_all_files(str(content_tree), (".xml",))
    assert count == 1
    assert capsys.readouterr().out.splitlines()[-1] == "1 errors found in 1 xml files"


def test_validate_all_files_skips_git_folder(content_tree, monkeypatch):
    """Files under .git are not scanned when scanning from the cwd."""
    git_dir = content_tree / ".git" / "objects"
    git_dir.mkdir(parents=True)
    shutil.copy(paths.BAD_BES, git_dir / "bad.bes")
    monkeypatch.chdir(content_tree)

    assert vbx.validate_all_files() == 2
    assert vbx.validate_all_files(".") == 2


# ---------------------------------------------------------------------------
# main() / command line
# ---------------------------------------------------------------------------


def test_main_exit_code_is_error_count(content_tree):
    """Calling main() exits with the number of failing files."""
    with pytest.raises(SystemExit) as wrapped_error:
        vbx.main(str(content_tree))
    assert wrapped_error.value.code == 2


def run_cli(cwd):
    """Run `python -m validate_bes_xml` from cwd using the local src."""
    env = dict(os.environ)
    env["PYTHONPATH"] = (
        os.path.join(paths.REPO_ROOT, "src") + os.pathsep + env.get("PYTHONPATH", "")
    )
    return subprocess.run(
        [sys.executable, "-m", "validate_bes_xml"],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_scans_cwd(content_tree):
    """The CLI scans the cwd, prints the summary, and exits with the error count."""
    result = run_cli(str(content_tree))
    assert result.returncode == 2
    assert result.stdout.splitlines()[-1] == "2 errors found in 4 xml files"


def test_cli_empty_folder_exits_zero(tmp_path):
    """No content means exit code 0."""
    result = run_cli(str(tmp_path))
    assert result.returncode == 0
    assert result.stdout == "0 errors found in 0 xml files\n"
