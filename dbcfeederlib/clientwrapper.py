#!/usr/bin/env python3

#################################################################################
# Copyright (c) 2023 Contributors to the Eclipse Foundation
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
from typing import Any, List, Optional

from abc import ABC, abstractmethod

log = logging.getLogger(__name__)


class ClientWrapper(ABC):
    """
    Wraps client-specific functionality so that that main dbcfeeder does not need to care about it.
    This acts as a base class, each client (type and/or technology) shall be in a separate file
    This file shall be feeder/provider independent, and can possibly be moved to kuksa.val/kuksa-client
    """
    def __init__(self, ip: str, port: int, token_path: str, tls: bool = True):
        """
        This init method is only supposed to be called by subclassed __init__ functions
        """
        self._ip = ip
        self._port = port
        self._token_path = token_path
        self._tls = tls
        self._registered = False
        self._root_ca_path: Optional[str] = None
        self._tls_server_name: Optional[str] = None
        self._do_init()

    def _do_init(self):
        """
        Perform any implementation specific additional initialization.

        Called at the end of __init__.
        This default implementation does nothing.
        """

    def set_ip(self, ip: str):
        """ Set IP address to use """
        self._ip = ip

    def set_port(self, port: int):
        """ Set port to use """
        self._port = port

    def set_tls(self, tls: bool):
        """
        Set if TLS shall be used (including server auth).
        Currently we rely on default location for root cert as defined by kuksa-client
        """
        self._tls = tls

    def get_tls(self) -> bool:
        """
        Return TLS setting
        """
        return self._tls

    def set_root_ca_path(self, path: str):
        """ Set Path for Root CA (CA.pem) """
        self._root_ca_path = path
        log.info("Using root CA path: %s", self._root_ca_path)

    def set_tls_server_name(self, name: str):
        """ Set Path for Root CA (CA.pem) """
        self._tls_server_name = name
        log.info("Using TLS server name: %s", self._tls_server_name)

    def set_token_path(self, token_path: str):
        self._token_path = token_path
        log.info("Using token from: %s", self._token_path)

    # Abstract methods to implement
    @abstractmethod
    def start(self):
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        pass

    @abstractmethod
    def is_signal_defined(self, vss_name: str) -> bool:
        pass

    @abstractmethod
    def update_datapoint(self, name: str, value: Any) -> bool:
        pass

    @abstractmethod
    def stop(self):
        pass

    @abstractmethod
    def supports_subscription(self) -> bool:
        """Return true if this client supports subscribing to VSS signals"""

    @abstractmethod
    async def subscribe(self, vss_names: List[str], callback):
        """Creates a subscription and calls the callback when data received"""
