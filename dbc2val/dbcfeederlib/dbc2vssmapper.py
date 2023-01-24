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

"""
Classes for maintaining mapping between dbc and VSS
as well as transforming dbc data to VSS data.
"""

import json
import logging
import sys
from typing import Any, Dict, List
from dataclasses import dataclass

from py_expression_eval import Parser

log = logging.getLogger(__name__)

@dataclass
class VSSObservation:
    """
    A VSSObservation is a container for a single observation/data for a single VSS signal.
    The data contained is the raw data as received on CAN, it has not yet been transformed
    into VSS representation.
    """

    dbc_name : str
    vss_name : str
    raw_value : Any
    time : float


class VSSMapping:
    """A mapping for a VSS signal"""

    parser : Parser = Parser()

    def __init__(self, vss_name : str, transform :dict, interval_ms : int,
                 on_change : bool, datatype: str, description : str):
        self.vss_name = vss_name
        self.transform = transform
        self.interval_ms = interval_ms
        self.on_change = on_change
        self.datatype = datatype
        self.description = description
        # For time comparison (interval_ms) we store last value used for comparison. Unit seconds.
        self.last_time : float = 0.0
        # For value comparison (on_changes) we store last value used for comparison
        self.last_vss_value : Any = None

    def time_condition_fulfilled(self, time : float) -> bool:
        """
        Checks if time condition to send signal is fulfilled
        Value (on_change) condition not evaluated
        """
        fulfilled = True
        log.debug(f"Checking interval for {self.vss_name}. "
                  f"Time is {time}, last sent {self.last_time}")

        # First shall always evaluate to true
        if (self.interval_ms > 0) and (self.last_time != 0.0):
            diff_ms =( time - self.last_time) * 1000.0
            if diff_ms < self.interval_ms:
                log.debug(f"Interval not exceeded for {self.vss_name}. Time is {time}")
                fulfilled = False

        # We must set time already now even if a value check is performed later
        # Reason is that value condition is evaluated later after queuing
        if fulfilled:
            self.last_time = time

        return fulfilled

    def change_condition_fulfilled(self, vss_value : Any) -> bool:
        """
        Checks if change condition to send signal is fulfilled.
        Transformation is expected to be costly, so transformation and value check only performed
        if time condition is fulfilled.
        """
        fulfilled = False
        log.debug(f"Checking change condition for {self.vss_name}. "
                  f"New value {vss_value}, old value {self.last_vss_value}")

        if not vss_value is None:
            if self.last_vss_value is None:
                # Always send first value
                fulfilled = True
            elif self.on_change:
                fulfilled = self.last_vss_value != vss_value
            else:
                fulfilled = True

        if fulfilled:
            self.last_vss_value = vss_value
        return fulfilled



    def transform_value(self, value : Any) -> Any:
        """
        Transforms the given "raw" DBC value to the wanted VSS value.
        For now does not make any type checks
        """
        vss_value = None
        if self.transform is None:
            log.debug(f"No mapping to VSS {self.vss_name}, using raw value {value}")
            vss_value = value
        else:
            if "mapping" in self.transform:
                tmp = self.transform["mapping"]
                # Assumed to be a list
                for item in tmp:
                    from_val = item["from"]
                    if from_val == value:
                        new_val = item["to"]
                        vss_value = new_val
                        break
            elif "math" in self.transform:
                tmp = self.transform["math"]
                try:
                    vss_value = VSSMapping.parser.parse(tmp).evaluate({"x": value})
                except Exception:
                    # It is assumed that you may consider it ok that transformation fails sometimes,
                    # so giving warning instead of error
                    # This could be e.g. trying to treat a string as int
                    log.warning(f"Transformation failed for value {value} "
                                f"for VSS signal {self.vss_name}, signal ignored!", exc_info=True)
            else:
                # It is supposed that "extract_verify_transform" already have checked that
                # we have a valid transform, so we shall never end up here
                log.error("Unsupported transform")

        if vss_value is None:
            log.info(f"No mapping to VSS {self.vss_name} found for raw value {value},"
                     f"returning None to indicate that it shall be ignored!")
        else:
            log.debug(f"Transformed value {vss_value} for {self.vss_name}")
        return vss_value


class Mapper:
    """
    The mapper class contain all mappings between dbc and vss.
    It also contain functionality for transforming data
    """

    # Where we keep mapping, key is dbc signal name
    mapping : Dict[str, List[VSSMapping]] = {}

    def transform_value(self, vss_observation : VSSObservation) -> Any:
        """
        Find mapping and transform value.
        """
        # If we have an observation we know that a mapping exists
        vss_signal = self.get_vss_mapping(vss_observation.dbc_name, vss_observation.vss_name)
        value = vss_signal.transform_value(vss_observation.raw_value)
        log.debug(f"Transformed dbc {vss_observation.dbc_name} to VSS "
                  f"{vss_observation.vss_name}, "
                  f"from raw value {vss_observation.raw_value} to {value}")
        return value

    def extract_verify_transform(self, expanded_name : str , node : dict):
        """
        Extracts transformation and checks it seems to be correct
        """
        if not "transform" in node:
            log.debug(f"No transformation found for {expanded_name}")
            # For now assumed that None is Ok
            return None
        transform = node["transform"]

        has_mapping = False

        if not isinstance(transform, dict):
            log.error(f"Transform not dict for {expanded_name}")
            sys.exit(-1)
        if "mapping" in transform:
            tmp = transform["mapping"]
            if not isinstance(tmp, list):
                log.error(f"Transform mapping not list for {expanded_name}")
                sys.exit(-1)
            for item in tmp:
                if not (("from" in item) and ("to" in item)):
                    log.error(f"Mapping missing to and from in {item} for {expanded_name}")
                    sys.exit(-1)
            has_mapping = True

        if "math" in transform:
            if has_mapping:
                log.error(f"Can not have both mapping and math for {expanded_name}")
                sys.exit(-1)
            if not isinstance(transform["math"], str):
                log.error(f"Math must be str for {expanded_name}")
                sys.exit(-1)
        elif not has_mapping:
            log.error(f"Unsupported transform for {expanded_name}")
            sys.exit(-1)
        return transform

    def analyze_signal(self, expanded_name, node):
        """
        Analyzes a signal and add mapping entry if correct mapping found
        """
        if "dbc" in node:
            log.debug(f"Signal {expanded_name} has dbc!")
            dbc_def = node["dbc"]
            transform = self.extract_verify_transform(expanded_name, dbc_def)
            dbc_name = dbc_def.get("signal", "")
            if dbc_name == "":
                log.error(f"No dbc signal found for {expanded_name}")
                sys.exit(-1)
            on_change : bool = False
            if "on_change" in dbc_def:
                tmp = dbc_def["on_change"]
                if isinstance(tmp,bool):
                    on_change = tmp
                else:
                    log.error(f"Value for on_change ({tmp}) is not bool")
                    sys.exit(-1)
            if "interval_ms" in dbc_def:
                interval = dbc_def["interval_ms"]
                if not isinstance(interval,int):
                    log.error(f"Faulty interval for {expanded_name}")
                    sys.exit(-1)
            else:
                if on_change:
                    log.info(f"Using default interval 0 ms for {expanded_name} "
                             f"as it has on_change condition")
                    interval = 0
                else:
                    log.info(f"Using default interval 1000 ms for {expanded_name}")
                    interval = 1000
            mapping_entry = VSSMapping(expanded_name, transform, interval, on_change,
                                       node["datatype"], node["description"])
            if not dbc_name in self.mapping:
                self.mapping[dbc_name] = []
            self.mapping[dbc_name].append(mapping_entry)

    def traverse_vss_node(self,name, node, prefix = ""):
        """
        Traverse a vss node/tree and order all found VSS signals to be analyzed
        so that mapping can be extracted
        """
        is_signal = False
        is_branch = False
        expanded_name = ""
        if isinstance(node,dict):
            if "type" in node:
                if node["type"] in ["sensor","actuator", "attribute"]:
                    is_signal = True
                elif node["type"] in ["branch"]:
                    is_branch = True
                    prefix = prefix + name + "."

        # Assuming it to be a dict
        if is_branch:
            for item in node["children"].items():
                self.traverse_vss_node(item[0],item[1],prefix)
        elif is_signal:
            expanded_name = prefix + name
            self.analyze_signal(expanded_name, node)
        elif isinstance(node,dict):
            for item in node.items():
                self.traverse_vss_node(item[0],item[1],prefix)

    def get_vss_mapping(self, dbc_name : str, vss_name :str) -> VSSMapping:
        """
        Helper method for test purposes
        """
        if dbc_name in self.mapping:
            for mapping in self.mapping[dbc_name]:
                if mapping.vss_name == vss_name:
                    return mapping
        return None


    def __init__(self, filename):
        with open(filename, "r") as file:
            try:
                jsonmapping = json.load(file)
                log.info(f"Reading dbc configurations from {filename}")
            except Exception:
                log.error(f"Failed to read json from {filename}", exc_info=True)
                sys.exit(-1)

        self.traverse_vss_node("",jsonmapping)


    def map(self):
        """ Get access to the map items """
        return self.mapping.items()

    def __contains__(self, key):
        return key in self.mapping

    def __getitem__(self, item):
        return self.mapping[item]
    