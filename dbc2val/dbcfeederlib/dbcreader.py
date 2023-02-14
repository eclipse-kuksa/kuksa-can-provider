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

import can
import cantools
import threading
import time
import logging
from dbcfeederlib import dbc2vssmapper
from queue import Queue

log = logging.getLogger(__name__)


class DBCReader:
    def __init__(self, rxqueue: Queue, dbcfile: str, mapper: str, use_strict_parsing: bool):
        self.queue = rxqueue
        self.mapper = mapper
        log.info("Reading DBC file {}".format(dbcfile))
        self.db = cantools.database.load_file(dbcfile, strict = use_strict_parsing)
        self.canidwl = self.get_whitelist()
        log.info("CAN ID whitelist={}".format(self.canidwl))
        self.parseErr = 0
        self.run = True

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
        self.bus = can.interface.Bus(*args, **kwargs) # pylint: disable=abstract-class-instantiated
        rxThread = threading.Thread(target=self.rxWorker)
        rxThread.start()

    def get_whitelist(self):
        log.info("Collecting signals, generating CAN ID whitelist")
        wl = []
        for entry in self.mapper.map():
            canid = self.get_canid_for_signal(entry[0])
            if canid is not None and canid not in wl:
                log.info(f"Adding {entry[0]} to white list, canid is {canid}")
                wl.append(canid)
        return wl

    def get_canid_for_signal(self, sig_to_find):
        for msg in self.db.messages:
            for signal in msg.signals:
                if signal.name == sig_to_find:
                    id = msg.frame_id
                    log.debug(
                        "Found signal in DBC file {} in CAN frame id 0x{:02x}".format(
                            signal.name, id
                        )
                    )
                    return id
        log.warning("Signal {} not found in DBC file".format(sig_to_find))
        return None

    def rxWorker(self):
        log.info("Starting Rx thread")
        while self.run:
            msg = self.bus.recv(timeout=1)
            log.debug("processing message from CAN bus")
            if msg and msg.arbitration_id in self.canidwl:
                try:
                    decode = self.db.decode_message(msg.arbitration_id, msg.data)
                    log.debug("Decoded message: %s", str(decode))
                except Exception:
                    self.parseErr += 1
                    log.warning(
                        "Error Decoding: ID:{}".format(msg.arbitration_id),
                        exc_info=True,
                    )
                    continue
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
        log.info("Stopped Rx thread")

    def stop(self):
        self.run = False
