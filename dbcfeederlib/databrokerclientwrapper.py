#!/usr/bin/env python3

#################################################################################
# Copyright (c) 2022, 2023 Contributors to the Eclipse Foundation
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
from typing import Any, Dict, List, Optional

import os
import contextlib
from pathlib import Path

import grpc.aio

import kuksa_client.grpc  # type: ignore[import]
from kuksa_client.grpc import Datapoint
from kuksa_client.grpc import DataEntry
from kuksa_client.grpc import DataType
from kuksa_client.grpc import EntryUpdate
from kuksa_client.grpc import Field
from kuksa_client.grpc import Metadata
from kuksa_client.grpc.aio import VSSClient  # type: ignore[import]
from kuksa_client.grpc import SubscribeEntry
from kuksa_client.grpc import View
from dbcfeederlib import clientwrapper

log = logging.getLogger(__name__)


class DatabrokerClientWrapper(clientwrapper.ClientWrapper):
    """
    Client Wrapper using the interface in
    https://github.com/eclipse/kuksa.val/blob/master/kuksa-client/kuksa_client/grpc/__init__.py
    """
    # No default token path given as no default token included in packages/containers
    def __init__(self, ip: str = "127.0.0.1", port: int = 55555,
                 token_path: str = "",
                 tls: bool = False):
        """
        Init Databroker client wrapper, by default with TLS
        """
        super().__init__(ip, port, token_path, tls)
        self._grpc_client = None
        self._name_to_type: Dict[str, DataType] = {}
        self._rpc_kwargs: Dict[str, str] = {}
        self._connected = False
        self._exit_stack = contextlib.ExitStack()
        self._token = ""

    def _do_init(self):
        """
        Set up gRPC metadata for interaction for Databroker.
        """

        if os.environ.get("VEHICLEDATABROKER_DAPR_APP_ID"):
            grpc_metadata = (
                ("dapr-app-id", os.environ.get("VEHICLEDATABROKER_DAPR_APP_ID")),
            )
            self._rpc_kwargs = {'metadata': grpc_metadata}

    def start(self):
        """
        Start connection to databroker and authorize
        """

        log.info(f"Connecting to Data Broker using {self._ip}:{self._port}")

        # For now will just throw a FileNotFoundError if file cannot be found
        # token = ""
        if self._token_path != "":
            log.info(f"Token path specified is {self._token_path}")
            with open(self._token_path, "r") as file:
                self._token = file.read()
            log.debug(f"Token is: {self._token}")
        else:
            log.info("No token path specified. KUKSA.val Databroker must run without authentication!")

        # We do not connect directly when we create VSSClient
        # Instead we provide token first when we do authorize
        # The alternative approach would be to provide token in constructor
        # with/without ensure_startup_connection and not actively call "authorize"
        # The only practical difference is how progress and errors (if any) are reported!

        # If there is a path VSSClient will request a secure connection
        if self._tls and self._root_ca_path:
            root_path = Path(self._root_ca_path)
        else:
            root_path = None

        self._grpc_client = self._exit_stack.enter_context(kuksa_client.grpc.VSSClient(
                 host=self._ip,
                 port=self._port,
                 ensure_startup_connection=False,
                 root_certificates=root_path,
                 tls_server_name=self._tls_server_name
            ))
        self._grpc_client.authorize(token=self._token, **self._rpc_kwargs)
        self._grpc_client.channel.subscribe(
                lambda connectivity: self.on_broker_connectivity_change(connectivity),
                try_to_connect=False,
            )

    def on_broker_connectivity_change(self, connectivity):
        log.info("Connectivity to data broker changed to: %s", connectivity)
        if connectivity in {grpc.ChannelConnectivity.READY, grpc.ChannelConnectivity.IDLE}:
            # Can change between READY and IDLE. Only act if coming from
            # unconnected state
            if not self._connected:
                log.info("Connected to data broker")
                self._connected = True
        else:
            if self._connected:
                log.info("Disconnected from data broker")
            else:
                if connectivity == grpc.ChannelConnectivity.CONNECTING:
                    log.info("Trying to connect to data broker")
            self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def is_signal_defined(self, vss_name: str) -> bool:
        """
        Check if the signal is registered. If not log an error.
        In the future this method may try register signals that are not yet registered.
        The arguments data_type and description are kept for that purpose.
        Returns True if check succeeds.
        """
        if self._grpc_client is None:
            log.warning("is_signal_defined called before client has been started")
            return False
        try:
            log.debug("Checking if signal %s is registered", vss_name)
            metadata = self._grpc_client.get_metadata((vss_name,), **self._rpc_kwargs)
            if len(metadata) == 1:
                self._name_to_type[vss_name] = metadata[vss_name].data_type
                log.info(
                    "%s is already registered with type %s",
                    vss_name,
                    metadata[vss_name].data_type.name,
                )
                return True
            log.error("Unexpected metadata response when checking for %s: %s", vss_name, metadata)
        except kuksa_client.grpc.VSSClientError as client_error:
            code = client_error.error.get('code')
            if code == 404:
                log.error("Signal %s is not registered", vss_name)
            else:
                log.error("Error checking registration of %s", vss_name, exc_info=True)
        return False

    def update_datapoint(self, name: str, value: Any) -> bool:
        """
        Update datapoint.
        Supported format for value is still a bit unclear/undefined.
        Like an a bool VSS signal both be fed as a Python bool and a string representing json true/false value
        (possibly with correct case)
        """
        if self._grpc_client is None:
            log.warning("update_datapoint called before client has been started")
            return False
        try:

            updates = (EntryUpdate(DataEntry(
                name,
                value=Datapoint(value=value),
                # Specifying data_type removes the need for the client to query data_type from the server before
                # issuing every set() call.
                metadata=Metadata(data_type=self._name_to_type[name]),
            ), (Field.VALUE,)),)

            self._grpc_client.set(updates=updates, **self._rpc_kwargs)
            log.debug("%s => %s", name, value)

        except kuksa_client.grpc.VSSClientError:
            log.error(f"Error sending {value} to databroker", exc_info=True)
            return False

        return True

    def stop(self):
        log.info("Stopping databroker client")
        if self._grpc_client is None:
            log.warning("stop called before client has been started")
        else:
            self._exit_stack.close()
            self._grpc_client = None

    def supports_subscription(self) -> bool:
        return True

    async def subscribe(self, vss_names: List[str], callback):
        """Create a subscription and invoke the callback when data received."""
        entries: List[SubscribeEntry] = []
        for name in vss_names:
            # Always subscribe to target
            subscribe_entry = SubscribeEntry(name, View.FIELDS, [Field.ACTUATOR_TARGET])
            log.info("Subscribe entry: %s", subscribe_entry)
            entries.append(subscribe_entry)

        # If there is a path VSSClient will request a secure connection
        if self._tls and self._root_ca_path:
            root_path: Optional[Path] = Path(self._root_ca_path)
        else:
            root_path = None

        async with VSSClient(self._ip, self._port, token=self._token,
                             root_certificates=root_path, tls_server_name=self._tls_server_name) as client:
            async for updates in client.subscribe(entries=entries):
                log.debug(f"Received update of length {len(updates)}")
                await callback(updates)
