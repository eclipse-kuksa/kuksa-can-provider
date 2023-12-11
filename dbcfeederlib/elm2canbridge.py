#!/usr/bin/python3

########################################################################
# Copyright (c) 2020 Contributors to the Eclipse Foundation
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

import os
import sys
import serial  # type: ignore
import can  # type: ignore
import threading

from multiprocessing import Queue, Process
from typing import Any, Dict, List, Optional

# To limit memory in case parsing thread dies and serial reader keeps filling
QUEUE_MAX_ELEMENTS = 2048


class elm2canbridge:
    def __init__(self, canport: str, cfg: Dict[str, Any], whitelist: Optional[List[int]] = None):
        print("Try setting up elm2can bridge")
        print("Creating virtual CAN interface")
        result = os.system("./createvcan.sh")
        if (not os.WIFEXITED(result)) or os.WEXITSTATUS(result) != 0:
            print(f"Calling createvcan.sh failed with error code {os.WEXITSTATUS(result)}")
            sys.exit(-1)

        self._whitelist = whitelist
        elm = serial.Serial()
        elm.baudrate = cfg['baud']
        elm.port = cfg['port']
        elm.timeout = 10
        try:
            elm.open()
        except Exception as e:
            print(f"Could not open elm port, exception {e}")
            sys.exit(-1)

        if not elm.is_open:
            print("elm2canbridge: Can not open serial port")
            sys.exit(-1)

        self._init_elm(elm, cfg['speed'], cfg['canack'])
        # pylint: disable=abstract-class-instantiated
        can_device = can.Bus(channel=canport, interface='socketcan')
        ser_queue: Queue = Queue(QUEUE_MAX_ELEMENTS)

        # mt = threading.Thread(target=self._serial_procesor, args=(ser_queue, can))
        mt = threading.Thread(target=self._serial_procesor, args=(ser_queue, can_device))
        mt.start()

        sr = Process(target=self._serial_reader, args=(elm, ser_queue,))
        sr.start()
        srpid = sr.pid
        print("Running on pid {}".format(srpid))

    def _serial_reader(self, elm: serial.Serial, q: Queue) -> None:
        # No time to loose. Read and stuff into queue
        # using bytearray, reading bigger strides and searching for '\r' gets input overruns in UART
        # so this is the dumbest, fastest way

        buffer = bytearray(64)
        index = 0

        os.nice(-10)
        print("elm2canbridge: Enter monitoring mode...")
        if self._whitelist is not None:
            print("Applying whitelist")
            elm.write(b'STM\r')
            elm.read(4)  # Consume echo
        else:
            print("No filter applied")
            elm.write(b'STMA\r')
            elm.read(5)  # Consume echo

        elm.timeout = None
        CARRIAGE_RETURN = 13
        while True:
            buffer[index] = elm.read()[0]
            # print("Read: {}=={} ".format(buffer[index],CR))
            # print("Buffer {}".format(buffer))
            if buffer[index] == CARRIAGE_RETURN or index == 63:
                # print("Received {}".format(bytes(buffer).hex()[:index]))
                q.put(buffer[:index])  # Todo will slice copy deep enough or is this a race?
                index = 0
                continue
            index += 1

    def _serial_procesor(self, q: Queue, can_device: can.BusABC):
        print("elm2canbridge: Waiting for incoming...")

        while True:
            line = q.get().decode('utf-8')
            # print("Received {}".format(line))

            is_extended_id = False
            # print("Received from elm: {}".format(line))
            try:
                items = line.split()
                if len(items[0]) == 3:  # normal id
                    canid = int(items[0], 16)
                    # print("Normal ID {}".format(canid))
                    del items[0]
                elif len(items) >= 4:  # extended id
                    is_extended_id = True
                    canid = int(items[0] + items[1] + items[2] + items[3], 16)
                    items = items[4:]
                    # print("Extended ID {}".format(canid))
                else:
                    print(
                        "Parseline: Invalid line: {}, len first element: {}, total elements: {}".format(line,
                                                                                                        len(items[0]),
                                                                                                        len(items)))
                    continue

                data = ''.join(items)
                # print("data: {}".format(data))
                data_bytes = bytearray.fromhex(data)
            except Exception:
                # print("Error parsing: " + str(e))
                # print("Error. ELM line, items **{}**".format(line.split()))
                continue

            if len(data_bytes) > 8:
                continue

            if canid > 0x2000000:
                continue

            can_msg = can.Message(arbitration_id=canid, data=data_bytes, is_extended_id=is_extended_id)
            try:
                can_device.send(can_msg)
            except Exception as e:
                print("Error forwarding message to Can ID 0x{:02x} (extended: {}) with data 0x{}".
                      format(canid, is_extended_id, data_bytes.hex()))
                print("Error: {}".format(e))

    def _init_elm(self, elm: serial.Serial, can_speed: int, ack: bool):
        """Currently only works with OBDLink devices"""
        print("Detecting ELM...")
        elm.write(b'\r\r')
        self._wait_for_prompt(elm)
        self._write_to_elm(elm, b'ATI\r')
        resp = self._read_response(elm)
        if not resp.strip().startswith("ELM"):
            print("Unexpected response to ATI: {}".format(resp))
            sys.exit(-1)

        self._wait_for_prompt(elm)
        print("Disable linefeed")
        self._execute_command(elm, b'ATL 0\r')
        print("Enable Headers")
        self._execute_command(elm, b'AT H1\r')
        print("Enable Spaces")
        self._execute_command(elm, b'AT S1\r')
        print("Disable DLC")
        self._execute_command(elm, b'AT D0\r')

        if self._whitelist is not None:
            print("Using Whitelist")
            print("Clear all filters")
            self._execute_command(elm, b'STFAC\r')
            for canid in self._whitelist:
                if canid < 2048:
                    # standard CAN frame IDs are 11 bits long,
                    # so we can safely ignore the 5 most significant bits
                    # of the 16-bit integer representing the ID
                    cmd = "STFPA {:04x}, 07ff\r".format(canid)
                else:
                    # Extended CAN frame IDs are 29 bits long,
                    # so we can safely ignore the 3 MSBs of the
                    # 32-bit integer representing the ID.
                    # We can also ignore the 3 MSBs of the ID which contain
                    # the priority.
                    cmd = "STFPA {:08x}, 03ffffff\r".format(canid)
                print("Exec "+str(cmd))
                self._execute_command(elm, cmd.encode('utf-8'))

        print("Set CAN speed")
        self._execute_command(elm, b'STP 32\r')
        cmd = "STPBR " + str(can_speed) + "\r"
        self._execute_command(elm, cmd.encode('utf-8'))
        self._execute_command(elm, b'STPBRR\r', expectok=False)
        print("Speed is {}".format(can_speed))
        if ack:
            self._execute_command(elm, b'STCMM 1\r')
        else:
            self._execute_command(elm, b'STCMM 0\r')

    def _wait_for_prompt(self, elm):
        while elm.read() != b'>':
            pass

    def _write_to_elm(self, elm, data):
        # print("Write")
        length = len(data)
        elm.write(data)
        echo = elm.read(length)
        if echo != data:
            print("elm2canbridge: Not the same {}/{}".format(data, echo))
        # print("Write Done")

    def _read_response(self, elm):
        response = ""
        while True:
            d = elm.read()
            if d == b'\r':
                return response
            response = response + d.decode('utf-8')
        # print("DEBUG: "+response)

    def _execute_command(self, elm, command, expectok=True):
        self._write_to_elm(elm, command)
        resp = self._read_response(elm)
        if expectok and resp.strip() != "OK":
            print("Invalid response {} for command {}".format(resp, command))
            sys.exit(-1)
        self._wait_for_prompt(elm)
        return resp
