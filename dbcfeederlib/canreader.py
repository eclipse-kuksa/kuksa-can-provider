#!/usr/bin/env python3

#################################################################################
# Copyright (c) 2023 Contributors to the Eclipse Foundation
#
# See the NOTICE file(s) distributed with this work for additional
# information regarding copyright ownership.
#
# This program and the accompanying materials are made available under the
# terms of the Apache License 2.0 which is available at
# http://www.apache.org/licenses/LICENSE-2.0
#
# SPDX-License-Identifier: Apache-2.0
#################################################################################

import logging
import time

from abc import ABC, abstractmethod

import cantools.database  # type: ignore

from cantools.typechecking import SignalMappingType
from dbcfeederlib.canplayer import CANplayer
from dbcfeederlib.dbc2vssmapper import Mapper, VSSObservation
from typing import Any, Dict, Optional
from queue import Queue

log = logging.getLogger(__name__)


class CanReader(ABC):
    """
    Provides means to read messages from a CAN bus.
    """
    def __init__(self, rxqueue: Queue, mapper: Mapper, can_port: str,
                 dump_file: Optional[str] = None, can_fd: bool = False):
        """
        This init method is only supposed to be called by subclass' __init__ functions.
        """
        self._running = False
        self._queue = rxqueue
        self._mapper = mapper
        self._running = False
        self._can_player: Optional[CANplayer] = None

        can_filters = mapper.can_frame_id_whitelist()
        log.info("Using CAN frame ID whitelist=%s", can_filters)
        self._can_kwargs: Dict[str, Any] = {
            "interface": "socketcan",
            "channel": can_port,
            "can_filters": can_filters,
            "fd": can_fd
        }
        if dump_file is not None:
            self._can_kwargs["interface"] = "virtual"
            self._can_kwargs["bitrate"] = 500000
            self._can_player = CANplayer(dump_file, can_port)

    def is_running(self) -> bool:
        return self._running

    @abstractmethod
    def _start_can_bus_listener(self):
        """
        Start listening to CAN bus.
        """
        pass

    def start(self):
        """
        Start processing of messages.
        """
        self._running = True
        self._start_can_bus_listener()
        if self._can_player is not None:
            self._can_player.start()

    @abstractmethod
    def _stop_can_bus_listener(self):
        """
        Stop listening to CAN bus.
        """
        pass

    def stop(self):
        if self._can_player is not None:
            self._can_player.stop()
        self._running = False
        self._stop_can_bus_listener()

    def _process_can_message(self, frame_id: int, data: Any):
        try:
            message_def = self._mapper.get_message_by_frame_id(frame_id)
            if message_def is not None:
                decode = message_def.decode(bytes(data), allow_truncated=True, decode_containers=True)
                if log.isEnabledFor(logging.DEBUG):
                    log.debug("Decoded message: %s", str(decode))
                rx_time = time.time()

                if isinstance(decode, dict):
                    # handle normal frame
                    self._handle_decoded_frame(message_def, decode, rx_time)
                else:
                    # handle container frame
                    for tmp in decode:
                        if isinstance(tmp[1], bytes):
                            continue
                        self._handle_decoded_frame(tmp[0], tmp[1], rx_time)

        except Exception:
            log.warning("Error processing CAN message with frame ID: %#x", frame_id, exc_info=True)

    def _handle_decoded_frame(self, message_def: cantools.database.Message, decoded: SignalMappingType, rx_time: float):
        for signal_name, raw_value in decoded.items():  # type: ignore
            signal: cantools.database.Signal = message_def.get_signal_by_name(signal_name)
            if isinstance(raw_value, (int, float)):
                # filter out signals with values out of defined range
                # which is usually because the signal's value is unavailable
                # (represented as e.g. "all bits set")
                if signal.minimum is not None and raw_value < signal.minimum:
                    log.debug(
                        "discarding out-of-range value [signal: %s, min: %s, value: %s]",
                        signal_name, signal.minimum, raw_value
                    )
                    continue
                if signal.maximum is not None and raw_value > signal.maximum:
                    log.debug(
                        "discarding out-of-range value [signal: %s, max: %s, value: %s]",
                        signal_name, signal.maximum, raw_value
                    )
                    continue
            for signal_mapping in self._mapper.get_dbc2vss_mappings(signal_name):

                if signal_mapping.time_condition_fulfilled(rx_time):
                    log.debug(
                        "Queueing %s, triggered by %s, raw value %s",
                        signal_mapping.vss_name, signal_name, raw_value
                    )
                    self._queue.put(VSSObservation(
                        signal_name, signal_mapping.vss_name, raw_value, rx_time))
                else:
                    log.debug(
                        "Ignoring %s, triggered by %s, raw value %s",
                        signal_mapping.vss_name, signal_name, raw_value
                    )
