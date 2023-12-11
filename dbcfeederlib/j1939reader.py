#!/usr/bin/python3

########################################################################
# Copyright (c) 2020,2023 Contributors to the Eclipse Foundation
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

# This script is to read CAN messages based on PGN - SAE J1939
# Prior to using this script, can-j1939 and
# the relevant wheel-package should be installed first:
# $ pip3 install can-j1939

import logging

from queue import Queue
from typing import Optional

import j1939  # type: ignore[import]

from dbcfeederlib import canreader
from dbcfeederlib import dbc2vssmapper

log = logging.getLogger(__name__)


class J1939Reader(canreader.CanReader):

    def __init__(self, rxqueue: Queue, mapper: dbc2vssmapper.Mapper, can_port: str, dump_file: Optional[str] = None):
        super().__init__(rxqueue, mapper, can_port, dump_file)

        self._ecu = j1939.ElectronicControlUnit()
        self._ecu.subscribe(self._on_message)

    def _on_message(self, priority: int, pgn: int, source_address: int, timestamp: int, data):
        # create an extended CAN frame ID from PGN and source address
        extended_frame_id: int = pgn << 8 | source_address
        log.debug("Processing j1939 message [frame_id: %d, PGN %#x]", extended_frame_id, pgn)
        self._process_can_message(extended_frame_id, data)

    def _start_can_bus_listener(self):
        self._ecu.connect(**self._can_kwargs)

    def _stop_can_bus_listener(self):
        self._ecu.disconnect()
