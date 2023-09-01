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

import os

from dbcfeederlib import dbcparser

# read config only once
test_path = os.path.dirname(os.path.abspath(__file__))
def_dbc = test_path + "/../../Model3CAN.dbc"


def test_default_dbc():

    parser3 = dbcparser.DBCParser([def_dbc])
    assert parser3.get_canid_for_signal('SteeringAngle129') == 297
    assert parser3.get_canid_for_signal('DI_uiSpeed') == 599


def test_splitted_dbc():
    """
    This verifies that we can read a splitted DBC File.
    Difference compared to default is that 'SteeringAngle129' has been moved to test1_2.dbc
    """
    parser3 = dbcparser.DBCParser([test_path + "/test1_1.dbc", test_path + "/test1_2.dbc"])
    assert parser3.get_canid_for_signal('SteeringAngle129') == 297
    assert parser3.get_canid_for_signal('DI_uiSpeed') == 599


def test_duplicated_dbc():
    """
    Load original DBC multiple times
    """
    parser3 = dbcparser.DBCParser([def_dbc, def_dbc])
    assert parser3.get_canid_for_signal('SteeringAngle129') == 297
    assert parser3.get_canid_for_signal('DI_uiSpeed') == 599
