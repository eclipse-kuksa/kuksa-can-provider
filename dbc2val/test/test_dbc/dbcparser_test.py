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

from dbcfeederlib import dbcparser
import os

NON_EXISTING_CAN_FRAME_ID: int = 0x45

# read config only once
test_path = os.path.dirname(os.path.abspath(__file__))
def_dbc = test_path + "/../../Model3CAN.dbc"


def test_default_dbc():
    """
    Verify that the parser can read message definitions from a standard .dbc file.
    """
    parser = dbcparser.DBCParser([def_dbc])
    assert parser.get_canid_for_signal('SteeringAngle129') == 297
    assert parser.get_canid_for_signal('DI_uiSpeed') == 599

    signals = parser.get_signals_for_canid(599)
    assert "DI_speedChecksum" in signals
    assert "DI_speedCounter" in signals
    assert "DI_uiSpeed" in signals
    assert "DI_uiSpeedHighSpeed" in signals
    assert "DI_uiSpeedUnits" in signals
    assert "DI_vehicleSpeed" in signals


def test_split_dbc():
    """
    Verify that the parser can read message definitions from multiple standard .dbc files.
    """
    parser = dbcparser.DBCParser([test_path + "/test1_1.dbc", test_path + "/test1_2.dbc"])
    # signal from message defined in first file
    assert parser.get_canid_for_signal('SteeringAngle129') == 297
    # signal from message defined in second file
    assert parser.get_canid_for_signal('DI_uiSpeed') == 599


def test_duplicated_dbc():
    """
    Verify that the parser can read message definitions from a standard .dbc file
    specified several times.
    """
    parser = dbcparser.DBCParser([def_dbc, def_dbc])
    assert parser.get_canid_for_signal('SteeringAngle129') == 297
    assert parser.get_canid_for_signal('DI_uiSpeed') == 599


def test_single_kcd():
    """
    Verify that the parser can read message definitions from a single .kcd file.
    """
    parser = dbcparser.DBCParser([test_path + "/test1_1.kcd"])
    assert parser.get_canid_for_signal('DI_bmsRequestInterfaceVersion') == 0x16

    signals = parser.get_signals_for_canid(0x16)
    assert "DI_bmsOpenContactorsRequest" in signals
    assert "DI_bmsRequestInterfaceVersion" in signals


def test_split_kcd():
    """
    Verify that the parser can read message definitions from multiple .kcd files.
    """
    parser = dbcparser.DBCParser([test_path + "/test1_1.kcd", test_path + "/test1_2.kcd"])
    # signal from message defined in first file
    assert parser.get_canid_for_signal('DI_bmsRequestInterfaceVersion') == 0x16
    # signal from message defined in second file
    assert parser.get_canid_for_signal('SteeringAngle129') == 0x129


def test_mixed_file_types():
    """
    Verify that the parser can read message definitions from multiple .kcd and
    standard .dbc files.
    """
    parser = dbcparser.DBCParser([test_path + "/test1_1.kcd", test_path + "/test1_2.dbc"])
    # signal from message defined in first file
    assert parser.get_canid_for_signal('DI_bmsRequestInterfaceVersion') == 0x16
    # signal from message defined in second file
    assert parser.get_canid_for_signal('SteeringAngle129') == 0x129


def test_get_message_for_for_non_existing_frame_id_returns_none():
    parser = dbcparser.DBCParser([test_path + "/test1_1.kcd"])
    assert parser.get_message_for_canid(NON_EXISTING_CAN_FRAME_ID) is None


def test_get_signals_for_non_existing_frame_id_returns_empty_list():
    parser = dbcparser.DBCParser([test_path + "/test1_1.kcd"])
    assert len(parser.get_signals_for_canid(NON_EXISTING_CAN_FRAME_ID)) == 0


def test_get_canid_for_unused_signal_name_returns_none():
    parser = dbcparser.DBCParser([test_path + "/test1_1.kcd"])
    assert parser.get_canid_for_signal("unused_signal") is None
