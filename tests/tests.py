"""test validate_bes_xml"""

import argparse
import os.path
import sys

# check for --test_pip arg
parser = argparse.ArgumentParser()
parser.add_argument(
    "--test_pip", help="to test package installed with pip", action="store_true"
)
args = parser.parse_args()

if not args.test_pip:
    # add module folder to import paths for testing local src
    sys.path.append(
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
    )
    # reverse the order so we make sure to get the local src module, not pip package
    sys.path.reverse()

import validate_bes_xml  # pylint: disable=import-error,wrong-import-position

print(validate_bes_xml.__file__)


# make sure we are testing the right place:
if args.test_pip:
    # this will false positive on windows
    assert "/src/" not in validate_bes_xml.__file__
else:
    # check for only 'src' so it will work on windows and non-windows
    assert "src" in validate_bes_xml.__file__


# must be 4 valid schema files:
assert 4 == len(validate_bes_xml.validate_bes_xml.find_schema_files())

# run the script
num_errors = validate_bes_xml.validate_bes_xml.validate_all_files()

try:
    assert num_errors == 2
except AssertionError:
    print("Error: Tests failed")
    sys.exit(num_errors)

# tests pass, return 0:
print("Success: Tests pass")
sys.exit(0)
