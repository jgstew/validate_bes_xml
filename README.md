# validate_bes_xml

A python module for validating BigFix XML files and content.

Validates `.bes` and `.ojo` files, Git External Custom Site files
(`siteConfig.xml`, `site.xml`, `digest.xml`) and BigFix Inventory
signatures against the official BigFix XML schemas (bundled with the
module), and reports what is wrong and where when a file does not
validate. Useful locally and as a CI check for repositories of
BigFix content.

## How it works

For each XML file, the validator:

1. Parses the file and reports XML syntax errors, if any.
2. Determines which schema to use, in this order:
   - `.ojo` in the file name -> `BESOJO.xsd`
   - `.BESDomain` in the file name (any case) -> `BESDomain.xsd`
   - an attribute on the root tag referencing an `.xsd` file
     (e.g. `xsi:noNamespaceSchemaLocation="BES.xsd"`)
   - the name of the root tag itself (e.g. `<BES>` -> `BES.xsd`), also
     used when the attribute names an `.xsd` that isn't available
3. Validates the file against that schema and prints the line number and
   reason for every schema violation found.

Bundled schemas:

- `BES.xsd` - Fixlets, Tasks, Analyses, Baselines, Computer Groups, etc.
- `BESAPI.xsd` - BigFix REST API XML
- `BESOJO.xsd` - Wizards / Dashboards (`.ojo` files)
- `BESDomain.xsd` - Domain content
- `SiteConfig.xsd`, `Site.xsd`, `Digest.xsd` - Git External Custom Site
  `siteConfig.xml`, `site.xml` and `digest.xml`
- `SoftwareIdentityCatalog.xsd` - BigFix Inventory signatures

The site and signature schemas come from
[bigfix/RepositorySiteExample](https://github.com/bigfix/RepositorySiteExample)
and [bigfix/CommunityContent](https://github.com/bigfix/CommunityContent),
renamed to match their root elements. See
[`THIRD_PARTY_NOTICES.md`](src/validate_bes_xml/schemas/THIRD_PARTY_NOTICES.md)
for each source, commit and license.

Additional `.xsd` files placed in the current working directory
(or a `schemas` subfolder of it) are picked up automatically.
A schema is matched by its file name, ignoring case (so `siteConfig.xsd`
finds `SiteConfig.xsd`), and the bundled copy is always used over another
file with the same name. An `.xsd` that cannot be read or
parsed is skipped with a warning on stderr.

## Requirements

- Python 3
- [lxml](https://pypi.org/project/lxml/)

## Installation

```sh
pip install validate-bes-xml
```

Or from a clone of this repository:

```sh
pip install .
```

## Usage

### Command line

Validate all `.bes` and `.ojo` files in the current directory and its
subfolders (excluding `.git`):

```sh
python -m validate_bes_xml
```

The command line does not scan `.xml` files, since most XML in a
repository is not BigFix content. Validate site files and signatures from
Python, with `validate_xml()` or `validate_bes()`.

The exit code is the number of files that failed validation, so `0` means
everything validated. This makes it easy to use as a CI check:

```yaml
# example GitHub Actions step
- name: Validate BES XML
  run: |
    pip install validate-bes-xml
    python -m validate_bes_xml
```

Example output for an invalid file:

```
Schema Validation Error in: ./example.bes
  validated against schema: .../validate_bes_xml/schemas/BES.xsd
  Line 2: Element 'BES': Missing child element(s). Expected is one of ( Fixlet, Task, Analysis, SingleAction, SourcedFixletAction, MultipleActionGroup, Baseline, ComputerGroup, CustomSite, ActionSite ).
2 errors found in 71 xml files
```

### Python

```python
import validate_bes_xml

# validate a single file, returns True or False:
validate_bes_xml.validate_xml("example.bes")

# validate all .bes and .ojo files in a folder tree,
# returns the number of files that failed validation:
validate_bes_xml.validate_all_files("path/to/content")

# customize which file extensions are scanned:
validate_bes_xml.validate_all_files(".", file_extensions=(".bes",))
```

To validate XML that is not in a file on disk, or to get the errors back
instead of printed, use `validate_bes()`. It never prints, and returns a
`ValidationResult` that is truthy when valid:

```python
import validate_bes_xml

result = validate_bes_xml.validate_bes(raw_bytes, filename="example.bes")
if not result:
    print("failed against", result.schema)
    for line, message in result.errors:
        print(f"Line {line}: {message}")
```

`validate_bes()` accepts:

- a file path, as a `str` or `pathlib.Path`
- XML text, as a `str` that starts with `<` (a leading BOM is ignored)
- `bytes`, `bytearray`, or `memoryview` (the XML encoding declaration is used)
- a binary or text file-like object
- a parsed `lxml.etree` ElementTree or Element

Use `xml=` or `path=` instead of the first argument to skip guessing
whether a `str` is XML text or a path. Pass `filename=` so in-memory XML
gets the same `.ojo` / `.BESDomain` schema rules as a file. It defaults to
the path, or to the `.name` of an open file.

`ValidationResult` fields:

- `valid`: `True` or `False`
- `schema`: path of the schema that was used, or `None` when the XML did not
  parse or no bundled schema matched
- `errors`: list of `(line, message)` tuples; `line` is `None` when unknown
- `status`: a `validate_bes_xml.Status`, one of the values below
- `inferred_schema`: the schema file name that was looked up, such as
  `"BES.xsd"`, set whenever the XML parsed (even if no schema matched), else
  `None`

| `status` | Meaning |
| --- | --- |
| `"valid"` | parsed, and passed the schema |
| `"invalid"` | parsed, and failed the schema |
| `"syntax_error"` | not well-formed XML |
| `"no_schema"` | parsed, but no schema matched `inferred_schema` |
| `"error"` | anything else: unreadable file, no root element, or a schema that failed to compile |

`Status` members compare equal to their string values, so
`result.status == "no_schema"` and `result.status is Status.NO_SCHEMA` both
work. Only a result with status `"valid"` is truthy: a `"no_schema"` result
is falsy, as before. Test the result, not `result.status`, since every
`Status` member is a non-empty string and so is itself truthy.

To treat "no schema applies" as validity unknown instead of invalid, check
`status`, not whether `line` is `None`:

```python
from validate_bes_xml import Status, validate_bes

result = validate_bes(raw_bytes)
if result.status is Status.NO_SCHEMA:
    print("no schema for", result.inferred_schema)
elif not result:
    print(result.status, result.errors)
```

`status` must agree with `valid`: `ValidationResult(valid=True,
status="invalid")` raises `ValueError`. So to change `valid` with
`dataclasses.replace()`, also pass `status=None` to derive it again, for
example `dataclasses.replace(result, valid=True, status=None)`. Setting
`result.valid` directly does not update `status`.

Each `.xsd` is compiled once per process and reused.

`validate_xml(path, verbose=False)` validates a file without printing.

## Development

Clone the repository, then install the requirements:

```sh
pip install -r requirements.txt
pip install pytest
```

Run the tests from the root of the repository:

```sh
pytest -v
```

The test examples live in `tests/examples`: files in `good` must validate,
files in `bad` must not.

## Related

- [jgstew/bigfix_prefetch](https://github.com/jgstew/bigfix_prefetch)
- [BigFix Developer documentation](https://developer.bigfix.com/)

## License

[MIT](LICENSE)
