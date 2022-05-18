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


import yaml 
import transforms.mapping
import transforms.math


class mapper:

    def __init__(self,input):
        with open(input,'r') as file:
            self.mapping = yaml.full_load(file)

        self.transforms={}
        self.transforms['fullmapping']=transforms.mapping.mapping(discard_non_matching_items=True)
        self.transforms['partialmapping']=transforms.mapping.mapping(discard_non_matching_items=False)
        self.transforms['math']=transforms.math.math()



        for key in self.mapping.keys():
            self.mapping[key]['lastupdate']=0.0
            if 'minupdatedelay' not in self.mapping[key]:
                print("Mapper: No minimal update delay defined for signal {}, setting to 1000ms.".format(key))

    def map(self):
        return self.mapping.items()

    #returns true if element can be updated
    def minUpdateTimeElapsed(self,key, time):
        diff=time - self.mapping[key]['lastupdate']
        #print("Curr update {}, last update {}, diff: {}".format(time, self.mapping[key]['lastupdate'], diff ))
        if diff*1000 >= self.mapping[key]['minupdatedelay']:
            self.mapping[key]['lastupdate']=time
            return True
        return False

    # Check whether there are transforms defined to map DBC signal "signal" to 
    # VSS path "target". Returns the (potentially) transformed values
    def transform(self,signal, target, value):
        if "transform" not in self.mapping[signal]["targets"][target].keys(): #no transform defined, return as is
            return value
        for transform in self.mapping[signal]["targets"][target]["transform"]:
            if transform in self.transforms.keys():  #found a known transform and apply
                value=self.transforms[transform].transform(self.mapping[signal]["targets"][target]["transform"][transform],value)
            else:
                print(f"Warning: Unknown transform {transform} for {signal}->{target}")
        return value

    def __contains__(self,key):
        return key in self.mapping.keys()

    def __getitem__(self, item):
        return self.mapping[item]
    