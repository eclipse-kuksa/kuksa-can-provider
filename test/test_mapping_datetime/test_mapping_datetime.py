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

from dbcfeederlib.dbc2vssmapper import Mapper, VSSObservation


test_path = os.path.dirname(os.path.abspath(__file__))
dbc_file_names = [test_path + "/../../Model3CAN.dbc"]


def _datetime_transform(inputs):
    return {
        "datetime": {
            "format": "iso8601",
            "inputs": inputs,
        }
    }


def _load_mapper(tmp_path, transform):
    mapping = {
        "A": {
            "type": "branch",
            "description": "Branch A.",
            "children": {
                "DateTimeValue": {
                    "type": "sensor",
                    "datatype": "string",
                    "description": "Datetime test signal.",
                    "dbc": {
                        "signal": "S1",
                        "transform": transform,
                    },
                }
            },
        }
    }
    mapping_path = tmp_path / "mapping_datetime.json"
    mapping_path.write_text(json.dumps(mapping), encoding="utf-8")
    return Mapper(str(mapping_path), dbc_file_names)


def _default_inputs():
    return {
        "year": "Year",
        "month": "Month",
        "day": "Day",
        "hour": "Hours",
        "minute": "Minutes",
        "second": "Seconds",
    }


def _observation(raw_value):
    return VSSObservation("S1", "A.DateTimeValue", raw_value, 1.0, "frame")


def test_datetime_transform_is_parsed_into_mapping(tmp_path):
    inputs = _default_inputs()
    mapper = _load_mapper(tmp_path, _datetime_transform(inputs))

    mapping = mapper.get_dbc2vss_mapping("S1", "A.DateTimeValue")

    assert mapping is not None
    assert mapping.transform is not None
    assert mapping.transform["datetime"]["format"] == "iso8601"
    assert mapping.transform["datetime"]["inputs"] == inputs


def test_datetime_transform_frame_to_iso8601(tmp_path):
    mapper = _load_mapper(tmp_path, _datetime_transform(_default_inputs()))
    mapping = mapper.get_dbc2vss_mapping("S1", "A.DateTimeValue")

    assert mapping is not None
    result = mapping.transform_frame(_observation({
        "Year": 2026,
        "Month": 10,
        "Day": 5,
        "Hours": 14,
        "Minutes": 7,
        "Seconds": 9,
    }))
    assert result == "2026-10-05T14:07:09"


@pytest.mark.parametrize(
    ("day_value", "expected"),
    [
        (5.5, "2026-10-05T12:30:13"),
        (5.1, "2026-10-05T02:54:13"),
    ],
)
def test_datetime_transform_supports_fractional_day(tmp_path, day_value, expected):
    mapper = _load_mapper(tmp_path, _datetime_transform(_default_inputs()))
    mapping = mapper.get_dbc2vss_mapping("S1", "A.DateTimeValue")

    assert mapping is not None
    result = mapping.transform_frame(_observation({
        "Year": 2026,
        "Month": 10,
        "Day": day_value,
        "Hours": 0,
        "Minutes": 30,
        "Seconds": 12.6,
    }))
    assert result == expected


def test_datetime_transform_supports_timezone_offset_inputs(tmp_path):
    inputs = _default_inputs()
    inputs["local_hour_offset"] = "HourOffset"
    inputs["local_minute_offset"] = "MinuteOffset"
    mapper = _load_mapper(tmp_path, _datetime_transform(inputs))
    mapping = mapper.get_dbc2vss_mapping("S1", "A.DateTimeValue")

    assert mapping is not None
    result = mapping.transform_frame(_observation({
        "Year": 2026,
        "Month": 10,
        "Day": 5,
        "Hours": 14,
        "Minutes": 7,
        "Seconds": 9,
        "HourOffset": 2,
        "MinuteOffset": 30,
    }))
    assert result == "2026-10-05T14:07:09+02:30"


def test_datetime_transform_invalid_frame_values_return_none(tmp_path, caplog):
    mapper = _load_mapper(tmp_path, _datetime_transform(_default_inputs()))
    mapping = mapper.get_dbc2vss_mapping("S1", "A.DateTimeValue")

    assert mapping is not None
    result = mapping.transform_frame(_observation({
        "Year": 2026,
        "Month": 13,
        "Day": 5,
        "Hours": 14,
        "Minutes": 7,
        "Seconds": 9,
    }))

    assert result is None
    assert any(
        logger == "dbcfeederlib.dbc2vssmapper"
        and level == logging.ERROR
        and message.startswith("Error creating datetime from frame")
        for logger, level, message in caplog.record_tuples
    )


def test_datetime_transform_missing_frame_input_returns_none(tmp_path, caplog):
    mapper = _load_mapper(tmp_path, _datetime_transform(_default_inputs()))
    mapping = mapper.get_dbc2vss_mapping("S1", "A.DateTimeValue")

    assert mapping is not None
    result = mapping.transform_frame(_observation({
        "Year": 2026,
        "Month": 10,
        "Day": 5,
        "Hours": 14,
        "Minutes": 7,
    }))

    assert result is None
    assert any(
        logger == "dbcfeederlib.dbc2vssmapper"
        and level == logging.ERROR
        and message.startswith("Error extracting datetime inputs from frame")
        for logger, level, message in caplog.record_tuples
    )


@pytest.mark.parametrize(
    ("transform", "error_message"),
    [
        (
            {"datetime": "iso8601"},
            "Transformation definition for A.DateTimeValue has a \"datetime\" property that is not a dict",
        ),
        (
            {"datetime": {}},
            "Transformation definition for A.DateTimeValue has no \"format\" property",
        ),
        (
            {"datetime": {"format": 1}},
            "Transformation definition for A.DateTimeValue has a \"format\" property that is not a str",
        ),
        (
            {"datetime": {"format": "rfc3339"}},
            'Transformation definition for A.DateTimeValue has a "format" property '
            'that is not supported yet: rfc3339',
        ),
        (
            {"datetime": {"format": "iso8601"}},
            "Transformation definition for A.DateTimeValue has no \"inputs\" property",
        ),
        (
            {"datetime": {"format": "iso8601", "inputs": []}},
            "Transformation definition for A.DateTimeValue has a \"inputs\" property that is not a dict",
        ),
        (
            {
                "datetime": {
                    "format": "iso8601",
                    "inputs": {
                        "year": "Year",
                        "month": "Month",
                        "day": "Day",
                        "hour": "Hours",
                        "minute": "Minutes",
                    },
                }
            },
            "Transformation definition for A.DateTimeValue has missing required \"inputs\": {'second'}",
        ),
        (
            {
                "datetime": {
                    "format": "iso8601",
                    "inputs": {
                        **_default_inputs(),
                        "nanoseconds": "Nanoseconds",
                    },
                }
            },
            'Transformation definition for A.DateTimeValue has a "inputs" property '
            "with unsupported inputs: {'nanoseconds'}",
        ),
        (
            {
                "datetime": {
                    "format": "iso8601",
                    "inputs": {
                        **_default_inputs(),
                        "year": 2026,
                    },
                }
            },
            "Transformation definition for A.DateTimeValue has input \"year\" that is not mapped to a str",
        ),
    ],
)
def test_invalid_datetime_definitions_are_rejected(tmp_path, caplog, transform, error_message):
    with pytest.raises(SystemExit) as excinfo:
        _load_mapper(tmp_path, transform)

    assert excinfo.value.code == -1
    assert ("dbcfeederlib.dbc2vssmapper", logging.ERROR, error_message) in caplog.record_tuples
