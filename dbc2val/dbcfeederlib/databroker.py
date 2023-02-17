#!/usr/bin/env python3

#################################################################################
# Copyright (c) 2022 Contributors to the Eclipse Foundation
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
from typing import Any
from typing import Optional
from typing import Union

import grpc.aio

import kuksa_client.grpc
from kuksa_client.grpc import Datapoint
from kuksa_client.grpc import DataEntry
from kuksa_client.grpc import DataType
from kuksa_client.grpc import EntryUpdate
from kuksa_client.grpc import Field
from kuksa_client.grpc import Metadata
from kuksa_client.grpc import VSSClient

log = logging.getLogger(__name__)


class Provider:
    def __init__(self, vss_client: VSSClient, grpc_metadata: Optional[grpc.aio.Metadata] = None):
        self._name_to_type : dict[str, DataType]= {}
        self._rpc_kwargs = {'metadata': grpc_metadata}
        log.info("Using %s", self._rpc_kwargs)
        self._vss_client = vss_client

    def check_registered(self, name: str, data_type: Union[str, DataType], description: str) -> bool:
        """
        Check if the signal is registered. If not raise an exception.
        In the future this method may try register signals that are not yet registered.
        The arguments data_type and description are kept for that purpose.
        Returns True if check succeeds.
        """
        if isinstance(data_type, str):
            data_type = getattr(DataType, data_type)
        try:
            log.debug("Checking if signal %s is registered",name)
            metadata = self._vss_client.get_metadata((name,), **self._rpc_kwargs)
            if len(metadata) == 1:
                self._name_to_type[name] = metadata[name].data_type
                log.info(
                    "%s is already registered with type %s",
                    name,
                    metadata[name].data_type.name,
                )
                return True
            log.error("Unexpected metadata response when checking for %s: %s", name, metadata)
        except kuksa_client.grpc.VSSClientError as client_error:
            code = client_error.error.get('code')
            if code == 404:
                log.error("Signal %s is not registered", name)
            else:
                log.error("Error checking registration of %s", name, exc_info=True)
        return False

    def update_datapoint(self, name: str, value: Any):
        updates = (EntryUpdate(DataEntry(
            name,
            value=Datapoint(value=value),
            # Specifying data_type removes the need for the client to query data_type from the server before
            # issuing every set() call.
            metadata=Metadata(data_type=self._name_to_type[name]),
        ), (Field.VALUE,)),)

        self._vss_client.set(updates=updates, **self._rpc_kwargs)
        log.debug("%s => %s", name, value)
