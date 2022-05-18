#!/usr/bin/python3

########################################################################
# Copyright (c) 2021 Robert Bosch GmbH
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


class mapping:

    # setting discard_non_matching_items to true will return "None" if a value
    # is not found in the mapping table. This can be used to only add
    # a subset of possible values to VSS
    # setting discard_non_matching_items to false will return values for
    # which no match exists unmodified
    def __init__(self, discard_non_matching_items):
        self.discard_non_matching_items=discard_non_matching_items

    def transform(self, spec, value):
        for k,v in spec.items():
            if value==k:
                return v
        #no match
        if self.discard_non_matching_items:
            return None
        else:
            return value