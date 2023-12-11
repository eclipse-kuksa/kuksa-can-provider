########################################################################
# Copyright (c) 2022,2023 Contributors to the Eclipse Foundation
#
# See the NOTICE file(s) distributed with this work for additional
# information regarding copyright ownership.
#
# This program and the accompanying materials are made available under the
# terms of the Apache License 2.0 which is available at
# http://www.apache.org/licenses/LICENSE-2.0
#
# SPDX-License-Identifier: Apache-2.0
########################################################################

import logging
import threading

import can  # type: ignore
from can.interfaces.virtual import VirtualBus

log = logging.getLogger(__name__)


class CANplayer:
    """
    Replay logged CAN messages from a file.

    The format is determined from the file suffix which can be one of:
      * .asc
      * .blf
      * .csv
      * .db
      * .log
      * .trc

    Gzip compressed files can be used as long as the original
    files suffix is one of the above (e.g. filename.asc.gz).
    """

    def __init__(self, dumpfile: str, can_port: str):
        self._running = False
        # open the file for reading can messages
        log.info("Starting repeated replay of CAN messages from log file %s", dumpfile)
        self._dumpfile = dumpfile
        self._can_port = can_port
        log.debug("Using virtual bus to replay CAN messages (channel: %s)", self._can_port)
        self._bus = VirtualBus(channel=can_port, bitrate=500000)

    def _process_log(self):
        # using MessageSync in order to consider timestamps of CAN messages
        # and the delays between them

        messages = can.LogReader(self._dumpfile)
        log_reader = can.MessageSync(messages=messages, timestamps=True)
        for msg in log_reader:
            if not self._running:
                return
            try:
                self._bus.send(msg)
                if log.isEnabledFor(logging.DEBUG):
                    log.debug("Sent message [channel: %s]: %s", self._bus.channel_info, msg)
            except can.CanError:
                log.error("Failed to send message via CAN bus")
        log.info("Replayed all messages from CAN log file")

    def _tx_worker(self):
        log.info("Starting to write CAN messages to bus")

        while self._running:
            self._process_log()

        log.info("Stopped writing CAN messages to bus")

    def start(self):
        self._running = True
        tx_thread = threading.Thread(target=self._tx_worker)
        tx_thread.start()

    def stop(self):
        self._running = False
        if self._bus:
            self._bus.shutdown()
            self._bus = None
