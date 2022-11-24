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
        self._name_to_type = {}
        self._rpc_kwargs = {'metadata': grpc_metadata}
        log.info("Using %s", self._rpc_kwargs)
        self._vss_client = vss_client

    def register(self, name: str, data_type: Union[str, DataType], description: str):
        if isinstance(data_type, str):
            data_type = getattr(DataType, data_type)
        try:
            log.debug(
                "register(%s, data_type: %s, '%s')",
                name,
                data_type.name,
                description,
            )
            metadata = self._vss_client.get_metadata((name,), **self._rpc_kwargs)
            if len(metadata) == 1:
                self._name_to_type[name] = metadata[name].data_type
                log.info(
                    "%s was already registered with type %s",
                    name,
                    metadata[name].data_type.name,
                )
                return
        except kuksa_client.grpc.VSSClientError:
            log.debug("Failed to get metadata", exc_info=True)

        self._register(name, data_type, description)

    def _register(self, name: str, data_type: DataType, description: str):
        try:
            self._vss_client.set_metadata(
                updates={name: Metadata(data_type=data_type, description=description)},
                **self._rpc_kwargs,
            )
            # Store datapoint IDs
            self._name_to_type[name] = data_type
            log.info(
                "%s was registered with type %s",
                name,
                data_type.name,
            )
        except kuksa_client.grpc.VSSClientError:
            log.warning("Failed to register datapoint %s", name, exc_info=True)
            raise

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
