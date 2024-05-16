#!/usr/bin/python3

########################################################################
# Copyright (c) 2023 Contributors to the Eclipse Foundation
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

import os
import logging

import pytest  # type: ignore

from dbcfeederlib import dbc2vssmapper

test_path = os.path.dirname(os.path.abspath(__file__))


def test_unknown_transform(caplog: pytest.LogCaptureFixture):

    mapping_path = test_path + "/test_unknown_transform.json"
    dbc_file_names = [test_path + "/../../Model3CAN.dbc"]

    with pytest.raises(SystemExit) as excinfo:
        dbc2vssmapper.Mapper(mapping_path, dbc_file_names)
    assert excinfo.value.code == -1
    error_msg = ("dbcfeederlib.dbc2vssmapper", logging.ERROR, "Unsupported transformation definition for A.B")
    assert error_msg in caplog.record_tuples


def test_vss2dbc_sensor(caplog: pytest.LogCaptureFixture):

    mapping_path = test_path + "/mapping_vss2dbc_not_actuator.json"
    dbc_file_names = [test_path + "/../../Model3CAN.dbc"]

    with pytest.raises(SystemExit) as excinfo:
        dbc2vssmapper.Mapper(mapping_path, dbc_file_names)
    assert excinfo.value.code == -1
    error_msg = ("dbcfeederlib.dbc2vssmapper", logging.ERROR,
                 "vss2dbc only allowed for actuators, VSS signal A.B is not an actuator!")
    assert error_msg in caplog.record_tuples


def test_mapper_fails_for_duplicate_signal_definition():

    mapping_path = test_path + "/mapping_for_ambiguous_signal.json"
    dbc_file_names = [test_path + "/../test_dbc/duplicate_signal_name.kcd"]

    with pytest.raises(SystemExit) as excinfo:
        dbc2vssmapper.Mapper(mapping_path, dbc_file_names, fail_on_duplicate_signal_definitions=True)
    assert excinfo.value.code == -1


def test_mapper_ignores_unused_duplicate_signal_definition():

    mapping_path = test_path + "/mapping_for_unused_ambiguous_signal.json"
    dbc_file_names = [test_path + "/../test_dbc/duplicate_signal_name.kcd"]

    mapper = dbc2vssmapper.Mapper(mapping_path, dbc_file_names, fail_on_duplicate_signal_definitions=True)
    affected_signal_names = mapper.handle_update("A.B", 15)
    assert len(affected_signal_names) == 1
    assert "SignalTwo" in affected_signal_names
