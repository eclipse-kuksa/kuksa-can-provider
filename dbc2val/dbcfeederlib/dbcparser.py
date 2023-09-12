#!/usr/bin/python3

########################################################################
# Copyright (c) 2023 Contributors to the Eclipse Foundation
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
import os

import cantools.database  # type: ignore

from types import MappingProxyType
from typing import cast, Dict, Optional, List, Set, Tuple


log = logging.getLogger(__name__)


class DBCParser:

    _dbc_file_encodings = MappingProxyType({
                'dbc': 'cp1252',
                'sym': 'cp1252'
            })

    def __init__(self,
                 dbc_file_names: List[str],
                 use_strict_parsing: bool = True,
                 expect_extended_frame_ids: bool = False):

        first = True
        processed_files: Set[str] = set()
        for filename in [name.strip() for name in dbc_file_names]:
            if filename in processed_files:
                log.warning("DBC file %s has already been read, ignoring it!", filename)
                continue
            processed_files.add(filename)
            if first:
                # by default, do not mask any bits of standard (11-bit) frame IDs
                mask = 0b11111111111
                if expect_extended_frame_ids:
                    # ignore 3 priority bits and 8 source address bits of extended
                    # (29-bit) frame IDs when looking up message definitions
                    mask = 0b00011111111111111111100000000
                log.info("Reading definitions from DBC file %s", filename)
                database = cantools.database.load_file(filename, strict=use_strict_parsing, frame_id_mask=mask)
                # load_file can return multiple types of databases, make sure we have CAN database
                if isinstance(database, cantools.database.can.database.Database):
                    self._db = cast(cantools.database.can.database.Database, database)
                    first = False
                else:
                    log.error("File %s is not a CAN database, likely a diagnostics database", filename)
                    sys.exit(-1)
            else:
                log.info("Adding definitions from DBC file %s", filename)
                self._add_db_file(filename)

        # Init some dictionaries to speed up search
        self._signal_to_canid: Dict[str, Optional[int]] = {}
        self._canid_to_signals: Dict[int, Set[str]] = {}

    def _determine_db_format_and_encoding(self, filename) -> Tuple[str, str]:
        db_format = os.path.splitext(filename)[1][1:].lower()

        try:
            encoding = DBCParser._dbc_file_encodings[db_format]
        except KeyError:
            encoding = 'utf-8'

        return db_format, encoding

    def _add_db_file(self, filename: str):
        db_format, encoding = self._determine_db_format_and_encoding(filename)
        if db_format == "arxml":
            self._db.add_arxml_file(filename, encoding)
        elif db_format == "dbc":
            self._db.add_dbc_file(filename, encoding)
        elif db_format == "kcd":
            self._db.add_kcd_file(filename, encoding)
        elif db_format == "sym":
            self._db.add_sym_file(filename, encoding)
        else:
            log.warning("Cannot read CAN message definitions from file using unsupported format: %s", db_format)

    def get_canid_for_signal(self, sig_to_find: str) -> Optional[int]:
        if sig_to_find in self._signal_to_canid:
            return self._signal_to_canid[sig_to_find]

        for msg in self._db.messages:
            for signal in msg.signals:
                if signal.name == sig_to_find:
                    frame_id = msg.frame_id
                    log.debug("Found signal %s in CAN message with frame ID %#x", signal.name, frame_id)
                    self._signal_to_canid[sig_to_find] = frame_id
                    return frame_id
        log.warning("Signal %s not found in CAN message database", sig_to_find)
        self._signal_to_canid[sig_to_find] = None
        return None

    def get_signals_for_canid(self, canid: int) -> Set[str]:

        if canid in self._canid_to_signals:
            return self._canid_to_signals[canid]

        names: Set[str] = set()
        message = self.get_message_for_canid(canid)
        if message is not None:
            for signal in message.signals:
                names.add(signal.name)
        self._canid_to_signals[canid] = names
        return names

    def get_message_for_canid(self, canid: int) -> Optional[cantools.database.Message]:
        try:
            return self._db.get_message_by_frame_id(canid)
        except KeyError:
            log.debug("No DBC mapping registered for CAN frame id %#x", canid)
            return None
