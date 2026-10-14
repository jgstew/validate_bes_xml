"""
The inputs from issue #17, shared by test_result_compat.py and test_status.py.

Each case is (case_id, make_kwargs). make_kwargs(tmp_path) returns the keyword
arguments for validate_bes(), so cases that need files on disk can build them.
"""

import concurrent.futures

import lxml.etree  # pylint: disable=import-error
from example_paths import GOOD_BES

import validate_bes_xml  # pylint: disable=import-error

# a schema that is well-formed XML but does not compile: the type does not exist
UNCOMPILABLE_XSD = (
    '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">'
    '<xs:element name="BES" type="nope"/>'
    "</xs:schema>"
)

# the root tag must not match either, since #19 falls back to it
XSI_LOCATION = (
    b'<Foo xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
    b'xsi:noNamespaceSchemaLocation="mine.xsd"/>'
)

EXTERNAL_ENTITY = (
    b'<?xml version="1.0"?>\n'
    b'<!DOCTYPE BES [<!ENTITY x SYSTEM "file:///etc/passwd">]><BES>&x;</BES>'
)


def _read_good_bes():
    with open(GOOD_BES, "rb") as file_obj:
        return file_obj.read()


def _uncompilable_schema(tmp_path):
    schema_path = tmp_path / "BES.xsd"
    schema_path.write_text(UNCOMPILABLE_XSD, encoding="utf-8")
    return {"source": b"<BES/>", "schema_pathnames": [str(schema_path)]}


CASES = [
    ("valid_bes", lambda tmp_path: {"source": _read_good_bes()}),
    ("schema_invalid", lambda tmp_path: {"source": b"<BES><Nope/></BES>"}),
    ("empty_bytes", lambda tmp_path: {"source": b""}),
    ("whitespace_only", lambda tmp_path: {"source": b"   \n"}),
    ("comment_only", lambda tmp_path: {"source": b"<!-- c -->"}),
    ("pi_only", lambda tmp_path: {"source": b"<?pi x?>"}),
    ("truncated", lambda tmp_path: {"source": b"<BES><Task>"}),
    (
        "bogus_encoding",
        lambda tmp_path: {"source": b'<?xml version="1.0" encoding="bogus"?><BES/>'},
    ),
    ("undefined_entity", lambda tmp_path: {"source": b"<BES>&nope;</BES>"}),
    ("external_entity", lambda tmp_path: {"source": EXTERNAL_ENTITY}),
    ("unknown_root", lambda tmp_path: {"source": b"<Foo/>"}),
    ("namespaced_root", lambda tmp_path: {"source": b'<a xmlns="urn:x"/>'}),
    ("xsi_location", lambda tmp_path: {"source": XSI_LOCATION}),
    (
        "no_matching_schema_path",
        lambda tmp_path: {
            "source": b"<BES/>",
            "schema_pathnames": ["/nowhere/Other.xsd"],
        },
    ),
    ("missing_file", lambda tmp_path: {"path": "does_not_exist.bes"}),
    ("directory", lambda tmp_path: {"path": "."}),
    (
        "tree_without_root",
        lambda tmp_path: {
            "source": lxml.etree.ElementTree(lxml.etree.Comment("x")),
        },
    ),
    ("uncompilable_schema", _uncompilable_schema),
]

CASE_IDS = [case_id for case_id, _ in CASES]


# a mix of valid, invalid, no-schema and syntax-error inputs
CONCURRENT_CASE_IDS = ("valid_bes", "schema_invalid", "unknown_root", "truncated")


def serial_and_concurrent_results(tmp_path, repeat=25, workers=8):
    """
    Validate a mix of inputs one at a time, then repeatedly in a thread pool.

    Returns (serial, concurrent): serial has one result per input, and
    concurrent[i] is the threaded result for the input serial[i % len(serial)].
    """
    kwargs_list = [
        make_kwargs(tmp_path)
        for case_id, make_kwargs in CASES
        if case_id in CONCURRENT_CASE_IDS
    ]
    serial = [validate_bes_xml.validate_bes(**kwargs) for kwargs in kwargs_list]
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        concurrent_results = list(
            executor.map(
                lambda kwargs: validate_bes_xml.validate_bes(**kwargs),
                kwargs_list * repeat,
            )
        )
    return serial, concurrent_results
