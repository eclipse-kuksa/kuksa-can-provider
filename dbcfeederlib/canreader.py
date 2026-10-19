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
from dbcfeederlib.dbc2vssmapper import Mapper, VSSMapping, VSSObservation
from typing import Any, Dict, Optional
from queue import Queue

log = logging.getLogger(__name__)


class CanReader(ABC):
    """
    Provides means to read messages from a CAN bus.
    """
    def __init__(self, rxqueue: Queue, mapper: Mapper, can_port: str,
                 dump_file: Optional[str] = None, can_fd: bool = False,
                 infinite: bool = False, use_j1939: bool = False):
        """
        This init method is only supposed to be called by subclass' __init__ functions.
        """
        self._running = False
        self._queue = rxqueue
        self._mapper = mapper
        self._running = False
        self._can_player: Optional[CANplayer] = None

        can_filters = mapper.can_frame_id_whitelist(use_j1939)
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
            self._can_player = CANplayer(dump_file, can_port, infinite=infinite)

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

    def _process_can_message(self, frame_id: int, data: bytes | bytearray):
        try:
            if not isinstance(data, (bytes, bytearray)):
                raise TypeError(f"Expected bytes or bytearray CAN payload, got {type(data).__name__}")

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

    def _process_multipacket_message(self, frame_id: int, data: list[int]):
        try:
            message_def = self._mapper.get_message_by_frame_id(frame_id)
            if message_def is not None:
                # create set comprehension to avoid duplicates
                # and to filter out signals without delimited-list mapping
                candidates = {
                    signal.name
                    for signal in message_def.signals
                    if any(
                        mapping.dbc_name == signal.name
                        and mapping.delimited_list is not None
                        for mapping in self._mapper.get_dbc2vss_mappings(signal.name)
                    )
                }

                if not candidates:
                    log.warning(
                        "No delimited-list mapping found for multipacket CAN message with frame ID %#x",
                        frame_id,
                    )
                    return

                if len(candidates) > 1:
                    log.error(
                        "Ambiguous delimited-list mappings for multipacket CAN message "
                        "with frame ID %#x: %s",
                        frame_id,
                        sorted(candidates),
                    )
                    return

                # candidates is guaranteed to have exactly one element at this point
                signal_name = next(iter(candidates))
                self._handle_decoded_frame(
                    message_def,
                    {signal_name: data},
                    time.time(),
                    only_delimited_list=True,
                )

        except Exception:
            log.warning("Error processing multipacket CAN message with frame ID: %#x", frame_id, exc_info=True)

    def _handle_decoded_frame(
        self,
        message_def: cantools.database.Message,
        decoded: SignalMappingType | dict[str, list[int]],
        rx_time: float,
        only_delimited_list: bool = False
    ):
        for signal_name, raw_value in decoded.items():  # type: ignore
            signal: cantools.database.Signal = message_def.get_signal_by_name(signal_name)
            # filter out signals with values out of defined range
            # which is usually because the signal's value is unavailable
            # (represented as e.g. "all bits set")
            if not self._is_signal_value_in_range(signal_name, signal, raw_value):
                continue
            for signal_mapping in self._mapper.get_dbc2vss_mappings(signal_name):
                if only_delimited_list and signal_mapping.delimited_list is None:
                    continue

                if signal_mapping.time_condition_fulfilled(rx_time):
                    log.debug(
                        "Queueing %s, triggered by %s, raw value %s",
                        signal_mapping.vss_name, signal_name, raw_value
                    )

                    filter_mismatch = False
                    if signal_mapping.multiplexer is not None:
                        multiplexer_idx = 0
                        multiplexer_len = signal_mapping.multiplexer.size()
                        while multiplexer_idx < multiplexer_len:
                            multiplex_name = signal_mapping.multiplexer.signals[multiplexer_idx]
                            multiplex_value = signal_mapping.multiplexer.values[multiplexer_idx]

                            if decoded[multiplex_name] != multiplex_value:
                                filter_mismatch = True

                            multiplexer_idx += 1

                    if not filter_mismatch:
                        if (
                            signal_mapping.transform is not None
                            and isinstance(signal_mapping.transform, dict)
                            and "datetime" in signal_mapping.transform
                        ):
                            # handle datetime transformation
                            if not self._datetime_inputs_are_valid(message_def, decoded, signal_mapping):
                                continue
                            self._queue.put(VSSObservation(
                                signal_name, signal_mapping.vss_name, decoded, rx_time, "frame"))
                        else:
                            self._queue.put(VSSObservation(
                                signal_name, signal_mapping.vss_name, raw_value, rx_time))

                else:
                    log.debug(
                        "Ignoring %s, triggered by %s, raw value %s",
                        signal_mapping.vss_name, signal_name, raw_value
                    )

    def _is_signal_value_in_range(
        self,
        signal_name: str,
        signal: cantools.database.Signal,
        raw_value: Any,
    ) -> bool:
        if not isinstance(raw_value, (int, float)):
            return True

        if signal.minimum is not None and raw_value < signal.minimum:
            log.debug(
                "discarding out-of-range value [signal: %s, min: %s, value: %s]",
                signal_name, signal.minimum, raw_value
            )
            return False

        if signal.maximum is not None and raw_value > signal.maximum:
            log.debug(
                "discarding out-of-range value [signal: %s, max: %s, value: %s]",
                signal_name, signal.maximum, raw_value
            )
            return False

        return True

    def _datetime_inputs_are_valid(
        self,
        message_def: cantools.database.Message,
        decoded: SignalMappingType | dict[str, list[int]],
        signal_mapping: VSSMapping,
    ) -> bool:
        dt_details = signal_mapping.transform["datetime"]
        dt_inputs = dt_details.get("inputs", {})

        for input_name, input_signal_name in dt_inputs.items():
            if input_signal_name not in decoded:  # type: ignore
                log.debug(
                    "discarding datetime observation [vss: %s, input: %s, signal: %s, reason: missing input]",
                    signal_mapping.vss_name,
                    input_name,
                    input_signal_name,
                )
                return False
            raw_value = decoded[input_signal_name]  # type: ignore

            try:
                signal = message_def.get_signal_by_name(input_signal_name)
            except KeyError:
                log.debug(
                    "discarding datetime observation [vss: %s, input: %s, signal: %s, "
                    "reason: signal missing in DBC message]",
                    signal_mapping.vss_name,
                    input_name,
                    input_signal_name,
                )
                return False

            if not self._is_signal_value_in_range(input_signal_name, signal, raw_value):
                log.debug(
                    "discarding datetime observation [vss: %s, input: %s, signal: %s]",
                    signal_mapping.vss_name,
                    input_name,
                    input_signal_name,
                )
                return False

        return True
