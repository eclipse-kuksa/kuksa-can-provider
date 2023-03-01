#!/usr/bin/python3

########################################################################
# Copyright (c) 2023 Robert Bosch GmbH
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

# The intention of file is to test parsing and transformation for various
# constructs


from dbcfeederlib import dbc2vssmapper
import os

# read config only once
path = os.path.dirname(os.path.abspath(__file__)) + "/test.json"
mapper: dbc2vssmapper.Mapper = dbc2vssmapper.Mapper(path)


def test_mapping_read():
    dbc_mapping = mapper["S1"]
    # We have 6 VSS signals using S1
    assert len(dbc_mapping) == 6


def test_no_transform_default():
    mapping = mapper.get_vss_mapping("S1", "A.NoTransformDefault")
    assert mapping is not None
    assert mapping.interval_ms == 1000
    assert mapping.on_change == False
    assert mapping.last_time == 0.0
    assert mapping.last_vss_value is None

    # 1000 ms limit default, should not care about values
    # First shall always be sent
    assert mapping.last_time == 0.0
    assert mapping.time_condition_fulfilled(0.01)
    assert mapping.last_time == 0.01
    assert not mapping.time_condition_fulfilled(0.02)
    assert mapping.last_time == 0.01
    assert not mapping.time_condition_fulfilled(1.00)
    assert mapping.last_time == 0.01
    assert mapping.time_condition_fulfilled(1.02)
    assert mapping.last_time == 1.02
    assert not mapping.time_condition_fulfilled(1.50)
    assert mapping.last_time == 1.02
    assert mapping.time_condition_fulfilled(2.03)
    assert mapping.last_time == 2.03

    # Change shall always report true regardless of value
    assert mapping.last_vss_value is None
    assert mapping.change_condition_fulfilled(23)
    assert mapping.last_vss_value == 23
    assert mapping.change_condition_fulfilled(23)
    assert mapping.change_condition_fulfilled(24)
    assert mapping.last_vss_value == 24

    assert mapping.transform_value(23.2) == 23.2


def test_no_transform_interval_500():
    mapping = mapper.get_vss_mapping("S1", "A.NoTransformInterval500")
    assert mapping is not None
    assert mapping.interval_ms == 500
    assert mapping.on_change == False
    # First shall always be sent
    assert mapping.time_condition_fulfilled(0.01)
    assert not mapping.time_condition_fulfilled(0.02)
    assert not mapping.time_condition_fulfilled(0.50)
    assert mapping.time_condition_fulfilled(0.52)
    assert not mapping.time_condition_fulfilled(1.00)
    assert mapping.time_condition_fulfilled(1.03)

    # Change shall always report true regardless of value
    assert mapping.change_condition_fulfilled(23)
    assert mapping.change_condition_fulfilled(23)

    assert mapping.transform_value(23.2) == 23.2


def test_no_transform_on_change_true():
    mapping = mapper.get_vss_mapping("S1", "A.NoTransformOnChangeTrue")
    assert mapping is not None
    assert mapping.interval_ms == 0
    assert mapping.on_change
    # First plus always
    assert mapping.time_condition_fulfilled(0.01)
    assert mapping.time_condition_fulfilled(45.0)
    assert mapping.time_condition_fulfilled(45.0)
    assert mapping.time_condition_fulfilled(48.0)
    assert mapping.time_condition_fulfilled(49.0)

    # First plus on change
    assert mapping.change_condition_fulfilled(23)
    assert not mapping.change_condition_fulfilled(23)
    assert mapping.change_condition_fulfilled(46)
    assert not mapping.change_condition_fulfilled(46)

    assert mapping.transform_value(23.2) == 23.2


def test_no_transform_on_change_false():
    # Should be same as test_no_transform_default
    mapping = mapper.get_vss_mapping("S1", "A.NoTransformOnChangeFalse")
    assert mapping is not None
    assert mapping.interval_ms == 1000
    assert mapping.on_change == False

    # First shall always be sent
    assert mapping.time_condition_fulfilled(0.01)
    assert not mapping.time_condition_fulfilled(0.02)
    assert not mapping.time_condition_fulfilled(1.00)
    assert mapping.time_condition_fulfilled(1.02)
    assert not mapping.time_condition_fulfilled(1.50)
    assert mapping.time_condition_fulfilled(2.03)

    # Change shall always report true regardless of value
    assert mapping.change_condition_fulfilled(23)
    assert mapping.change_condition_fulfilled(23)

    assert mapping.transform_value(23.2) == 23.2


def test_no_transform_on_change_interval_500():
    mapping = mapper.get_vss_mapping("S1", "A.NoTransformOnChangeInterval500")
    assert mapping is not None
    assert mapping.interval_ms == 500
    assert mapping.on_change
    # First shall always be sent
    assert mapping.time_condition_fulfilled(0.01)
    assert not mapping.time_condition_fulfilled(0.02)
    assert not mapping.time_condition_fulfilled(0.50)
    assert mapping.time_condition_fulfilled(0.52)
    assert not mapping.time_condition_fulfilled(1.00)
    assert mapping.time_condition_fulfilled(1.03)

    assert mapping.change_condition_fulfilled(23)
    assert not mapping.change_condition_fulfilled(23)
    assert mapping.change_condition_fulfilled(46)
    assert not mapping.change_condition_fulfilled(46)

    assert mapping.transform_value(23.2) == 23.2


def test_no_transform_always():
    mapping = mapper.get_vss_mapping("S1", "A.NoTransformAlways")
    assert mapping is not None
    assert mapping.interval_ms == 0
    assert mapping.on_change == False
    # First shall always be sent
    assert mapping.time_condition_fulfilled(0.01)
    assert mapping.time_condition_fulfilled(0.02)
    assert mapping.time_condition_fulfilled(0.50)
    assert mapping.time_condition_fulfilled(0.52)
    assert mapping.time_condition_fulfilled(1.00)
    assert mapping.time_condition_fulfilled(1.03)

    assert mapping.change_condition_fulfilled(23)
    assert mapping.change_condition_fulfilled(23)
    assert mapping.change_condition_fulfilled(46)
    assert mapping.change_condition_fulfilled(46)

    assert mapping.transform_value(23.2) == 23.2


def test_mapping_math():
    mapping = mapper.get_vss_mapping("S2", "A.Math")
    assert mapping is not None
    assert mapping.transform_value(26) == 5
    assert mapping.transform_value(-26) == 5

    # Error handling - value not supported
    assert mapping.transform_value("Sebastian") is None


def test_mapping_string_int():
    mapping = mapper.get_vss_mapping("S3", "A.MappingStringInt")
    assert mapping is not None
    
    assert mapping.transform_value("DI_GEAR_P") == 0
    assert mapping.transform_value("DI_GEAR_INVALID") == 0
    assert mapping.transform_value("DI_GEAR_R") == -1

    # Error handling - value not supported
    assert mapping.transform_value("Sebastian") is None


def test_mapping_string_string():
    mapping = mapper.get_vss_mapping("S4", "A.MappingStringString")
    assert mapping is not None
    assert mapping.interval_ms == 0
    assert mapping.on_change

    assert mapping.transform_value("schwarz") == "black"
    assert mapping.transform_value("weiss") == "white"

    # Error handling - value not supported
    assert mapping.transform_value("blau") is None


def test_mapping_int_int():
    mapping = mapper.get_vss_mapping("S5", "A.MappingIntInt")
    assert mapping is not None

    assert mapping.transform_value(3) == 7
    assert mapping.transform_value(4) == 4

    # Error handling - value not supported
    assert mapping.transform_value(6) is None

    assert mapping.transform_value(4) == 4


def test_mapping_int_duplicate():
    mapping = mapper.get_vss_mapping("S5", "A.MappingIntIntDuplicate")
    assert mapping is not None
    # For duplicated mappings we do not state which one that will be used,
    # both are OK
    assert (
        mapping.transform_value(3) == 7) or (
        mapping.transform_value(3) == 8)
    assert mapping.transform_value(4) == 4

    # Error handling - value not supported
    assert mapping.transform_value(6) is None


def test_mapping_int_int():
    mapping = mapper.get_vss_mapping("S6", "A.IsMappingBool")
    assert mapping is not None

    # Assuming that Yaml 1.1 syntax is used, i.e. yes is treated as True
    # Note that in JSON true/false is used
    assert mapping.transform_value(1)
    assert mapping.transform_value(2)
    assert not mapping.transform_value(3)
    assert mapping.transform_value(4)
