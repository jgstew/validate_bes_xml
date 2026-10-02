#!/usr/local/python
"""Python module to validate BigFix XML files."""

# pylint: disable=no-else-return
# pylint: disable=broad-except
# pylint: disable=too-many-return-statements
# pylint: disable=unused-variable
# pylint: disable=too-many-branches

import dataclasses
import functools
import io
import os
import sys
import threading
from typing import List, Optional, Tuple

try:
    import lxml.etree  # pylint: disable=import-error
except ImportError:
    import lxml


def infer_xml_schema(xml_doc_obj):
    """
    This function determines which schema
    should be used to validate the xml within the file.
    """
    try:
        # look for ".xsd" attribute on root tag
        for _name, value in xml_doc_obj.getroot().items():
            if ".xsd" in value.lower():
                return value
    except AttributeError:
        pass

    try:
        # use name of root tag as the name of the xsd
        return xml_doc_obj.getroot().tag + ".xsd"
    except BaseException as err:
        print(err)
        print("WARNING: using default - couldn't fine root tag")
        return "BES.xsd"


def find_schema_files(folder_path=None):
    """
    This function finds schema files in the following:
        - Folder passed in as parameter.

        - Current Working Directory
        - Directory the python module is in
        - Any `schemas` folders within the above
    """
    # use set to get only unique folders
    folder_set = set()
    if folder_path:
        folder_set.add(folder_path)
    folder_set.add(os.path.dirname(os.path.realpath(__file__)))
    folder_set.add(os.getcwd())

    folder_array = []

    for folder_item in folder_set:
        # for each unique folder, test if it exists
        if os.path.isdir(folder_item):
            folder_array.append(folder_item)
        # also add subfolder "schemas" if it exists
        if os.path.isdir(os.path.join(folder_item, "schemas")):
            folder_array.append(os.path.join(folder_item, "schemas"))

    schema_files_set = set()

    for folder_item in folder_array:
        for file_item in os.listdir(folder_item):
            if file_item.lower().endswith(".xsd"):
                file_item_path = os.path.join(folder_item, file_item)
                try:
                    # test xsd parsing
                    lxml.etree.XMLSchema(lxml.etree.parse(file_item_path))
                    schema_files_set.add(file_item_path)
                except lxml.etree.XMLSchemaParseError:
                    print("WARNING: xsd did not parse: " + file_item_path)
    # print(schema_files_set)
    return schema_files_set


SCHEMA_FILES = find_schema_files()


@dataclasses.dataclass
class ValidationResult:
    """
    The outcome of validating one BES XML document.

    Truthy when valid. `schema` is the path of the schema that was used, or None when
    the XML could not be parsed or no schema matched. `errors` is a list of
    (line, message) tuples for syntax or schema errors; line is None when unknown.
    """

    valid: bool
    schema: Optional[str] = None
    errors: List[Tuple[Optional[int], str]] = dataclasses.field(default_factory=list)

    def __bool__(self):
        return self.valid


# lxml keeps the error log on the shared, cached XMLSchema object
_SCHEMA_LOCK = threading.Lock()


@functools.lru_cache(maxsize=None)
def _load_schema(schema_path):
    """Compile an .xsd once per process."""
    return lxml.etree.XMLSchema(lxml.etree.parse(schema_path))


_BOM = "\ufeff"


def _parse(xml_input, parser=None):
    """
    Parse a path or binary stream with a new parser.

    On a syntax error, err.parse_errors holds this parse's (line, message) list.
    XMLSyntaxError.error_log can also hold errors from earlier parses, the
    parser's own error_log does not.
    """
    parser = parser or lxml.etree.XMLParser()
    try:
        return lxml.etree.parse(xml_input, parser)
    except lxml.etree.XMLSyntaxError as err:
        err.parse_errors = [(entry.line, entry.message) for entry in parser.error_log]
        raise


def _parse_text(text):
    """Parse XML text that is already decoded, ignoring any encoding declaration."""
    data = text.lstrip(_BOM).encode("utf-8")
    # the encoding argument overrides the document's own declaration
    return _parse(io.BytesIO(data), lxml.etree.XMLParser(encoding="utf-8"))


def _source_path(source, kind=None):
    """Return the file path if this source will be read as a path, else None."""
    if kind == "path" or isinstance(source, os.PathLike):
        return os.fspath(source)
    if (
        kind is None
        and isinstance(source, str)
        and not source.lstrip(_BOM).lstrip().startswith("<")
    ):
        return source
    return None


def _to_document(source, kind=None):
    """
    Turn any supported XML source into (ElementTree, name).

    kind is None to guess, "xml" for XML content, or "path" for a file path.
    name is the file name if one is known, else None.
    """
    source_path = _source_path(source, kind)
    if source_path is not None:
        return _parse(source_path), source_path

    if isinstance(source, lxml.etree._ElementTree):  # pylint: disable=protected-access
        return source, None
    if lxml.etree.iselement(source):
        return source.getroottree(), None

    if isinstance(source, str):
        return _parse_text(source), None

    if isinstance(source, (bytes, bytearray, memoryview)):
        return _parse(io.BytesIO(bytes(source))), None

    if hasattr(source, "read"):
        name = getattr(source, "name", None)
        if not isinstance(name, str):
            name = None
        data = source.read()
        if isinstance(data, str):
            return _parse_text(data), name
        return _parse(io.BytesIO(data)), name

    raise TypeError("unsupported XML source type: %s" % type(source).__name__)


def _validate(  # pylint: disable=too-many-locals,too-many-statements
    source, schema_pathnames, filename, kind, verbose
):
    """Validate one XML source. Prints today's validate_xml report when verbose."""

    if not schema_pathnames:
        schema_pathnames = SCHEMA_FILES

    # used in messages before the document's own name is known
    display_name = filename
    if display_name is None:
        display_name = _source_path(source, kind)

    # parse xml
    try:
        xml_doc_obj, source_name = _to_document(source, kind)

    except TypeError:
        raise

    # check for XML syntax errors
    except lxml.etree.XMLSyntaxError as err:
        if verbose:
            print("XML Syntax Error in: %s" % display_name)
            print(err)
        errors = getattr(err, "parse_errors", None) or [(err.lineno, str(err))]
        return ValidationResult(valid=False, errors=errors)

    # check for file IO error
    except OSError:
        if verbose:
            print("Invalid File: %s" % display_name)
        return ValidationResult(
            valid=False, errors=[(None, "Invalid File: %s" % display_name)]
        )

    # all other errors
    except Exception as err:
        if verbose:
            print(err)
        return ValidationResult(valid=False, errors=[(None, str(err))])

    if filename is None:
        filename = source_name
    if display_name is None:
        display_name = filename if filename is not None else "<xml>"

    inferred_schema_path = None
    lower_filename = (filename or "").lower()
    if ".ojo" in lower_filename:
        inferred_schema_name = "BESOJO.xsd"
    elif ".besdomain" in lower_filename:
        inferred_schema_name = "BESDomain.xsd"
    else:
        inferred_schema_name = infer_xml_schema(xml_doc_obj)
    for schema in schema_pathnames:
        if inferred_schema_name in schema:
            inferred_schema_path = schema

    if not inferred_schema_path:
        message = "no schema to validate %s (inferred schema name: %s)" % (
            display_name,
            inferred_schema_name,
        )
        if verbose:
            print("WARNING: " + message)
        return ValidationResult(valid=False, errors=[(None, message)])

    # validate using schema:
    try:
        xml_schema = _load_schema(inferred_schema_path)
        with _SCHEMA_LOCK:
            is_valid = xml_schema.validate(xml_doc_obj)
            errors = [(entry.line, entry.message) for entry in xml_schema.error_log]
    except Exception as err:
        if verbose:
            print(err)
        return ValidationResult(
            valid=False, schema=inferred_schema_path, errors=[(None, str(err))]
        )

    if is_valid:
        return ValidationResult(valid=True, schema=inferred_schema_path)

    if verbose:
        print("Schema Validation Error in: %s" % display_name)
        print("  validated against schema: %s" % inferred_schema_path)
        for line, message in errors:
            print(f"  Line {line}: {message}")
    return ValidationResult(valid=False, schema=inferred_schema_path, errors=errors)


def validate_bes(
    source=None, schema_pathnames=None, filename=None, *, xml=None, path=None
):
    """
    Validate BES XML from a path, str, bytes, stream, or parsed lxml tree.

    Give exactly one of `source` (type is guessed), `xml=` (XML content), or `path=`
    (a file path). `filename` enables the .ojo / .BESDomain schema rules for
    in-memory XML; it defaults to the path or the stream's `.name`.
    Never prints. Returns a ValidationResult, which is truthy when valid.
    """
    given = [
        (value, kind)
        for value, kind in ((source, None), (xml, "xml"), (path, "path"))
        if value is not None
    ]
    if len(given) != 1:
        raise TypeError("validate_bes() takes exactly one of source, xml=, or path=")
    value, kind = given[0]
    return _validate(value, schema_pathnames, filename, kind, verbose=False)


def validate_xml(file_pathname, schema_pathnames=None, verbose=True):
    """This will validate a single XML file against the schema."""
    kind = "path" if isinstance(file_pathname, (str, os.PathLike)) else None
    return bool(_validate(file_pathname, schema_pathnames, None, kind, verbose))


def validate_all_files(folder_path=".", file_extensions=(".bes", ".ojo")):
    """Validate all xml files in a folder and subfolders."""
    # https://stackoverflow.com/questions/3964681/find-all-files-in-a-directory-with-extension-txt-in-python

    count_errors = 0
    count_files = 0
    schema_pathnames = SCHEMA_FILES

    for root, dirs, files in os.walk(folder_path):
        # do not scan within .git folders, at any depth
        # (editing dirs in place stops os.walk from descending into them)
        dirs[:] = [folder for folder in dirs if folder != ".git"]
        for file in files:
            # process all files ending with `file_extensions`
            if file.lower().endswith(file_extensions):
                count_files = count_files + 1
                file_path = os.path.join(root, file)
                result = validate_xml(file_path, schema_pathnames)
                if not result:
                    count_errors = count_errors + 1

    print("%d errors found in %d xml files" % (count_errors, count_files))
    return count_errors


def main(folder_path=".", file_extensions=(".bes", ".ojo")):
    """Run this function by default."""

    # run the validation, get the number of errors
    count_errors = validate_all_files(folder_path, file_extensions)

    # return the number of errors as the exit code
    sys.exit(count_errors)


if __name__ == "__main__":
    main()
