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
import can

# fixes issues with pytinstaller not detecting can.interfaces.virtual usage
from can.interfaces.virtual import VirtualBus  # noqa: F401

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

    def __init__(self, dumpfile):
        self.run = False
        self.messages = [can.message]
        self.dumpfile = dumpfile

    def process_log(self):
        # open the file for reading can messages
        log.info("Replaying CAN message log {}".format(self.dumpfile))
        # using MessageSync in order to consider timestamps of CAN messages
        # and the delays between them
        log_reader = can.MessageSync(messages=can.LogReader(self.dumpfile), timestamps=True)
        for msg in log_reader:
            if not self.run:
                break
            try:
                self.bus.send(msg)
                log.debug(f"Message sent on {self.bus.channel_info}")
                log.debug(f"Message: {msg}")
            except can.CanError:
                log.debug("Failed to send message via CAN bus")

        log.debug("Replayed all messages from CAN log file")

    def txWorker(self):
        log.info("Starting Tx thread")

        while self.run:
            self.process_log()

        log.info("Stopped Tx thread")

    def start_replaying(self, canport):
        log.debug("Using virtual bus to replay CAN messages (channel: %s)", canport)
        self.bus = can.interface.Bus(bustype="virtual", channel=canport, bitrate=500000) # pylint: disable=abstract-class-instantiated
        self.run = True
        txThread = threading.Thread(target=self.txWorker)
        txThread.start()

    def stop(self):
        self.run = False
