#!/usr/bin/python3

########################################################################
# Copyright (c) 2020 Robert Bosch GmbH
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

# This script is to read CAN messages based on PGN - SAE J1939
# Prior to using this script, j1939 and
# the relevant wheel-package should be installed first:
# $ pip3 install j1939
# $ git clone https://github.com/benkfra/j1939.git
# $ cd j1939
# $ pip install

import logging
import time

import cantools
import j1939

log = logging.getLogger(__name__)


class J1939Reader(j1939.ControllerApplication):
    # CA to produce messages
    # This CA produces simulated sensor values and cyclically sends them to
    # the bus with the PGN 0xFEF6 (Intake Exhaust Conditions 1)

    def __init__(self, rxqueue, dbcfile, mapper):
        # compose the name descriptor for the new ca
        name = j1939.Name(
            arbitrary_address_capable=0,
            industry_group=j1939.Name.IndustryGroup.Industrial,
            vehicle_system_instance=1,
            vehicle_system=1,
            function=1,
            function_instance=1,
            ecu_instance=1,
            manufacturer_code=666,
            identity_number=1234567,
        )
        device_address_preferred = 128
        # old fashion calling convention for compatibility with Python2
        j1939.ControllerApplication.__init__(self, name, device_address_preferred)
        # adaptation
        self.queue = rxqueue
        self.db = cantools.database.load_file(dbcfile)
        self.mapper = mapper
        self.canidwl = self.get_whitelist()
        self.parseErr = 0
        self.run = True

    def start(self):
        # Starts the CA
        # (OVERLOADED function)

        # add our timer event
        self._ecu.add_timer(0.500, self.timer_callback)
        # call the super class function
        j1939.ControllerApplication.start(self)

    def stop(self):
        j1939.ControllerApplication.stop(self)

    def timer_callback(self, cookie):
        # Callback for sending the IEC1 message
        # This callback is registered at the ECU timer event mechanism to be
        # executed every 500ms.
        # :param cookie:
        # A cookie registered at 'add_timer'. May be None.

        # wait until we have our device_address
        if self.state != j1939.ControllerApplication.State.NORMAL:
            # returning true keeps the timer event active
            return True

        pgn = j1939.ParameterGroupNumber(0, 0xFE, 0xF6)
        data = [
            j1939.ControllerApplication.FieldValue.NOT_AVAILABLE_8,  # Particulate Trap Inlet Pressure (SPN 81)
            j1939.ControllerApplication.FieldValue.NOT_AVAILABLE_8,  # Boost Pressure (SPN 102)
            j1939.ControllerApplication.FieldValue.NOT_AVAILABLE_8,  # Intake Manifold 1 Temperature (SPN 105)
            j1939.ControllerApplication.FieldValue.NOT_AVAILABLE_8,  # Air Inlet Pressure (SPN 106)
            j1939.ControllerApplication.FieldValue.NOT_AVAILABLE_8,  # Air Filter 1 Differential Pressure (SPN 107)
            j1939.ControllerApplication.FieldValue.NOT_AVAILABLE_16_ARR[
                0
            ],  # Exhaust Gas Temperature (SPN 173)
            j1939.ControllerApplication.FieldValue.NOT_AVAILABLE_16_ARR[1],
            j1939.ControllerApplication.FieldValue.NOT_AVAILABLE_8,  # Coolant Filter Differential Pressure (SPN 112)
        ]

        # SPN 105, Range -40..+210
        # (Offset -40)
        receiverTemperature = 30
        data[2] = receiverTemperature + 40

        self.send_message(6, pgn.value, data)

        # returning true keeps the timer event active
        return True

    def get_whitelist(self):
        log.info("Collecting signals, generating CAN ID whitelist")
        wl = []
        for entry in self.mapper.map():
            canid = self.get_canid_for_signal(entry[0])
            if canid is not None and canid not in wl:
                wl.append(canid)
        return wl

    def get_canid_for_signal(self, sig_to_find):
        for msg in self.db.messages:
            for signal in msg.signals:
                if signal.name == sig_to_find:
                    id = msg.frame_id
                    log.info(
                        "Found signal {} in CAN frame id 0x{:02x}".format(
                            signal.name, id
                        )
                    )
                    return id
        log.warning("Signal {} not found in DBC file".format(sig_to_find))
        return None

    def start_listening(self, *args, **kwargs):
        """Start listening to CAN bus

        Arguments are passed directly to :class:`can.BusABC`. Typically these
        may include:

        :param channel:
            Backend specific channel for the CAN interface.
        :param str bustype:
            Name of the interface. See
            `python-can manual <https://python-can.readthedocs.io/en/latest/configuration.html#interface-names>`__
            for full list of supported interfaces.
        :param int bitrate:
            Bitrate in bit/s.
        """
        # create the ElectronicControlUnit (one ECU can hold multiple ControllerApplications)
        ecu = j1939.ElectronicControlUnit()

        # Connect to the CAN bus
        ecu.connect(*args, **kwargs)

        # add CA to the ECU
        ecu.add_ca(controller_application=self)
        self.start()

    def on_message(self, pgn, data):
        message = self.identify_message(pgn)
        if message is not None:
            signals = message._signals
            for signal in signals:
                self.put_signal_in_queue(signal, data)

    def identify_message(self, pgn):
        pgn_hex = hex(pgn)[2:]  # only hex(pgn) without '0x' prefix
        for message in self.db.messages:
            message_hex = hex(message.frame_id)[
                -6:-2
            ]  # only hex(pgn) without '0x' prefix, priority and source address
            if pgn_hex == message_hex:
                return message
        return None

    def put_signal_in_queue(self, signal, data):
        name = signal._name
        byte_order = signal._byte_order  # 'little_endian' or 'big_endian'
        scale = signal._scale
        offset = signal._offset
        data_type = type(data).__name__
        val = 0
        # When data_type is "list", `decode_signal` should be used. (Byte Level)
        if data_type != "bytearray":
            start_byte = int(signal._start / 8)  # start from 0
            num_of_bytes = signal._length / 8  # most likely 1 or 2
            val = self.decode_signal(
                start_byte, num_of_bytes, byte_order, scale, offset, data
            )
        # When data_type is "bytearray", `decode_byte_array` should be used. (Bit Level)
        else:
            start_bit = signal._start
            num_of_bits = signal._length
            val = self.decode_byte_array(
                start_bit, num_of_bits, byte_order, scale, offset, data
            )
        if val < signal._minimum:
            val = signal._minimum
        elif val > signal._maximum:
            val = signal._maximum
        if name in self.mapper:
            rxTime = time.time()
            if self.mapper.minUpdateTimeElapsed(name, rxTime):
                self.queue.put((name, val))

    def decode_signal(self, start_byte, num_of_bytes, byte_order, scale, offset, data):
        val = 0
        if num_of_bytes == 1:
            raw_value = data[start_byte]
            val = offset + raw_value * scale
        else:
            val = self.decode_2bytes(start_byte, byte_order, scale, offset, data)
        return val

    def decode_2bytes(self, start_byte, byte_order, scale, offset, data):
        start_data = data[start_byte]
        end_data = data[start_byte + 1]
        start_data_hex = hex(start_data)[2:]  # without '0x' prefix
        end_data_hex = hex(end_data)[2:]  # without '0x' prefix
        lit_end_hex_str = ""
        # Little Endian - Intel, AMD
        if byte_order == "little_endian":
            lit_end_hex_str = "0x" + end_data_hex + start_data_hex
        # Big Endian (a.k.a Endianness) - Motorola, IBM
        else:
            lit_end_hex_str = "0x" + start_data_hex + end_data_hex
        raw_value = int(lit_end_hex_str, base=16)
        val = offset + raw_value * scale
        return val

    def decode_byte_array(
        self, start_bit, num_of_bits, byte_order, scale, offset, data
    ):
        binary_str = ""
        # temp_bit_array = []
        binstr = ""
        # Little Endian - Intel, AMD
        if byte_order == "little_endian":
            for i in range(len(data)):
                dec = data[i]
                binstr = binstr + format(dec, "#010b")[2:][::-1]
        # Big Endian (a.k.a Endianness) - Motorola, IBM
        else:
            for i in range(len(data)):
                dec = data[i]
                binstr = binstr + format(dec, "#010b")[2:]
        # bit_array = list(reversed(temp_bit_array)) To call the smallest bit first
        for i in range(0, num_of_bits):
            binary_str = binstr[start_bit + i] + binary_str
        binary_str = "0b" + binary_str
        raw_value = int(binary_str, base=2)
        val = offset + raw_value * scale
        return val
