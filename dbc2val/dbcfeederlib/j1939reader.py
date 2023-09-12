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
import time

import j1939  # type: ignore[import]
from dbcfeederlib import dbc2vssmapper
from queue import Queue

log = logging.getLogger(__name__)


class J1939Reader:

    def __init__(self, rxqueue: Queue, mapper: dbc2vssmapper.Mapper):
        self._queue = rxqueue
        self._mapper = mapper
        self._ecu = j1939.ElectronicControlUnit()

    def stop(self):
        self._ecu.disconnect()

    def start_listening(self, *args, **kwargs):
        """Start listening to CAN bus

        Arguments are passed directly to :class:`can.BusABC`. Typically these
        may include:

        :param channel:
            Backend specific channel for the CAN interface.
        :param str bustype:
            Name of the interface. See
            `python-can manual <https://python-can.readthedocs.io/en/latest/configuration.html#interface-names>`__
            for full list of supported interfaces.
        :param int bitrate:
            Bitrate in bit/s.
        """

        # Connect to the CAN bus
        self._ecu.connect(*args, **kwargs)
        self._ecu.subscribe(self.on_message)

    def on_message(self, priority: int, pgn: int, sa: int, timestamp: int, data):
        # create an extended CAN frame ID from PGN and source address
        extended_can_id: int = pgn << 8 | sa
        message = self._mapper.get_message_for_canid(extended_can_id)
        if message is not None:
            log.debug("processing j1939 message [PGN: %#x]", pgn)
            try:
                decode = message.decode(bytes(data), allow_truncated=True)
                if log.isEnabledFor(logging.DEBUG):
                    log.debug("Decoded message: %s", str(decode))

                rx_time = time.time()
                for k, v in decode.items():  # type: ignore
                    vss_mappings = self._mapper.get_dbc2vss_mappings(k)
                    # Now time is defined per VSS signal, so handling needs to be different
                    for signal in vss_mappings:
                        if signal.time_condition_fulfilled(rx_time):
                            log.debug("Queueing %s, triggered by %s, raw value %s", signal.vss_name, k, v)
                            self._queue.put(dbc2vssmapper.VSSObservation(k, signal.vss_name, v, rx_time))
                        else:
                            log.debug("Ignoring %s, triggered by %s, raw value %s", signal.vss_name, k, v)
            except Exception:
                log.warning("Error decoding message %s [PGN: %#x]", message.name, pgn, exc_info=True)
