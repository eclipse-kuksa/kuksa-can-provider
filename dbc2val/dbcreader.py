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


import can, cantools
import threading

import time

class DBCReader:
    def __init__(self, cfg, rxqueue, mapper):
        self.queue=rxqueue
        self.mapper=mapper
        self.cfg=cfg
        print("Reading dbc file")
        self.db = cantools.database.load_file(cfg['dbcfile'])

        self.canidwl = self.get_whitelist()

        self.parseErr = 0
        self.run = True

    def start_listening(self):
        print("Open CAN device {}".format(self.cfg['port']))
        self.bus = can.interface.Bus(self.cfg['port'], bustype='socketcan')
        rxThread = threading.Thread(target=self.rxWorker)
        rxThread.start()

    def get_whitelist(self):
        print("Collecting signals, generating CAN ID whitelist")
        wl = []
        for entry in self.mapper.map():
            canid=self.get_canid_for_signal(entry[0])
            if canid != None and canid not in wl:
                wl.append(canid)
        return wl

    def get_canid_for_signal(self, sig_to_find):
        for msg in self.db.messages:
            for signal in msg.signals:
                if signal.name == sig_to_find:
                    id = msg.frame_id
                    print("Found signal {} in CAN frame id 0x{:02x}".format(signal.name, id))
                    return id
        print("Signal {} not found in DBC file".format(sig_to_find))
        return None


    def rxWorker(self):
        print("Starting thread")
        while self.run:
            msg=self.bus.recv(timeout=1)
            if msg:
                try:
                    decode=self.db.decode_message(msg.arbitration_id, msg.data)
                    #print("Decod" +str(decode))
                except Exception as e:
                    self.parseErr+=1
                    #print("Error Decoding: "+str(e))
                    continue
                rxTime=time.time()
                for k,v in decode.items():
                    if k in self.mapper:
                        if self.mapper.minUpdateTimeElapsed(k, rxTime):
                            self.queue.put((k,v))


    def stop(self):
        self.run = False



