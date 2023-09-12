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
import can  # type: ignore

log = logging.getLogger(__name__)


class CANMessage:
    """
    Wrapper class to hide dependency to CAN package.
    Reason is to make it simple to replace the CAN package dependency with something else if your KUKSA.val
    integration cannot interact directly with CAN, but rather interacts with some custom CAN solution/middleware.
    This wrapper class represents a https://python-can.readthedocs.io/en/stable/message.html#can.Message
    """

    def __init__(self, msg: can.Message):
        self.msg = msg

    def get_arbitration_id(self) -> int:
        """Get arbitration/frame id of message"""
        return self.msg.arbitration_id

    def get_data(self):
        """Get message data"""
        return self.msg.data
