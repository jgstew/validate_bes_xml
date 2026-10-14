"""Paths to the repository folders and example files used by the tests."""

import os.path

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOOD_EXAMPLES_DIR = os.path.join(REPO_ROOT, "tests", "examples", "good")
BAD_EXAMPLES_DIR = os.path.join(REPO_ROOT, "tests", "examples", "bad")
SCHEMAS_DIR = os.path.join(REPO_ROOT, "src", "validate_bes_xml", "schemas")
# the .xsd files shipped in the package, by file name
BUNDLED_SCHEMAS = {
    name for name in os.listdir(SCHEMAS_DIR) if name.lower().endswith(".xsd")
}

GOOD_BES = os.path.join(GOOD_EXAMPLES_DIR, "FixletDebugger.bes")
GOOD_OJO = os.path.join(GOOD_EXAMPLES_DIR, "minimal_wizard.ojo")
BAD_BES = os.path.join(BAD_EXAMPLES_DIR, "example_bes.bes")
