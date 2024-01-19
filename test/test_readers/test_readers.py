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

import unittest.mock as mock

from queue import Queue
from typing import Dict, List

import pytest  # type: ignore # noqa: F401

from cantools.database import Message, Signal
from dbcfeederlib.canreader import CanReader
from dbcfeederlib.dbc2vssmapper import Mapper, VSSObservation, VSSMapping
from dbcfeederlib.j1939reader import J1939Reader


class TestCanReader():

    class NoopCanReader(CanReader):
        def __init__(self, rxqueue: Queue, mapper: Mapper):
            super().__init__(rxqueue, mapper, "vcan0")

        def _start_can_bus_listener(self):
            pass

        def _stop_can_bus_listener(self):
            pass

    def test_process_can_message_handles_known_messages(self) -> None:

        # GIVEN a reader based on CAN message and mapping definitions
        decoded_message = {"UnboundedSignal": 10}
        message_def = Message(
            frame_id=0x0102,
            name="MyMessage",
            length=8,
            signals=[
                Signal(name="UnboundedSignal", start=0, length=8),
            ])
        message_def.decode = mock.Mock(return_value=decoded_message)  # type: ignore
        mapper = mock.create_autospec(spec=Mapper)
        mapper.get_message_by_frame_id.return_value = message_def
        mapper.get_dbc2vss_mappings.return_value = [VSSMapping(
            vss_name="Vehicle.Custom",
            dbc_name="UnboundedSignal",
            transform={},
            interval_ms=0,
            on_change=True,
            datatype="uint8",
            description="some custom signal")]
        queue = mock.create_autospec(spec=Queue)
        reader = TestCanReader.NoopCanReader(queue, mapper)

        # WHEN a message with a known frame ID is received
        reader._process_can_message(0x0102, bytes())

        # THEN its signals are mapped to VSS data entries
        mapper.get_dbc2vss_mappings.assert_called_once_with("UnboundedSignal")
        queue.put.assert_called_once()
        assert queue.put.call_args.args[0].dbc_name == "UnboundedSignal"
        assert queue.put.call_args.args[0].vss_name == "Vehicle.Custom"

    def test_process_can_message_ignores_out_of_range_values(self) -> None:

        # GIVEN a reader based on a CAN message definition that defines signals
        # with min and max values
        decoded_message = {"HasMinSignal": 3, "HasMaxSignal": 255}
        message_def = Message(
            frame_id=0x103,
            name="MyMessage",
            length=16,
            signals=[
                Signal(name="HasMinSignal", start=0, length=8, minimum=5),
                Signal(name="HasMaxSignal", start=8, length=8, maximum=254),
            ])
        message_def.decode = mock.Mock(return_value=decoded_message)  # type: ignore
        mapper = mock.create_autospec(spec=Mapper)
        mapper.get_message_by_frame_id.return_value = message_def
        queue = mock.create_autospec(spec=Queue)
        reader = TestCanReader.NoopCanReader(queue, mapper)

        # WHEN a  message is received from the CAN bus which only contains signals
        # with values out of range
        reader._process_can_message(0x103, bytes())

        # THEN the reader ignores the signal values
        mapper.get_message_by_frame_id.assert_called_once_with(0x0103)
        mapper.get_dbc2vss_mappings.assert_not_called()
        queue.put.assert_not_called()

    def test_process_can_message_ignores_unknown_messages(self) -> None:
        # GIVEN a reader based on an empty mapping definitions database
        queue = mock.create_autospec(spec=Queue)
        mapper = mock.create_autospec(spec=Mapper)
        mapper.get_message_by_frame_id.return_value = None
        reader = TestCanReader.NoopCanReader(queue, mapper)

        # WHEN a  message with an unknown PGN is received from the CAN bus
        reader._process_can_message(0x0102, bytes())

        # THEN the reader ignores the message
        mapper.get_message_by_frame_id.assert_called_once_with(0x0102)
        queue.put.assert_not_called()


def get_dbc2vss_mappings(signal_name: str) -> List[VSSMapping]:
    if signal_name == "Signal_One":
        return [VSSMapping(
                vss_name="A.One",
                dbc_name=signal_name,
                transform={},
                interval_ms=0,
                on_change=True,
                datatype="uint8",
                description="some custom signal")]
    elif signal_name == "Signal_Two":
        return [VSSMapping(
                vss_name="A.Two",
                dbc_name=signal_name,
                transform={},
                interval_ms=0,
                on_change=True,
                datatype="int16",
                description="some custom signal")]
    else:
        return []


def get_message_definition(frame_id: int, is_extended_frame: bool) -> Message:
    decoded_message = {"Signal_One": 0x10, "Signal_Two": 0x5432}
    msg_def = Message(
        frame_id=frame_id,
        name="Test_Message",
        length=24,
        is_extended_frame=is_extended_frame,
        signals=[
            Signal(name="Signal_One", start=0, length=8, maximum=213),
            Signal(name="Signal_Two", start=8, length=16, is_signed=True),
        ])
    msg_def.decode = mock.Mock(return_value=decoded_message)  # type: ignore
    return msg_def


def assert_signal_mappings(signal_mappings: Dict[str, VSSObservation]) -> None:
    assert signal_mappings["Signal_One"].vss_name == "A.One"
    assert signal_mappings["Signal_One"].raw_value == 0x10
    assert signal_mappings["Signal_Two"].vss_name == "A.Two"
    assert signal_mappings["Signal_Two"].raw_value == 0x5432


class TestJ1939Reader():

    def test_j1939reader_processes_j1939_message(self) -> None:

        # GIVEN a reader based on CAN message and mapping definitions
        queue = mock.create_autospec(spec=Queue)
        message_def = get_message_definition(0x01FFFF10, True)
        mapper = mock.create_autospec(spec=Mapper)
        mapper.get_message_by_frame_id.return_value = message_def
        mapper.get_dbc2vss_mappings.side_effect = get_dbc2vss_mappings
        j1939reader = J1939Reader(queue, mapper, "vcan0")

        # WHEN a message is received from the CAN bus for which a mapping gas been defined
        j1939reader._on_message(priority=1, pgn=0x1FFFF, source_address=0x45, timestamp=0, data=[0x10, 0x32, 0x54])

        # THEN the reader determines both VSS Data Entries that the CAN signals are mapped to
        assert queue.put.call_count == 2
        signal_mappings = {}
        for obs in queue.put.call_args_list:
            signal_mappings[obs.args[0].dbc_name] = obs.args[0]

        assert_signal_mappings(signal_mappings)


class TestDBCReader():

    def test_dbcreader_processes_can_message(self) -> None:

        # GIVEN a reader based on CAN message and mapping definitions
        queue = mock.create_autospec(spec=Queue)
        message_def = get_message_definition(0x011A, False)
        mapper = mock.create_autospec(spec=Mapper)
        mapper.get_message_by_frame_id.return_value = message_def
        mapper.get_dbc2vss_mappings.side_effect = get_dbc2vss_mappings
        dbcreader = J1939Reader(queue, mapper, "vcan0")

        # WHEN a message is received from the CAN bus for which a mapping has been defined
        dbcreader._process_can_message(frame_id=0x111A, data=bytearray([0x10, 0x32, 0x54]))

        # THEN the reader determines both VSS Data Entries that the CAN signals are mapped to
        assert queue.put.call_count == 2
        signal_mappings = {}
        for obs in queue.put.call_args_list:
            signal_mappings[obs.args[0].dbc_name] = obs.args[0]

        assert_signal_mappings(signal_mappings)
