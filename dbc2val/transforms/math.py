#!/usr/bin/python3

#########################################################################
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

from py_expression_eval import Parser


class math:
    def __init__(self):
        self.parser = Parser()

    def transform(self, spec, value):
        return self.parser.parse(spec).evaluate({"x": value})
