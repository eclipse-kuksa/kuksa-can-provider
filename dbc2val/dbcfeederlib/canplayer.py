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
import time

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
        self.run = True
        self.index = 0
        self.indexout = 1
        self.messages = [can.message]
        self.timestamp = None

        # open the file for reading can messages
        log.info("Replaying candump from {}".format(dumpfile))
        log_reader = can.LogReader(dumpfile)
        # get all messages out of the dumpfile and store into array of can messages
        for msg in log_reader:
            # store the sum of messages
            self.index = self.index + 1
            # add message to array
            self.messages.append(msg)
            # log.debug("Message Read out of candump file: \n{}".format(msgFromLog))
        log.debug("Parsing of can messages form the dump file is finished")

    def start_replaying(self, canport):
        log.debug("Using virtual bus to replay CAN messages (channel: %s)", canport)
        self.bus = can.interface.Bus(bustype="virtual", channel=canport, bitrate=500000) # pylint: disable=abstract-class-instantiated
        txThread = threading.Thread(target=self.txWorker)
        txThread.start()

    def getNextMessage(self):
        val = self.messages[self.indexout]
        self.indexout += 1
        # in case of end of array set the index pointer to start again
        if self.indexout >= self.index:
            self.indexout = 1
        return val

    def txWorker(self):
        log.info("Starting Tx thread")

        while self.run:
            next_message = self.getNextMessage()
            msg = can.Message(
                arbitration_id=next_message.arbitration_id,
                data=next_message.data,
                timestamp=next_message.timestamp,
            )
            if msg:
                try:
                    self.bus.send(msg)
                    log.debug(f"Message sent on {self.bus.channel_info}")
                    log.debug(f"Message: {msg}")
                except can.CanError:
                    log.debug("Message NOT sent")

            # add a sleep of 1 ms to not busy loop here
            if self.timestamp:
                log.debug(" --> delay({})".format((msg.timestamp - self.timestamp)))
                if msg.timestamp > self.timestamp:
                    time.sleep(msg.timestamp - self.timestamp)
                else:
                    log.debug(
                        "msg.timestamp not increased: ({} < {})".format(
                            msg.timestamp, self.timestamp
                        )
                    )
            else:
                time.sleep(0.001)

            self.timestamp = msg.timestamp

        log.info("Stopped Tx thread")

    def stop(self):
        self.run = False
