#!/usr/local/python
"""
# pylint: disable=line-too-long
"""

import io
import os
import sys

try:
    import lxml.etree  # pylint: disable=import-error
except ImportError:
    import lxml


def infer_xml_schema(xml_doc_obj):
    try:
        # look for ".xsd" attribute on root tag
        for name, value in xml_doc_obj.getroot().items():
            if ".xsd" in value.lower():
                return value
    except AttributeError:
        return "ERROR: default? BES.xsd"

    try:
        # use name of root tag as the name of the xsd
        return xml_doc_obj.getroot().tag + ".xsd"
    except:
        return "ERROR: default? BES.xsd"

    return "default? BES.xsd"


def validate_xml(file_pathname, schema_pathnames):
    """This will validate a single XML file against the schema"""
    # parse xml
    try:
        xml_doc_obj = lxml.etree.parse(file_pathname)
        # print('XML well formed, syntax ok.')

    # check for file IO error
    except IOError:
        print("Invalid File: %s" % file_pathname)
        return False

    # check for XML syntax errors
    except lxml.etree.XMLSyntaxError as err:
        print("XML Syntax Error in: %s" % file_pathname)
        print(err)
        return False

    # all other errors
    except Exception as err:  # pylint: disable=broad-except
        print(err)
        return False

    # TODO check if xml is valid to schema
    print( file_pathname )

    inferred_schema_path = None
    # print( infer_xml_schema(xml_doc_obj) )
    for schema in schema_pathnames:
        if infer_xml_schema(xml_doc_obj) in schema:
            print( schema )
            inferred_schema_path = schema
    
    if not inferred_schema_path:
        print("WARNING: no schema to validate " + file_pathname)

    return True


def validate_all_files(
    folder_path=".", file_extensions=(".bes", ".xml")
):
    """Validate all xml files in a folder and subfolders"""
    # https://stackoverflow.com/questions/3964681/find-all-files-in-a-directory-with-extension-txt-in-python

    count_errors = 0
    count_files = 0
    schema_pathnames = find_schema_files()

    for root, dirs, files in os.walk(folder_path):  # pylint: disable=unused-variable
        for file in files:
            # do not scan within .git folder
            if not root.startswith((".git", "./.git")):
                # process all files ending with `file_extensions`
                if file.lower().endswith(file_extensions):
                    count_files = count_files + 1
                    file_path = os.path.join(root, file)
                    result = validate_xml(file_path, schema_pathnames)
                    if not result:
                        count_errors = count_errors + 1

    print("%d errors found in %d xml files" % (count_errors, count_files))
    return count_errors

def find_schema_files(folder_path=None):
    # use set to get only unique folders
    folder_set = set()
    if folder_path:
        folder_set.add(folder_path)
    folder_set.add( os.path.dirname(os.path.realpath(__file__)) )
    folder_set.add( os.getcwd() )

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
                # test xsd parsing
                file_item_path = os.path.join(folder_item, file_item)
                try:
                    lxml.etree.XMLSchema(lxml.etree.parse(file_item_path))
                    schema_files_set.add(file_item_path)
                except lxml.etree.XMLSchemaParseError as err:
                    print("WARNING: xsd did not parse: " + file_item_path)

    return schema_files_set

def main(folder_path=".", file_extensions=(".bes", ".xml")):
    """Run this function by default"""

    # run the validation, get the number of errors
    count_errors = validate_all_files(folder_path, file_extensions)

    # return the number of errors as the exit code
    sys.exit(count_errors)


if __name__ == "__main__":
    main()
