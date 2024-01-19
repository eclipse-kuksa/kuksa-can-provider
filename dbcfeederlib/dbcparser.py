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
from typing import cast, Dict, List, Set, Tuple

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

        # by default, do not mask any bits of standard (11-bit) frame IDs
        self._frame_id_mask: int = 0b11111111111
        if expect_extended_frame_ids:
            # ignore 3 priority bits and 8 source address bits of extended
            # (29-bit) frame IDs when looking up message definitions
            self._frame_id_mask = 0b00011111111111111111100000000

        first = True
        processed_files: Set[str] = set()
        for filename in [name.strip() for name in dbc_file_names]:
            if filename in processed_files:
                log.warning("DBC file %s has already been read, ignoring it!", filename)
                continue
            processed_files.add(filename)
            if first:
                log.info("Reading definitions from bus description file %s", filename)
                database = cantools.database.load_file(
                    filename,
                    strict=use_strict_parsing,
                    frame_id_mask=self._frame_id_mask
                )
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
        self._signal_to_message_definitions = self._populate_signal_to_message_map()

    def _populate_signal_to_message_map(self) -> Dict[str, Set[cantools.database.Message]]:

        signal_to_message_defs: Dict[str, Set[cantools.database.Message]] = {}

        for msg_definition in self._db.messages:
            for inner_msg in [msg_definition, *(msg_definition.contained_messages or [])]:
                for signal in inner_msg.signals:
                    if signal.name in signal_to_message_defs:
                        signal_to_message_defs[signal.name].add(msg_definition)
                    else:
                        signal_to_message_defs[signal.name] = {msg_definition}

        if log.isEnabledFor(logging.WARNING):
            for (sig_name, messages) in signal_to_message_defs.items():
                if len(messages) > 1:
                    log.warning(
                        "Signal name %s is being used in multiple CAN messages (%s).",
                        sig_name, ', '.join([msg_def.name for msg_def in messages])
                    )
            log.warning(
                """Make sure that signals have the same semantics in all CAN messages where they are used
                to prevent unexpected behaviour when mapping VSS Data Entries to these signals."""
            )

        return signal_to_message_defs

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

    def can_frame_id_whitelist_mask(self) -> int:
        """Get the frame ID bit mask used for filtering messages received from CAN bus."""
        return self._frame_id_mask

    def get_messages_for_signal(self, sig_to_find: str) -> Set[cantools.database.Message]:
        """Get all CAN message definitions that use a given CAN signal name."""
        if sig_to_find in self._signal_to_message_definitions:
            return self._signal_to_message_definitions[sig_to_find]

        log.warning("Signal %s not found in CAN message database", sig_to_find)
        empty_set: Set[cantools.database.Message] = set()
        self._signal_to_message_definitions[sig_to_find] = empty_set
        return empty_set

    def get_message_by_frame_id(self, frame_id: int) -> cantools.database.Message:
        """
        Get the CAN message definition for a given CAN frame ID.
        Raises KeyError if no message definition for the given frame ID exists.
        """
        return self._db.get_message_by_frame_id(frame_id)

    def get_signals_by_frame_id(self, frame_id: int) -> List[cantools.database.Signal]:
        """Get the signals of the CAN message definition for a given CAN frame ID."""
        try:
            msg = self.get_message_by_frame_id(frame_id)
            signals: List[cantools.database.Signal] = list()
            for inner_msg in [msg, *(msg.contained_messages or [])]:
                signals.extend(inner_msg.signals)
            return signals
        except Exception:
            log.warning("CAN id %s not found in CAN message database", frame_id)
            return []
