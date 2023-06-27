#!/usr/bin/python3

########################################################################
# Copyright (c) 2023 Robert Bosch GmbH
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

import logging
import sys
from typing import Set, Optional, Dict, cast
import cantools

log = logging.getLogger(__name__)


class DBCParser:
    def __init__(self, dbcfile: str, use_strict_parsing: bool = True):

        first = True
        found_names = set()
        for name in dbcfile.split(","):
            filename = name.strip()
            if filename in found_names:
                log.warn("The DBC file {} has already been read, ignoring it!".format(filename))
                continue
            found_names.add(filename)
            if first:
                log.info("Reading DBC file {} as first file".format(filename))
                db = cantools.database.load_file(filename, strict=use_strict_parsing)
                # load_file can return multiple types of databases, make sure we have CAN database
                if isinstance(db, cantools.database.can.database.Database):
                    self.db = cast(cantools.database.can.database.Database, db)
                    first = False
                else:
                    log.error("File is not a CAN database, likely a diagnostics database")
                    sys.exit(-1)
            else:
                log.info("Adding definitions from {}".format(filename))
                self.db.add_dbc_file(filename)

        # Init some dictionaries to speed up search
        self.signal_to_canid: Dict[str, Optional[int]] = {}
        self.canid_to_signals: Dict[int, Set[str]] = {}

    def get_canid_for_signal(self, sig_to_find: str) -> Optional[int]:
        if sig_to_find in self.signal_to_canid:
            return self.signal_to_canid[sig_to_find]

        for msg in self.db.messages:
            for signal in msg.signals:
                if signal.name == sig_to_find:
                    frame_id = msg.frame_id
                    log.info(
                        "Found signal in DBC file {} in CAN frame id 0x{:02x}".format(
                            signal.name, frame_id
                        )
                    )
                    self.signal_to_canid[sig_to_find] = frame_id
                    return frame_id
        log.warning("Signal {} not found in DBC file".format(sig_to_find))
        self.signal_to_canid[sig_to_find] = None
        return None

    def get_signals_for_canid(self, canid: int) -> Set[str]:

        if canid in self.canid_to_signals:
            return self.canid_to_signals[canid]

        for msg in self.db.messages:
            if canid == msg.frame_id:
                names = set()
                for signal in msg.signals:
                    names.add(signal.name)
                self.canid_to_signals[canid] = names
                return names
        log.warning(f"CAN id {canid} not found in DBC file")
        self.canid_to_signals[canid] = set()
        return set()
