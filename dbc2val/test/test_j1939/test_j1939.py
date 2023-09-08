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

from queue import Empty, Queue
from typing import Dict

import pytest  # type: ignore

from dbcfeederlib.dbc2vssmapper import Mapper, VSSObservation
from dbcfeederlib.dbcparser import DBCParser
from dbcfeederlib.j1939reader import J1939Reader

test_path = os.path.dirname(os.path.abspath(__file__))


def test_on_message_processes_j1939_message():

    # GIVEN a reader based on CAN message and mapping definitions
    dbc2val_queue = Queue(10)
    parser = DBCParser([test_path + "/j1939.kcd"], expect_extended_frame_ids=True)
    mapper = Mapper(test_path + "/simple_mapping.json", parser, "")
    reader = J1939Reader(rxqueue=dbc2val_queue, mapper=mapper, dbc_parser=parser)

    # WHEN a message is received from the CAN bus for which a mapping gas been defined
    reader.on_message(priority=1, pgn=0x1FFFF, sa=0x45, timestamp=0, data=[0x10, 0x32, 0x54])

    # THEN the reader determines both VSS Data Entries that the CAN signals are mapped to
    signal_mappings: Dict[str, VSSObservation] = {}
    obs: VSSObservation = dbc2val_queue.get(block=False)
    signal_mappings[obs.dbc_name] = obs
    obs = dbc2val_queue.get(block=False)
    signal_mappings[obs.dbc_name] = obs

    assert signal_mappings["Signal_One"].vss_name == "A.One"
    assert signal_mappings["Signal_One"].raw_value == 0x10
    assert signal_mappings["Signal_Two"].vss_name == "A.Two"
    assert signal_mappings["Signal_Two"].raw_value == 0x5432


def test_on_message_ignores_unknown_CAN_messages():

    # GIVEN a reader based on CAN message and mapping definitions
    dbc2val_queue = Queue(10)
    parser = DBCParser([test_path + "/j1939.kcd"], expect_extended_frame_ids=True)
    mapper = Mapper(test_path + "/simple_mapping.json", parser, "")
    reader = J1939Reader(rxqueue=dbc2val_queue, mapper=mapper, dbc_parser=parser)

    # WHEN a  message with an unknown PGN is received from the CAN bus
    reader.on_message(priority=1, pgn=0x1FFFA, sa=0x12, timestamp=0, data=[0x10, 0x32, 0x54])

    # THEN the reader ignores the message
    with pytest.raises(Empty):
        dbc2val_queue.get(block=False)
