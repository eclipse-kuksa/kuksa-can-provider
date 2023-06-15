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

from dbcfeederlib import dbc2vssmapper
from dbcfeederlib import dbcparser
import os
import pytest
import logging


def test_unknown_transform(caplog, capsys):

    test_path = os.path.dirname(os.path.abspath(__file__))
    mapping_path = test_path + "/test_unknown_transform.json"
    parser = dbcparser.DBCParser(test_path + "/../../Model3CAN.dbc")

    with pytest.raises(SystemExit) as excinfo:
        dbc2vssmapper.Mapper(mapping_path, parser)
    out, err = capsys.readouterr()
    assert excinfo.value.code == -1
    assert caplog.record_tuples == [("dbcfeederlib.dbc2vssmapper", logging.ERROR, "Unsupported transform for A.B")]
