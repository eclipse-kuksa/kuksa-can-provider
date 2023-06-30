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

import threading
import time
import logging
from queue import Queue
from dbcfeederlib import dbc2vssmapper
from dbcfeederlib import canclient

log = logging.getLogger(__name__)


class DBCReader:
    def __init__(self, rxqueue: Queue, mapper, dbc_parser):
        self.queue = rxqueue
        self.mapper = mapper
        self.dbc_parser = dbc_parser
        self.canidwl = self.get_whitelist()
        log.info("CAN ID whitelist={}".format(self.canidwl))
        self.run = True
        self.canclient = None

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
        self.canclient = canclient.CANClient(*args, **kwargs)
        rx_thread = threading.Thread(target=self.rx_worker)
        rx_thread.start()

    def get_whitelist(self):
        log.info("Generating CAN ID whitelist")
        white_list = []
        for entry in self.mapper.get_dbc2val_entries():
            canid = self.dbc_parser.get_canid_for_signal(entry)
            if canid is not None and canid not in white_list:
                log.info(f"Adding {entry} to white list, canid is {canid}")
                white_list.append(canid)
        return white_list

    def rx_worker(self):
        log.info("Starting Rx thread")
        while self.run:
            msg = self.canclient.recv(timeout=1)
            log.debug("processing message from CAN bus")
            if msg and msg.get_arbitration_id() in self.canidwl:
                try:
                    decode = self.dbc_parser.db.decode_message(msg.get_arbitration_id(), msg.get_data())
                    log.debug("Decoded message: %s", str(decode))
                except Exception:
                    log.warning(
                        "Error Decoding: ID:{}".format(msg.get_arbitration_id()),
                        exc_info=True,
                    )
                    continue
                rx_time = time.time()
                for k, v in decode.items():
                    vss_mappings = self.mapper.get_dbc2val_mappings(k)
                    for signal in vss_mappings:
                        if signal.time_condition_fulfilled(rx_time):
                            log.debug(f"Queueing {signal.vss_name}, triggered by {k}, raw value {v} ")
                            self.queue.put(dbc2vssmapper.VSSObservation(k, signal.vss_name, v, rx_time))
                        else:
                            log.debug(f"Ignoring {signal.vss_name}, triggered by {k}, raw value {v} ")
        log.info("Stopped Rx thread")

    def stop(self):
        self.run = False
        if self.canclient:
            self.canclient.stop()
            self.canclient = None
