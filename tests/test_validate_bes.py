"""
Tests for validate_bes() and ValidationResult (issue #13).

tests/conftest.py puts the local src first on sys.path.

run `pytest -v` at the root to get results
"""

import io
import os.path
import pathlib

import lxml.etree  # pylint: disable=import-error
import pytest
from example_paths import BAD_BES, GOOD_BES, GOOD_OJO, REPO_ROOT

import validate_bes_xml  # pylint: disable=import-error

vbx = validate_bes_xml.validate_bes_xml


def read_bytes(file_path):
    """Return the raw bytes of a file."""
    with open(file_path, "rb") as file_obj:
        return file_obj.read()


def read_text(file_path):
    """Return the text of a file, decoded as utf-8."""
    with open(file_path, encoding="utf-8") as file_obj:
        return file_obj.read()


# ---------------------------------------------------------------------------
# exports
# ---------------------------------------------------------------------------


def test_validate_bes_exported_from_package():
    """Both validate_bes and ValidationResult are importable from the package."""
    assert validate_bes_xml.validate_bes is vbx.validate_bes
    assert validate_bes_xml.ValidationResult is vbx.ValidationResult


# ---------------------------------------------------------------------------
# ValidationResult
# ---------------------------------------------------------------------------


def test_result_is_truthy_when_valid():
    """A valid result is truthy, an invalid one is falsy."""
    assert vbx.ValidationResult(valid=True, schema="BES.xsd")
    assert not vbx.ValidationResult(valid=False, schema="BES.xsd")


def test_result_errors_default_to_empty_list():
    """Errors default to a new empty list per instance."""
    first = vbx.ValidationResult(valid=True)
    second = vbx.ValidationResult(valid=True)
    assert first.errors == []
    assert first.schema is None
    first.errors.append((1, "x"))
    assert second.errors == []


# ---------------------------------------------------------------------------
# validate_bes(): results
# ---------------------------------------------------------------------------


def test_validate_bes_good_file_result():
    """A valid file gives a valid result with the schema used and no errors."""
    result = vbx.validate_bes(GOOD_BES)
    assert isinstance(result, vbx.ValidationResult)
    assert result.valid is True
    assert result
    assert result.errors == []
    assert os.path.basename(result.schema) == "BES.xsd"


def test_validate_bes_schema_errors_have_line_and_message():
    """Schema errors come back as (line, message) tuples."""
    result = vbx.validate_bes(BAD_BES)
    assert result.valid is False
    assert os.path.basename(result.schema) == "BES.xsd"
    assert len(result.errors) >= 1
    line, message = result.errors[0]
    # the <BES> root tag is on line 2 of example_bes.bes
    assert line == 2
    assert "Missing child element(s)" in message


def test_validate_bes_syntax_error_has_line_and_message():
    """XML syntax errors come back as (line, message) tuples, schema is None."""
    result = vbx.validate_bes("<BES>\n<Task>\n</BES>")
    assert result.valid is False
    assert result.schema is None
    assert len(result.errors) >= 1
    line, message = result.errors[0]
    assert isinstance(line, int)
    assert message


def test_validate_bes_no_matching_schema():
    """An unknown root tag gives schema None and an explanatory error."""
    result = vbx.validate_bes("<TotallyUnknownRootTag/>")
    assert result.valid is False
    assert result.schema is None
    assert len(result.errors) == 1
    assert "TotallyUnknownRootTag.xsd" in result.errors[0][1]


def test_validate_bes_missing_file():
    """A path that doesn't exist gives an invalid result, it does not raise."""
    result = vbx.validate_bes(os.path.join(REPO_ROOT, "does_not_exist.bes"))
    assert result.valid is False
    assert result.schema is None
    assert len(result.errors) == 1
    assert "does_not_exist.bes" in result.errors[0][1]


def test_validate_bes_does_not_print(capsys):
    """Calling validate_bes() prints nothing, whatever the outcome."""
    vbx.validate_bes(GOOD_BES)
    vbx.validate_bes(BAD_BES)
    vbx.validate_bes("<BES><Task></BES>")
    vbx.validate_bes("<TotallyUnknownRootTag/>")
    vbx.validate_bes(os.path.join(REPO_ROOT, "does_not_exist.bes"))
    assert capsys.readouterr().out == ""


def test_validate_bes_custom_schema_pathnames():
    """The schema_pathnames argument limits which schemas can be used."""
    assert (
        vbx.validate_bes(GOOD_BES, schema_pathnames=["/nowhere/Other.xsd"]).schema
        is None
    )


# ---------------------------------------------------------------------------
# validate_bes(): source types
# ---------------------------------------------------------------------------


def test_source_pathlib_path():
    """A pathlib.Path is treated as a path."""
    assert vbx.validate_bes(pathlib.Path(GOOD_BES)).valid is True


def test_source_str_path():
    """A str that doesn't look like XML is treated as a path."""
    assert vbx.validate_bes(GOOD_BES).valid is True


def test_source_str_xml_text():
    """A str starting with '<' is treated as XML text."""
    assert vbx.validate_bes(read_text(GOOD_BES)).valid is True


def test_source_str_xml_text_with_bom():
    """A BOM before '<' still counts as XML text, and is ignored."""
    assert vbx.validate_bes("\ufeff" + read_text(GOOD_BES)).valid is True


def test_source_str_xml_text_with_leading_whitespace():
    """Leading whitespace before '<' still counts as XML text, not a path."""
    result = vbx.validate_bes("\n  <BES/>")
    assert os.path.basename(result.schema) == "BES.xsd"
    # whitespace before an XML declaration is a syntax error, as in a file
    result = vbx.validate_bes("\n  " + read_text(GOOD_BES))
    assert result.valid is False
    assert result.schema is None
    assert result.errors[0][0] == 2
    assert "XML declaration" in result.errors[0][1]


def test_syntax_errors_do_not_include_earlier_parse_errors():
    """Each result only reports errors from its own parse."""
    vbx.validate_bes("<first><unclosed></first>")
    result = vbx.validate_bes("<BES>\n<Task>\n</BES>")
    assert all("first" not in message for _line, message in result.errors)


def test_source_str_xml_text_with_non_utf8_declaration():
    """A str is already decoded, so its encoding declaration is ignored."""
    text = read_text(GOOD_BES).replace('encoding="UTF-8"', 'encoding="ISO-8859-1"')
    assert 'encoding="ISO-8859-1"' in text
    assert vbx.validate_bes(text).valid is True


@pytest.mark.parametrize("wrap", [bytes, bytearray, memoryview])
def test_source_bytes_like(wrap):
    """Bytes, bytearray and memoryview are parsed as XML."""
    assert vbx.validate_bes(wrap(read_bytes(GOOD_BES))).valid is True


def test_source_bytes_respects_encoding_declaration():
    """Bytes are decoded using the XML encoding declaration."""
    data = (
        '<?xml version="1.0" encoding="ISO-8859-1"?>\n'
        "<BES><Bogus>r\u00e9sum\u00e9</Bogus></BES>"
    ).encode("iso-8859-1")
    result = vbx.validate_bes(data)
    # well-formed, so it gets as far as schema validation
    assert os.path.basename(result.schema) == "BES.xsd"
    assert result.valid is False


def test_source_binary_stream():
    """A binary file-like object is parsed directly."""
    assert vbx.validate_bes(io.BytesIO(read_bytes(GOOD_BES))).valid is True


def test_source_text_stream():
    """A text file-like object is read and parsed like a str."""
    assert vbx.validate_bes(io.StringIO(read_text(GOOD_BES))).valid is True


def test_source_open_file_uses_name_for_extension_rules():
    """An open file's .name is used as the filename, so .ojo rules apply."""
    with open(GOOD_OJO, "rb") as file_obj:
        result = vbx.validate_bes(file_obj)
    assert result.valid is True
    assert os.path.basename(result.schema) == "BESOJO.xsd"


def test_source_element_tree():
    """A parsed lxml ElementTree is used as-is."""
    tree = lxml.etree.parse(GOOD_BES)
    assert vbx.validate_bes(tree).valid is True


def test_source_element():
    """A parsed lxml Element is wrapped in an ElementTree."""
    root = lxml.etree.parse(GOOD_BES).getroot()
    assert vbx.validate_bes(root).valid is True


def test_source_unsupported_type_raises():
    """A type we can't handle raises TypeError."""
    with pytest.raises(TypeError):
        vbx.validate_bes(12345)


# ---------------------------------------------------------------------------
# validate_bes(): explicit xml= / path= keywords
# ---------------------------------------------------------------------------


def test_explicit_xml_keyword():
    """Xml= treats a str as XML text without guessing."""
    assert vbx.validate_bes(xml=read_text(GOOD_BES)).valid is True


def test_explicit_xml_keyword_with_text_that_does_not_start_with_lt():
    """Xml= skips the '<' guess, so the text is parsed (and fails as syntax)."""
    result = vbx.validate_bes(xml="not xml at all")
    assert result.valid is False
    assert result.schema is None
    assert result.errors
    # it was parsed (a syntax error has a line number), not opened as a file
    assert isinstance(result.errors[0][0], int)


def test_explicit_path_keyword():
    """Path= treats a str as a path without guessing."""
    assert vbx.validate_bes(path=GOOD_BES).valid is True


def test_explicit_path_keyword_with_xml_looking_name(tmp_path):
    """Path= opens the file even when the name starts with '<'."""
    odd_file = tmp_path / "<odd>.bes"
    try:
        odd_file.write_bytes(read_bytes(GOOD_BES))
    except OSError:
        pytest.skip("file system does not allow '<' in file names")
    assert vbx.validate_bes(path=str(odd_file)).valid is True


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"source": "<BES/>", "xml": "<BES/>"},
        {"source": GOOD_BES, "path": GOOD_BES},
        {"xml": "<BES/>", "path": GOOD_BES},
    ],
)
def test_exactly_one_source_required(kwargs):
    """Exactly one of source, xml=, path= must be given."""
    with pytest.raises(TypeError):
        vbx.validate_bes(**kwargs)


# ---------------------------------------------------------------------------
# validate_bes(): filename and extension rules
# ---------------------------------------------------------------------------


def test_filename_ojo_rule_applies_to_in_memory_xml():
    """Filename='x.ojo' picks BESOJO.xsd for in-memory XML."""
    result = vbx.validate_bes(read_bytes(GOOD_OJO), filename="whatever.OJO")
    assert result.valid is True
    assert os.path.basename(result.schema) == "BESOJO.xsd"


def test_besdomain_extension_rule():
    """The .BESDomain rule should work (it was dead code before, issue #13)."""
    result = vbx.validate_bes("<BES/>", filename="content.BESDomain")
    assert os.path.basename(result.schema) == "BESDomain.xsd"


def test_besdomain_extension_rule_in_validate_xml(tmp_path, capsys):
    """The validate_xml() wrapper also picks BESDomain.xsd for .BESDomain files."""
    domain_file = tmp_path / "content.BESDomain"
    domain_file.write_text("<BES/>")
    assert vbx.validate_xml(str(domain_file)) is False
    assert "BESDomain.xsd" in capsys.readouterr().out


def test_filename_overrides_path():
    """An explicit filename wins over the path for the extension rules."""
    result = vbx.validate_bes(GOOD_BES, filename="pretend.ojo")
    assert os.path.basename(result.schema) == "BESOJO.xsd"


def test_no_filename_uses_root_tag():
    """Without a filename the schema comes from the root."""
    result = vbx.validate_bes(read_bytes(GOOD_OJO))
    # minimal_wizard.ojo has a <BES> root, so it is checked against BES.xsd
    assert os.path.basename(result.schema) != "BESOJO.xsd"


# ---------------------------------------------------------------------------
# schema caching
# ---------------------------------------------------------------------------


def test_compiled_schema_is_cached(monkeypatch):
    """Each .xsd is compiled once per process, not once per call."""
    vbx.validate_bes(GOOD_BES)  # make sure BES.xsd is in the cache

    calls = []
    real_xmlschema = lxml.etree.XMLSchema

    def counting_xmlschema(*args, **kwargs):
        calls.append(args)
        return real_xmlschema(*args, **kwargs)

    monkeypatch.setattr(lxml.etree, "XMLSchema", counting_xmlschema)

    for _ in range(3):
        assert vbx.validate_bes(GOOD_BES).valid is True
    assert not calls


# ---------------------------------------------------------------------------
# validate_xml(): backward compatibility and verbose
# ---------------------------------------------------------------------------


def test_validate_xml_accepts_pathlib_path():
    """The validate_xml() wrapper no longer needs a str path."""
    assert vbx.validate_xml(pathlib.Path(GOOD_BES)) is True


def test_validate_xml_still_returns_bool():
    """The validate_xml() wrapper keeps returning a plain bool."""
    assert vbx.validate_xml(GOOD_BES) is True
    assert vbx.validate_xml(BAD_BES) is False


def test_validate_xml_verbose_false_is_quiet(capsys):
    """Calling validate_xml(verbose=False) prints nothing."""
    assert vbx.validate_xml(BAD_BES, verbose=False) is False
    assert capsys.readouterr().out == ""


def test_validate_xml_verbose_default_keeps_output(capsys):
    """By default validate_xml() prints the same report as before."""
    assert vbx.validate_xml(BAD_BES) is False
    out = capsys.readouterr().out
    assert f"Schema Validation Error in: {BAD_BES}" in out
    assert "  validated against schema: " in out
    assert "  Line 2: " in out


# ---------------------------------------------------------------------------
# PR #15 review fixes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "filename, expected_schema",
    [
        (pathlib.Path("content", "wizard.ojo"), "BESOJO.xsd"),
        (pathlib.Path("content", "site.BESDomain"), "BESDomain.xsd"),
        (pathlib.Path("content", "fixlet.bes"), "BES.xsd"),
    ],
)
def test_filename_accepts_pathlib_path(filename, expected_schema):
    """A pathlib.Path filename applies the same extension rules as a str."""
    result = vbx.validate_bes("<BES/>", filename=filename)
    assert os.path.basename(result.schema) == expected_schema


def test_filename_pathlib_path_in_messages():
    """A pathlib.Path filename shows up as a str path in error messages."""
    result = vbx.validate_bes("<Unknown/>", filename=pathlib.Path("x", "y.bes"))
    assert os.path.join("x", "y.bes") in result.errors[0][1]


def test_parser_does_not_expand_external_entities(tmp_path):
    """External entities (XXE) are never expanded into the document."""
    secret = tmp_path / "secret.txt"
    secret.write_text("top-secret-value")
    body = read_text(GOOD_BES).split("?>", 1)[1]
    payload = (
        '<?xml version="1.0"?>'
        f'<!DOCTYPE BES [<!ENTITY s SYSTEM "{secret.as_uri()}">]>'
        + body.replace("<Title>", "<Title>&s; ", 1)
    )
    for source in (payload, payload.encode("utf-8"), io.StringIO(payload)):
        result = vbx.validate_bes(source)
        assert result.valid is False
        assert all(
            "top-secret-value" not in message for _line, message in result.errors
        )


def test_parser_does_not_expand_external_entities_from_file(tmp_path):
    """Files on disk get the same protection as in-memory XML."""
    secret = tmp_path / "secret.txt"
    secret.write_text("top-secret-value")
    xxe_file = tmp_path / "xxe.bes"
    xxe_file.write_text(
        f'<?xml version="1.0"?><!DOCTYPE BES [<!ENTITY s SYSTEM "{secret.as_uri()}">]>'
        "<BES>&s;</BES>"
    )
    result = vbx.validate_bes(str(xxe_file))
    assert result.valid is False
    assert all("top-secret-value" not in message for _line, message in result.errors)


def test_parser_still_expands_internal_entities():
    """Entities defined inside the document still work, as with lxml's default."""
    body = read_text(GOOD_BES).split("?>", 1)[1]
    doc = '<?xml version="1.0"?><!DOCTYPE BES [<!ENTITY t "Hello">]>' + body.replace(
        "<Title>", "<Title>&t; ", 1
    )
    assert vbx.validate_bes(doc).valid is True


def test_lxml_minimum_version_is_pinned():
    """Lxml 5.0+ is required: older versions expand external entities by default."""
    for file_name in ("requirements.txt", "setup.cfg"):
        with open(os.path.join(REPO_ROOT, file_name), encoding="utf-8") as file_obj:
            assert "lxml>=5" in file_obj.read().replace(" ", ""), file_name


@pytest.mark.parametrize("bad_input", [None, 12345, object()])
def test_validate_xml_returns_false_for_unsupported_input(bad_input):
    """The legacy wrapper returns False instead of raising, as before."""
    assert vbx.validate_xml(bad_input, verbose=False) is False


def test_validate_xml_unsupported_input_prints_error_when_verbose(capsys):
    """With verbose on, the reason is printed, like other failures."""
    assert vbx.validate_xml(None) is False
    assert "unsupported XML source type: NoneType" in capsys.readouterr().out


# the public API of 2.1.1, plus what this release adds
ORIGINAL_PUBLIC_NAMES = {"SCHEMA_FILES", "find_schema_files", "infer_xml_schema"}
ORIGINAL_PUBLIC_NAMES |= {"main", "validate_all_files", "validate_xml"}
EXPECTED_PUBLIC_NAMES = ORIGINAL_PUBLIC_NAMES | {"ValidationResult", "validate_bes"}


def test_module_all_lists_public_api():
    """The implementation module's __all__ is exactly the public API."""
    assert set(vbx.__all__) == EXPECTED_PUBLIC_NAMES


def test_import_star_exports_only_public_api():
    """Using `from validate_bes_xml import *` exports only the public API."""
    namespace = {}
    exec("from validate_bes_xml import *", namespace)  # pylint: disable=exec-used
    namespace.pop("__builtins__")
    # the implementation submodule itself was also exported in 2.1.1
    assert set(namespace) == EXPECTED_PUBLIC_NAMES | {"validate_bes_xml"}


@pytest.mark.parametrize(
    "name",
    ["dataclasses", "functools", "io", "threading", "List", "Optional", "Tuple"],
)
def test_package_does_not_reexport_implementation_imports(name):
    """Imports used inside the module are not package attributes."""
    assert not hasattr(validate_bes_xml, name)
