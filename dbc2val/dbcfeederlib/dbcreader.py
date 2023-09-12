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

import threading
import time
import logging

from queue import Queue

from dbcfeederlib import dbc2vssmapper
from dbcfeederlib import canclient

log = logging.getLogger(__name__)


class DBCReader:
    def __init__(self, rxqueue: Queue, mapper: dbc2vssmapper.Mapper):
        self._queue = rxqueue
        self._mapper = mapper
        self._canidwl = self.get_whitelist()
        log.info("CAN ID whitelist=%s", self._canidwl)
        self._running = False
        self._canclient = None

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
        self._running = True
        self._canclient = canclient.CANClient(*args, **kwargs)
        rx_thread = threading.Thread(target=self._rx_worker)
        rx_thread.start()

    def get_whitelist(self):
        log.debug("Generating CAN ID whitelist")
        white_list = []
        for signal_name in self._mapper.get_dbc2vss_entries():
            canid = self._mapper.get_canid_for_signal(signal_name)
            if canid is not None and canid not in white_list:
                log.debug("Adding CAN frame id %d of message containing signal %s to white list", canid, signal_name)
                white_list.append(canid)
        return white_list

    def _process_message(self, frame_id: int, data: bytearray):

        log.debug("processing message with frame ID %#x from CAN bus", frame_id)
        try:
            message_def = self._mapper.get_message_for_canid(frame_id)
            if message_def is not None:
                decode = message_def.decode(bytes(data), allow_truncated=True)
                if log.isEnabledFor(logging.DEBUG):
                    log.debug("Decoded message: %s", str(decode))

                rx_time = time.time()
                for k, v in decode.items():  # type: ignore
                    vss_mappings = self._mapper.get_dbc2vss_mappings(k)
                    for signal in vss_mappings:
                        if signal.time_condition_fulfilled(rx_time):
                            log.debug("Queueing %s, triggered by %s, raw value %s", signal.vss_name, k, v)
                            self._queue.put(dbc2vssmapper.VSSObservation(k, signal.vss_name, v, rx_time))
                        else:
                            log.debug("Ignoring %s, triggered by %s, raw value %s", signal.vss_name, k, v)
        except Exception:
            log.warning("Error decoding message with frame ID: %#x", frame_id, exc_info=True)

    def _rx_worker(self):
        log.info("Starting Rx thread")
        while self._running:
            can_message = self._canclient.recv(timeout=1)
            if can_message is not None:
                frame_id = can_message.get_arbitration_id()
                if frame_id in self._canidwl:
                    self._process_message(frame_id, can_message.get_data())
                else:
                    log.debug("ignoring CAN message with frame ID %s not on whitelist", frame_id)
        log.info("Stopped Rx thread")

    def stop(self):
        self._running = False
        if self._canclient:
            self._canclient.stop()
            self._canclient = None
