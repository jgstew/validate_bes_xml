"""
Tests for the site and signature schemas, and how a schema is picked (issue #19).

tests/conftest.py puts the local src first on sys.path.
"""

import os.path
import shutil

import example_paths
import lxml.etree  # pylint: disable=import-error
import pytest
from example_paths import BAD_EXAMPLES_DIR, GOOD_EXAMPLES_DIR, SCHEMAS_DIR

import validate_bes_xml  # pylint: disable=import-error

Status = validate_bes_xml.Status

XSI = 'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'


def schema_name(result):
    """Return the file name of the schema a result used, or None."""
    return None if result.schema is None else os.path.basename(result.schema)


def validate_text(text, **kwargs):
    """Validate XML given as a str."""
    return validate_bes_xml.validate_bes(xml=text, **kwargs)


# ---------------------------------------------------------------------------
# example files
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "file_name, schema",
    [
        ("siteConfig.xml", "SiteConfig.xsd"),
        ("site.xml", "Site.xsd"),
        ("digest.xml", "Digest.xsd"),
        ("SoftwareIdentityCatalog.xml", "SoftwareIdentityCatalog.xsd"),
    ],
)
def test_good_site_files_are_valid(file_name, schema):
    """Each kind of site file validates against the schema named for its root."""
    result = validate_bes_xml.validate_bes(
        path=os.path.join(GOOD_EXAMPLES_DIR, file_name)
    )
    assert result.status is Status.VALID
    assert schema_name(result) == schema


@pytest.mark.parametrize(
    "file_name, schema, line, message",
    [
        (
            "siteConfig_duplicate_BesFileDir.xml",
            "SiteConfig.xsd",
            4,
            "Element 'BesFileDir': This element is not expected.",
        ),
        (
            "siteConfig_out_of_order.xml",
            "SiteConfig.xsd",
            4,
            "Element 'BesFileDir': This element is not expected.",
        ),
        (
            "digest_unsupported_period.xml",
            "Digest.xsd",
            3,
            "The value 'PT10M' is not an element of the set",
        ),
        (
            # xs:string keeps the spaces, so a padded value is not in the set
            "digest_padded_period.xml",
            "Digest.xsd",
            3,
            "The value ' PT15M ' is not an element of the set",
        ),
        (
            "digest_out_of_order.xml",
            "Digest.xsd",
            4,
            "Element 'Relevance': This element is not expected.",
        ),
        (
            "site_two_relevance.xml",
            "Site.xsd",
            4,
            "Element 'Relevance': This element is not expected.",
        ),
        (
            "SoftwareIdentityCatalog_bad_size.xml",
            "SoftwareIdentityCatalog.xsd",
            8,
            "The value '12a' is not accepted by the pattern '[0-9]*'",
        ),
        (
            "SoftwareIdentityCatalog_three_or.xml",
            "SoftwareIdentityCatalog.xsd",
            13,
            "Element 'OR': This element is not expected.",
        ),
    ],
)
def test_bad_site_files_are_invalid(file_name, schema, line, message):
    """Each bad site file fails its schema, at the line of the problem."""
    result = validate_bes_xml.validate_bes(
        path=os.path.join(BAD_EXAMPLES_DIR, file_name)
    )
    assert result.status is Status.INVALID
    assert schema_name(result) == schema
    # one error, so the fixture doesn't also fail for an unintended reason
    assert len(result.errors) == 1
    assert result.errors[0][0] == line
    assert message in result.errors[0][1]


def test_extended_signature_is_valid():
    """A signature can hold an ExtendedSignature instead of AND."""
    result = validate_text(
        '<SoftwareIdentityCatalog><Software name="n" vendor="v" version="*">'
        "<Signature><ExtendedSignature><![CDATA[<x/>]]></ExtendedSignature>"
        "</Signature></Software></SoftwareIdentityCatalog>"
    )
    assert result.status is Status.VALID


def test_signature_version_must_start_with_a_number():
    """Software/@version must match ([0-9]{1,18}\\..*)|\\*."""
    result = validate_text(
        '<SoftwareIdentityCatalog><Software name="n" vendor="v" version="any">'
        "<Signature><ExtendedSignature/></Signature></Software>"
        "</SoftwareIdentityCatalog>"
    )
    assert result.status is Status.INVALID


# ---------------------------------------------------------------------------
# files that share a name with a site file, but are something else
# ---------------------------------------------------------------------------


def test_sitemap_named_site_xml_has_no_schema():
    """A sitemap is not a BigFix site.xml, and no schema applies to it."""
    result = validate_bes_xml.validate_bes(
        xml=b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"/>',
        filename="site.xml",
    )
    assert result.status is Status.NO_SCHEMA
    assert result.schema is None


# ---------------------------------------------------------------------------
# schema names match without regard to case
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "root, schema",
    [
        ("site", "Site.xsd"),
        ("digest", "Digest.xsd"),
        ("siteconfig", "SiteConfig.xsd"),
        ("SITE", "Site.xsd"),
    ],
)
def test_wrong_case_root_gets_a_schema_error(root, schema):
    """A root tag in the wrong case finds its schema, which then rejects it."""
    result = validate_text("<%s/>" % root)
    assert result.status is Status.INVALID
    assert schema_name(result) == schema
    assert "No matching global declaration" in result.errors[0][1]


def test_eclipse_update_site_xml_is_invalid_not_no_schema():
    """
    An Eclipse update-site site.xml has a lowercase <site> root, so it is invalid.

    This follows from matching names without regard to case, as chosen in
    #19. A tool that skips no_schema files must exclude these some other way.
    """
    result = validate_bes_xml.validate_bes(
        xml='<site><feature url="f.jar" id="a" version="1.0"/></site>',
        filename="site.xml",
    )
    assert result.status is Status.INVALID
    assert schema_name(result) == "Site.xsd"


def test_lowercase_schema_location_finds_the_bundled_schema():
    """The example repo ships siteConfig.xsd; it matches SiteConfig.xsd."""
    result = validate_text(
        "<SiteConfig %s "
        'xsi:noNamespaceSchemaLocation="../siteConfig.xsd">'
        "<BesFileDir>Fixlets</BesFileDir></SiteConfig>" % XSI
    )
    assert result.status is Status.VALID
    assert schema_name(result) == "SiteConfig.xsd"
    assert result.inferred_schema == "siteConfig.xsd"


def test_lowercase_schema_file_matches_root_tag(tmp_path):
    """A schema file named in another case is used for a matching root tag."""
    lower = tmp_path / "site.xsd"
    shutil.copy(os.path.join(SCHEMAS_DIR, "Site.xsd"), lower)
    result = validate_text("<Site/>", schema_pathnames=[str(lower)])
    assert result.status is Status.VALID
    assert result.schema == str(lower)


def test_bundled_schema_wins_over_another_case(tmp_path):
    """On a case-insensitive name clash, the bundled copy is still used."""
    other = tmp_path / "site.xsd"
    shutil.copy(os.path.join(SCHEMAS_DIR, "Site.xsd"), other)
    bundled = os.path.join(SCHEMAS_DIR, "Site.xsd")
    result = validate_text("<Site/>", schema_pathnames=[str(other), bundled])
    assert os.path.realpath(result.schema) == os.path.realpath(bundled)


def test_non_bundled_tie_break_is_sorted_order(tmp_path):
    """Without a bundled copy, the first path in sorted order wins."""
    paths = []
    for folder, name in (("b", "site.xsd"), ("a", "SITE.xsd")):
        (tmp_path / folder).mkdir()
        target = tmp_path / folder / name
        shutil.copy(os.path.join(SCHEMAS_DIR, "Site.xsd"), target)
        paths.append(str(target))
    result = validate_text("<Site/>", schema_pathnames=paths)
    assert result.schema == min(paths)


# ---------------------------------------------------------------------------
# a root attribute names the schema; the root tag is the fallback
# ---------------------------------------------------------------------------


def test_root_attribute_is_used_before_the_root_tag():
    """A schema named by a root attribute wins when it exists."""
    result = validate_text(
        '<Site %s xsi:noNamespaceSchemaLocation="Digest.xsd"/>' % XSI
    )
    assert schema_name(result) == "Digest.xsd"
    assert result.inferred_schema == "Digest.xsd"
    assert result.status is Status.INVALID


def test_root_tag_is_the_fallback_for_an_unknown_attribute_schema():
    """An attribute naming a missing .xsd falls back to the root tag's schema."""
    result = validate_text(
        '<SiteConfig %s xsi:noNamespaceSchemaLocation="mine.xsd">'
        "<BesFileDir>Fixlets</BesFileDir></SiteConfig>" % XSI
    )
    assert result.status is Status.VALID
    assert schema_name(result) == "SiteConfig.xsd"
    assert result.inferred_schema == "SiteConfig.xsd"


def test_no_match_for_attribute_or_root_tag_reports_the_attribute():
    """With no match at all, the message and inferred_schema are the first name."""
    result = validate_text('<Foo %s xsi:noNamespaceSchemaLocation="mine.xsd"/>' % XSI)
    assert result.status is Status.NO_SCHEMA
    assert result.inferred_schema == "mine.xsd"
    assert result.errors == [
        (None, "no schema to validate <xml> (inferred schema name: mine.xsd)")
    ]


def test_infer_xml_schema_still_returns_the_attribute():
    """The public infer_xml_schema() keeps returning a single name."""
    root = lxml.etree.fromstring(
        '<Site %s xsi:noNamespaceSchemaLocation="mine.xsd"/>' % XSI
    )
    tree = lxml.etree.ElementTree(root)
    assert validate_bes_xml.infer_xml_schema(tree) == "mine.xsd"


@pytest.mark.parametrize(
    "filename, inferred_schema",
    [("x.ojo", "BESOJO.xsd"), ("x.BESDomain", "BESDomain.xsd")],
)
def test_file_name_rules_do_not_fall_back(filename, inferred_schema):
    """The .ojo / .BESDomain rules name one schema, with no root-tag fallback."""
    only_bes = [os.path.join(SCHEMAS_DIR, "BES.xsd")]
    result = validate_text("<BES/>", filename=filename, schema_pathnames=only_bes)
    assert result.status is Status.NO_SCHEMA
    assert result.inferred_schema == inferred_schema


@pytest.mark.parametrize(
    "filename",
    [
        "/repos/my.ojo.content/siteConfig.xml",
        "repos/foo.BESDomain/Fixlets/siteConfig.xml",
        "C:\\repos\\my.ojo.content\\siteConfig.xml",
    ],
)
def test_file_name_rules_ignore_folder_names(filename):
    """Only the file name picks BESOJO.xsd or BESDomain.xsd, not a folder."""
    result = validate_text(
        "<SiteConfig><BesFileDir>Fixlets</BesFileDir></SiteConfig>",
        filename=filename,
    )
    assert result.status is Status.VALID
    assert schema_name(result) == "SiteConfig.xsd"


def test_bes_with_unknown_schema_location_falls_back_to_bes_xsd():
    """<BES xsi:noNamespaceSchemaLocation="mine.xsd"> used to have no schema."""
    with open(example_paths.GOOD_BES, encoding="utf-8") as file_obj:
        text = file_obj.read()
    old_location = 'xsi:noNamespaceSchemaLocation="BES.xsd"'
    assert old_location in text
    text = text.replace(old_location, 'xsi:noNamespaceSchemaLocation="mine.xsd"', 1)
    result = validate_text(text)
    assert result.status is Status.VALID
    assert schema_name(result) == "BES.xsd"
    assert result.inferred_schema == "BES.xsd"
