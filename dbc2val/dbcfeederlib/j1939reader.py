#!/usr/bin/python3

########################################################################
# Copyright (c) 2020,2023 Robert Bosch GmbH
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

import cantools
import j1939
from dbcfeederlib import dbc2vssmapper
from queue import Queue

log = logging.getLogger(__name__)


class J1939Reader:

    def __init__(self, rxqueue: Queue, dbcfile: str, mapper: str, use_strict_parsing: bool):
        self.queue = rxqueue
        self.db = cantools.database.load_file(dbcfile, strict = use_strict_parsing)
        self.mapper = mapper
        self.ecu = j1939.ElectronicControlUnit();

    def stop(self):
        self.ecu.disconnect()

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
        self.ecu.connect(*args, **kwargs)
        self.ecu.subscribe(self.on_message)

    def on_message(self, priority: int, pgn: int, sa: int, timestamp: int, data):
        message = self.identify_message(pgn)
        if message is not None:
            log.debug("processing j1939 message [PGN: %s]", pgn)
            try:
                decode = message.decode(bytes(data), allow_truncated=True)
                # log.debug("Decoded message: %s", str(decode))
                rxTime = time.time()
                for k, v in decode.items():
                    if k in self.mapper:
                        # Now time is defined per VSS signal, so handling needs to be different
                        for signal in self.mapper[k]:
                            if signal.time_condition_fulfilled(rxTime):
                                log.debug(f"Queueing {signal.vss_name}, triggered by {k}, raw value {v} ")
                                self.queue.put(dbc2vssmapper.VSSObservation(k, signal.vss_name, v, rxTime))
                            else:
                                log.debug(f"Ignoring {signal.vss_name}, triggered by {k}, raw value {v} ")
            except Exception:
                log.warning(
                    "Error decoding message [PGN: {}]".format(message.name),
                    exc_info=True,
                )

    def identify_message(self, pgn):
        pgn_hex = hex(pgn)[2:]  # only hex(pgn) without '0x' prefix
        for message in self.db.messages:
            message_hex = hex(message.frame_id)[
                -6:-2
            ]  # only hex(pgn) without '0x' prefix, priority and source address
            if pgn_hex == message_hex:
                return message
        log.debug("no DBC mapping registered for j1939 message [PGN: %s]", pgn_hex)
        return None
