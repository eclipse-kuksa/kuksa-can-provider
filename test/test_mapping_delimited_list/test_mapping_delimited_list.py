#!/usr/bin/python3

########################################################################
# Copyright (c) 2026 Contributors to the Eclipse Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0
########################################################################

import json
import logging
import os

import pytest  # type: ignore

from dbcfeederlib.dbc2vssmapper import Mapper, VSSDelimitedList

test_path = os.path.dirname(os.path.abspath(__file__))
dbc_file_names = [test_path + "/../../Model3CAN.dbc"]


def _load_mapper(tmp_path, datatype="string", delimited_list=None):
    dbc_mapping = {
        "signal": "S1",
    }
    if delimited_list is not None:
        dbc_mapping["delimited_list"] = delimited_list
    mapping = {
        "A": {
            "type": "branch",
            "description": "Branch A.",
            "children": {
                "DelimitedValue": {
                    "type": "sensor",
                    "datatype": datatype,
                    "description": "Delimited list test signal.",
                    "dbc": dbc_mapping,
                }
            },
        }
    }
    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(json.dumps(mapping), encoding="utf-8")
    return Mapper(str(mapping_path), dbc_file_names)


@pytest.mark.parametrize(
    ("delimiter", "index", "raw_value", "expected"),
    [
        ("|", 0, "front|rear|left", "front"),
        ("|", 1, "front|rear|left", "rear"),
        ("|", 2, "front|rear|left", "left"),
        ("||", 1, "front||rear||left", "rear"),
        ("|", 1, "front||left", ""),
    ],
)
def test_delimited_list_selects_zero_based_item(tmp_path, delimiter, index, raw_value, expected):
    mapper = _load_mapper(tmp_path, delimited_list={"delimiter": delimiter, "index": index})
    mapping = mapper.get_dbc2vss_mapping("S1", "A.DelimitedValue")

    assert mapping is not None
    assert mapping.transform_value([ord(character) for character in raw_value]) == expected


def test_delimited_list_out_of_range_logs_warning_and_returns_empty_string(tmp_path, caplog):
    mapper = _load_mapper(tmp_path, delimited_list={"delimiter": "|", "index": 3})
    mapping = mapper.get_dbc2vss_mapping("S1", "A.DelimitedValue")

    assert mapping is not None
    assert mapping.transform_value([ord(character) for character in "front|rear"]) == ""
    warning = (
        "dbcfeederlib.dbc2vssmapper", logging.WARNING,
        "Delimited list value for A.DelimitedValue is out of range, using empty string"
    )
    assert warning in caplog.record_tuples


def test_delimited_list_is_parsed_into_mapping(tmp_path):
    mapper = _load_mapper(tmp_path, delimited_list={"delimiter": "|", "index": 1})
    mapping = mapper.get_dbc2vss_mapping("S1", "A.DelimitedValue")

    assert mapping is not None
    assert mapping.delimited_list is not None
    assert mapping.delimited_list.get_delimiter() == "|"
    assert mapping.delimited_list.get_index() == 1


def test_list_without_delimited_list_keeps_legacy_join_behavior(tmp_path):
    mapper = _load_mapper(tmp_path)
    mapping = mapper.get_dbc2vss_mapping("S1", "A.DelimitedValue")

    assert mapping is not None
    assert mapping.delimited_list is None
    assert mapping.transform_value([ord(character) for character in "front|rear"]) == "front|rear"


def test_delimited_list_does_not_change_non_string_values(tmp_path):
    mapper = _load_mapper(tmp_path, datatype="uint8", delimited_list={"delimiter": "|", "index": 1})
    mapping = mapper.get_dbc2vss_mapping("S1", "A.DelimitedValue")
    raw_value = [ord(character) for character in "front|rear"]

    assert mapping is not None
    assert mapping.transform_value(raw_value) == raw_value


@pytest.mark.parametrize(
    ("definition", "error_message"),
    [
        ([], "Delimited list definition for A.DelimitedValue is not a dict"),
        ({}, "No delimiter provided in delimited list for S1"),
        ({"delimiter": 1, "index": 0},
         "Delimiter of delimited list for mapping definition of A.DelimitedValue is not a non-empty string"),
        ({"delimiter": "", "index": 0},
         "Delimiter of delimited list for mapping definition of A.DelimitedValue is not a non-empty string"),
        ({"delimiter": "|"}, "No index provided for delimited list in signal S1"),
        ({"delimiter": "|", "index": "1"},
         "Index of delimited list for mapping definition of A.DelimitedValue is not a non-negative integer"),
        ({"delimiter": "|", "index": -1},
         "Index of delimited list for mapping definition of A.DelimitedValue is not a non-negative integer"),
        ({"delimiter": "|", "index": True},
         "Index of delimited list for mapping definition of A.DelimitedValue is not a non-negative integer"),
    ],
)
def test_invalid_delimited_list_definition_is_rejected(tmp_path, caplog, definition, error_message):
    with pytest.raises(SystemExit) as excinfo:
        _load_mapper(tmp_path, delimited_list=definition)

    assert excinfo.value.code == -1
    error = ("dbcfeederlib.dbc2vssmapper", logging.ERROR, error_message)
    assert error in caplog.record_tuples


def test_delimited_list_get_item_handles_out_of_range_index():
    delimited_list = VSSDelimitedList("|", 2)

    assert delimited_list.get_item("front|rear") == (False, "")
