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

from dbcfeederlib import dbcparser
import os

# read config only once
test_path = os.path.dirname(os.path.abspath(__file__))


def test_single_kcd():

    parser = dbcparser.DBCParser([test_path + "/test1_1.kcd"])
    assert parser.get_canid_for_signal('DI_bmsRequestInterfaceVersion') == 0x16


def test_split_kcd():
    """
    This verifies that we can read multiple KCD files.
    """
    parser = dbcparser.DBCParser([test_path + "/test1_1.kcd", test_path + "/test1_2.kcd"])
    assert parser.get_canid_for_signal('DI_bmsRequestInterfaceVersion') == 0x16
    assert parser.get_canid_for_signal('SteeringAngle129') == 0x129


def test_mixed_file_types():
    """
    This verifies that we can read files of different type.
    """
    parser = dbcparser.DBCParser([test_path + "/test1_1.kcd", test_path + "/test1_2.dbc"])
    assert parser.get_canid_for_signal('DI_bmsRequestInterfaceVersion') == 0x16
    assert parser.get_canid_for_signal('SteeringAngle129') == 0x129


def test_duplicated_dbc():
    """
    Load original KCD multiple times
    """
    parser = dbcparser.DBCParser([test_path + "/test1_1.kcd", test_path + "/test1_1.kcd"])
    assert parser.get_canid_for_signal('DI_bmsRequestInterfaceVersion') == 0x16
