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
from typing import Optional
import can  # type: ignore
from dbcfeederlib import canmessage

log = logging.getLogger(__name__)


class CANClient:
    """
    Wrapper class to hide dependency to CAN package.
    Reason is to make it simple to replace the CAN package dependency with something else if your KUKSA.val
    integration cannot interact directly with CAN, but rather interacts with some custom CAN solution/middleware
    """

    def __init__(self, *args, **kwargs):
        self.bus = can.interface.Bus(*args, **kwargs)  # pylint: disable=abstract-class-instantiated

    def stop(self):
        if self.bus:
            self.bus.shutdown()
            self.bus = None

    def recv(self, timeout: int = 1) -> Optional[canmessage.CANMessage]:
        """Wait for message from CAN"""
        try:
            msg = self.bus.recv(timeout)
        except can.CanError:
            msg = None
            if self.bus:
                log.error("Error while waiting for recv from CAN", exc_info=True)
            else:
                # This is expected if we are shutting down
                log.debug("Exception received during shutdown")

        if msg:
            canmsg = canmessage.CANMessage(msg)
            return canmsg
        return None

    def send(self, arbitration_id, data):
        """Send message to CAN"""
        msg = can.Message(arbitration_id=arbitration_id, data=data)
        try:
            self.bus.send(msg)
            log.debug(f"Message sent on {self.bus.channel_info}")
            log.debug(f"Message: {msg}")
        except can.CanError:
            log.error("Failed to send message via CAN bus")
