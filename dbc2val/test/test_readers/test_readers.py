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
from dbcfeederlib.dbcreader import DBCReader
from dbcfeederlib.j1939reader import J1939Reader

test_path = os.path.dirname(os.path.abspath(__file__))


def _assert_signal_mappings(signal_mappings: Dict[str, VSSObservation]):
    assert signal_mappings["Signal_One"].vss_name == "A.One"
    assert signal_mappings["Signal_One"].raw_value == 0x10
    assert signal_mappings["Signal_Two"].vss_name == "A.Two"
    assert signal_mappings["Signal_Two"].raw_value == 0x5432


@pytest.fixture
def dbc2vss_queue() -> Queue:
    return Queue(10)


@pytest.fixture
def j1939reader(dbc2vss_queue: Queue) -> J1939Reader:
    mapper = Mapper(
        mapping_definitions_file=test_path + "/simple_mapping.json",
        dbc_file_names=[test_path + "/j1939.kcd"],
        expect_extended_frame_ids=True,
        use_strict_parsing=True)
    return J1939Reader(dbc2vss_queue, mapper)


@pytest.fixture
def dbcreader(dbc2vss_queue: Queue) -> DBCReader:
    mapper = Mapper(
        mapping_definitions_file=test_path + "/simple_mapping.json",
        dbc_file_names=[test_path + "/standard_can.kcd"],
        expect_extended_frame_ids=False,
        use_strict_parsing=True)
    return DBCReader(dbc2vss_queue, mapper)


def test_j1939reader_processes_j1939_message(j1939reader: J1939Reader, dbc2vss_queue: Queue):

    # GIVEN a reader based on CAN message and mapping definitions

    # WHEN a message is received from the CAN bus for which a mapping gas been defined
    j1939reader.on_message(priority=1, pgn=0x1FFFF, sa=0x45, timestamp=0, data=[0x10, 0x32, 0x54])

    # THEN the reader determines both VSS Data Entries that the CAN signals are mapped to
    signal_mappings: Dict[str, VSSObservation] = {}
    obs: VSSObservation = dbc2vss_queue.get(block=False)
    signal_mappings[obs.dbc_name] = obs
    obs = dbc2vss_queue.get(block=False)
    signal_mappings[obs.dbc_name] = obs

    _assert_signal_mappings(signal_mappings)


def test_j1939reader_ignores_unknown_CAN_messages(j1939reader: J1939Reader, dbc2vss_queue: Queue):

    # GIVEN a reader based on CAN message and mapping definitions

    # WHEN a  message with an unknown PGN is received from the CAN bus
    j1939reader.on_message(priority=1, pgn=0x1FFFA, sa=0x12, timestamp=0, data=[0x10, 0x32, 0x54])

    # THEN the reader ignores the message
    with pytest.raises(Empty):
        dbc2vss_queue.get(block=False)


def test_dbcreader_processes_can_message(dbcreader: DBCReader, dbc2vss_queue: Queue):

    # GIVEN a reader based on CAN message and mapping definitions

    # WHEN a message is received from the CAN bus for which a mapping has been defined
    dbcreader._process_message(frame_id=0x111A, data=bytearray([0x10, 0x32, 0x54]))

    # THEN the reader determines both VSS Data Entries that the CAN signals are mapped to
    signal_mappings: Dict[str, VSSObservation] = {}
    obs: VSSObservation = dbc2vss_queue.get(block=False)
    signal_mappings[obs.dbc_name] = obs
    obs = dbc2vss_queue.get(block=False)
    signal_mappings[obs.dbc_name] = obs

    _assert_signal_mappings(signal_mappings)


def test_dbcreader_ignores_unknown_CAN_messages(dbcreader: DBCReader, dbc2vss_queue: Queue):

    # GIVEN a reader based on CAN message and mapping definitions

    # WHEN a message with an unknown frame ID is received from the CAN bus
    dbcreader._process_message(frame_id=0x10AC, data=bytearray([0x10, 0x32, 0x54]))

    # THEN the reader ignores the message
    with pytest.raises(Empty):
        dbc2vss_queue.get(block=False)
