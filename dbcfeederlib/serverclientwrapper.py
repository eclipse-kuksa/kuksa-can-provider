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
from typing import Any, List
import json

from kuksa_client import KuksaClientThread  # type: ignore[import]

from dbcfeederlib import clientwrapper

log = logging.getLogger(__name__)


class ServerClientWrapper(clientwrapper.ClientWrapper):
    def __init__(self, ip: str = "localhost", port: int = 8090,
                 token_path: str = "",
                 tls: bool = True):
        # For WebSocket (KUKSA.val Server) we do not send in token information by default
        # That means in practice that the default defined in kuksa-client will be used
        # (as of today 'jwt/all-read-write.json.token')
        log.debug("Initializing ServerClientWrapper")
        super().__init__(ip, port, token_path, tls)

        # Holder for configs used by kuksa-client
        # for default values
        # see https://github.com/eclipse/kuksa.val/blob/master/kuksa-client/kuksa_client/cli_backend/__init__.py
        self._client_config = {}
        # Set read-only configs, others to be set just before we use config as they may change
        self._client_config["protocol"] = "ws"
        self._kuksa = None

    def _do_init(self):
        log.debug("No additional initialization necessary for KUKSA.val server")

    def start(self):
        """
        Start connection to server and authorize
        """

        # Finalize config
        self._client_config["ip"] = self._ip
        self._client_config["port"] = self._port
        self._client_config["insecure"] = not self._tls
        # Do not set token if it is empty to allow default client lib info to be used
        if self._token_path != "":
            self._client_config["token"] = self._token_path

        if self._root_ca_path:
            self._client_config['cacertificate'] = self._root_ca_path
        if self._tls_server_name:
            self._client_config['tls_server_name'] = self._tls_server_name

        self._kuksa = KuksaClientThread(self._client_config)
        self._kuksa.start()
        self._kuksa.authorize(token_or_tokenfile=self._token_path)

    def is_connected(self) -> bool:
        # This one is quite unreliable, see https://github.com/eclipse/kuksa.val/issues/523
        if self._kuksa is None:
            log.error("is_connected called before client has been started")
            return False
        return self._kuksa.checkConnection()

    def is_signal_defined(self, vss_name: str) -> bool:
        if self._kuksa is None:
            log.error("is_signal_defined called before client has been started")
            return False
        # Check if signal is defined in server
        resp = json.loads(self._kuksa.getMetaData(vss_name))
        if "error" in resp:
            log.error("Signal %s appears not to be registered: %s", vss_name, resp['error'])
            return False
        log.info("Signal %s is registered", vss_name)
        log.debug("Signal %s registration information: %s", vss_name, resp)
        return True

    def update_datapoint(self, name: str, value: Any) -> bool:
        """
        Update datapoint.
        Supported format for value is still a bit unclear/undefined.
        Like an a bool VSS signal both be fed as a Python bool and a string representing json true/false value
        (possibly with correct case)
        """
        if self._kuksa is None:
            log.error("update_datapoint called before client has been started")
            return False
        success = True
        if isinstance(value, bool):
            # For bool KUKSA server expects lower case (true/false) rather than Python case (True/False)
            send_value = json.dumps(value)
        else:
            send_value = str(value)
        tmp_text = self._kuksa.setValue(name, send_value)
        log.debug(f"Got setValue response for {name}:{send_value}:{tmp_text}")
        resp = json.loads(tmp_text)
        if "error" in resp:
            log.error(f"Error sending {name} to kuksa-val-server: {resp['error']}")
            success = False

        return success

    def stop(self):
        log.info("Stopping server client")
        if self._kuksa is not None:
            self._kuksa.stop()
            self._kuksa = None

    def supports_subscription(self) -> bool:
        log.info("Feature not implemented")
        return False

    async def subscribe(self, vss_names: List[str], callback):
        log.error("Feature not implemented")
        return
