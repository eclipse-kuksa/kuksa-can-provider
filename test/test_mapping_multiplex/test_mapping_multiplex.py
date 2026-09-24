#!/usr/bin/python3

########################################################################
# Copyright (c) 2024 Contributors to the Eclipse Foundation
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

# Tests for the multiplexer support added to dbc2vssmapper.py and canreader.py

import logging
import os
import unittest.mock as mock

from queue import Queue

import pytest  # type: ignore

from dbcfeederlib import dbc2vssmapper
from dbcfeederlib.canreader import CanReader
from dbcfeederlib.dbc2vssmapper import Mapper, VSSMapping, VSSMultiplexer

test_path = os.path.dirname(os.path.abspath(__file__))
dbc_file_names = [test_path + "/test_mux.dbc"]


# ---------------------------------------------------------------------------
# dbc2vssmapper.py: parsing of the "multiplexer" mapping definition
# ---------------------------------------------------------------------------

def test_multiplexer_is_parsed_for_mapping():
    mapping_path = test_path + "/mapping_multiplex.json"
    mapper = Mapper(mapping_path, dbc_file_names)

    mapping = mapper.get_dbc2vss_mapping("AlwaysPresent", "A.AlwaysPresentModeA")
    assert mapping is not None
    assert mapping.multiplexer is not None
    assert mapping.multiplexer.size() == 1
    assert mapping.multiplexer.get_signal(0) == "MuxSelector"
    assert mapping.multiplexer.get_value(0) == 0


def test_multiplexer_is_none_when_not_configured():
    mapping_path = test_path + "/mapping_multiplex.json"
    mapper = Mapper(mapping_path, dbc_file_names)

    mapping = mapper.get_dbc2vss_mapping("AlwaysPresent", "A.NoMultiplexer")
    assert mapping is not None
    assert mapping.multiplexer is None


def test_multiplexer_allows_multiple_mappings_for_same_signal():
    mapping_path = test_path + "/mapping_multiplex.json"
    mapper = Mapper(mapping_path, dbc_file_names)

    # "AlwaysPresent" is mapped twice, once per MuxSelector value
    mappings = mapper.get_dbc2vss_mappings("AlwaysPresent")
    vss_names = {m.vss_name: m for m in mappings}
    assert vss_names["A.AlwaysPresentModeA"].multiplexer.get_value(0) == 0
    assert vss_names["A.AlwaysPresentModeB"].multiplexer.get_value(0) == 1


def test_multiplexer_signal_and_data_signal_must_share_can_frame(caplog: pytest.LogCaptureFixture):
    mapping_path = test_path + "/mapping_multiplex_mismatch.json"

    with pytest.raises(SystemExit) as excinfo:
        Mapper(mapping_path, dbc_file_names)
    assert excinfo.value.code == -1
    error_msg = (
        "dbcfeederlib.dbc2vssmapper", logging.ERROR,
        "CAN signal name OtherSignal and multiplexer signal name MuxSelector "
        "does no apply to the same CAN frames"
    )
    assert error_msg in caplog.record_tuples


def test_multiplexer_fails_when_signal_is_missing(caplog: pytest.LogCaptureFixture):
    mapping_path = test_path + "/mapping_multiplex_no_signal.json"

    with pytest.raises(SystemExit) as excinfo:
        Mapper(mapping_path, dbc_file_names)
    assert excinfo.value.code == -1
    error_msg = (
        "dbcfeederlib.dbc2vssmapper", logging.ERROR,
        "No signal provided in multiplexer for AlwaysPresent"
    )
    assert error_msg in caplog.record_tuples


def test_multiplexer_fails_when_signal_is_not_valid(caplog: pytest.LogCaptureFixture):
    mapping_path = test_path + "/mapping_multiplex_invalid_signal.json"

    with pytest.raises(SystemExit) as excinfo:
        Mapper(mapping_path, dbc_file_names)
    assert excinfo.value.code == -1
    error_msg = (
        "dbcfeederlib.dbc2vssmapper", logging.ERROR,
        "CAN signal name AlwaysPresent and multiplexer signal name NonExistentSignal "
        "does no apply to the same CAN frames"
    )
    assert error_msg in caplog.record_tuples


def test_multiplexer_fails_when_value_is_not_an_integer(caplog: pytest.LogCaptureFixture):
    mapping_path = test_path + "/mapping_multiplex_invalid_value.json"

    with pytest.raises(SystemExit) as excinfo:
        Mapper(mapping_path, dbc_file_names)
    assert excinfo.value.code == -1
    error_msg = (
        "dbcfeederlib.dbc2vssmapper", logging.ERROR,
        "Value for multiplexer in signal AlwaysPresent is not an integer"
    )
    assert error_msg in caplog.record_tuples


def test_multiplexer_fails_when_value_is_missing(caplog: pytest.LogCaptureFixture):
    mapping_path = test_path + "/mapping_multiplex_no_value.json"

    with pytest.raises(SystemExit) as excinfo:
        Mapper(mapping_path, dbc_file_names)
    assert excinfo.value.code == -1
    error_msg = (
        "dbcfeederlib.dbc2vssmapper", logging.ERROR,
        "No value provided in multiplexer for AlwaysPresent"
    )
    assert error_msg in caplog.record_tuples


# ---------------------------------------------------------------------------
# dbc2vssmapper.py: VSSMultiplexer class in isolation (full branch coverage)
# ---------------------------------------------------------------------------

def test_vss_multiplexer_append_and_size():
    multiplexer = VSSMultiplexer()
    assert multiplexer.size() == 0

    multiplexer.append("MuxSelector", 0)
    multiplexer.append("OtherSelector", 1)

    assert multiplexer.size() == 2
    assert multiplexer.get_signal(0) == "MuxSelector"
    assert multiplexer.get_value(0) == 0
    assert multiplexer.get_signal(1) == "OtherSelector"
    assert multiplexer.get_value(1) == 1


def test_vss_multiplexer_get_signal_out_of_range(caplog: pytest.LogCaptureFixture):
    multiplexer = VSSMultiplexer()
    multiplexer.append("MuxSelector", 0)

    assert multiplexer.get_signal(1) == ''
    error_msg = ("dbcfeederlib.dbc2vssmapper", logging.ERROR, "Access to multiplexer exceeds size")
    assert error_msg in caplog.record_tuples


def test_vss_multiplexer_get_value_out_of_range(caplog: pytest.LogCaptureFixture):
    multiplexer = VSSMultiplexer()
    multiplexer.append("MuxSelector", 0)

    assert multiplexer.get_value(1) == -1
    error_msg = ("dbcfeederlib.dbc2vssmapper", logging.ERROR, "Access to multiplexer exceeds size")
    assert error_msg in caplog.record_tuples


# ---------------------------------------------------------------------------
# canreader.py: filtering of decoded signals based on the multiplexer
# ---------------------------------------------------------------------------

class NoopCanReader(CanReader):
    """Minimal CanReader implementation usable for testing _handle_decoded_frame/_process_can_message."""

    def __init__(self, rxqueue: Queue, mapper: dbc2vssmapper.Mapper):
        super().__init__(rxqueue, mapper, "vcan0")

    def _start_can_bus_listener(self):
        pass

    def _stop_can_bus_listener(self):
        pass


def _mapping_for(vss_name: str, dbc_name: str, multiplexer_value: int) -> VSSMapping:
    multiplexer = VSSMultiplexer()
    multiplexer.append("MuxSelector", multiplexer_value)
    return VSSMapping(
        vss_name=vss_name,
        dbc_name=dbc_name,
        transform={},
        interval_ms=0,
        on_change=True,
        datatype="uint8",
        description="some signal",
        multiplexer=multiplexer)


def test_reader_queues_signal_matching_multiplexer_value():
    # GIVEN a mapping which is only valid when MuxSelector equals 0
    mapping = _mapping_for("A.AlwaysPresentModeA", "AlwaysPresent", 0)
    message_def = mock.Mock()
    message_def.get_signal_by_name.return_value = mock.Mock(minimum=None, maximum=None)
    message_def.decode.return_value = {"MuxSelector": 0, "AlwaysPresent": 42}

    mapper = mock.create_autospec(spec=dbc2vssmapper.Mapper)
    mapper.get_message_by_frame_id.return_value = message_def
    mapper.get_dbc2vss_mappings.side_effect = lambda name: [mapping] if name == "AlwaysPresent" else []
    queue = mock.create_autospec(spec=Queue)
    reader = NoopCanReader(queue, mapper)

    # WHEN a CAN message is received with a MuxSelector value that matches the mapping
    reader._process_can_message(0x100, bytes())

    # THEN the signal is queued
    queue.put.assert_called_once()
    assert queue.put.call_args.args[0].dbc_name == "AlwaysPresent"
    assert queue.put.call_args.args[0].vss_name == "A.AlwaysPresentModeA"


def test_reader_discards_signal_not_matching_multiplexer_value():
    # GIVEN a mapping which is only valid when MuxSelector equals 1
    mapping = _mapping_for("A.AlwaysPresentModeB", "AlwaysPresent", 1)
    message_def = mock.Mock()
    message_def.get_signal_by_name.return_value = mock.Mock(minimum=None, maximum=None)
    # but the received frame has MuxSelector == 0
    message_def.decode.return_value = {"MuxSelector": 0, "AlwaysPresent": 42}

    mapper = mock.create_autospec(spec=dbc2vssmapper.Mapper)
    mapper.get_message_by_frame_id.return_value = message_def
    mapper.get_dbc2vss_mappings.side_effect = lambda name: [mapping] if name == "AlwaysPresent" else []
    queue = mock.create_autospec(spec=Queue)
    reader = NoopCanReader(queue, mapper)

    # WHEN a CAN message is received with a MuxSelector value that does not match the mapping
    reader._process_can_message(0x100, bytes())

    # THEN the signal is not queued
    queue.put.assert_not_called()


def test_reader_queues_signal_without_multiplexer_regardless_of_selector():
    # GIVEN a mapping without a multiplexer condition
    mapping = VSSMapping(
        vss_name="A.NoMultiplexer",
        dbc_name="AlwaysPresent",
        transform={},
        interval_ms=0,
        on_change=True,
        datatype="uint8",
        description="some signal")
    message_def = mock.Mock()
    message_def.get_signal_by_name.return_value = mock.Mock(minimum=None, maximum=None)
    message_def.decode.return_value = {"MuxSelector": 1, "AlwaysPresent": 42}

    mapper = mock.create_autospec(spec=dbc2vssmapper.Mapper)
    mapper.get_message_by_frame_id.return_value = message_def
    mapper.get_dbc2vss_mappings.side_effect = lambda name: [mapping] if name == "AlwaysPresent" else []
    queue = mock.create_autospec(spec=Queue)
    reader = NoopCanReader(queue, mapper)

    # WHEN a CAN message is received
    reader._process_can_message(0x100, bytes())

    # THEN the signal is queued regardless of the MuxSelector value
    queue.put.assert_called_once()
