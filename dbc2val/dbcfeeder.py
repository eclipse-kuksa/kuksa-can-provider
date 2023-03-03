#!/usr/bin/env python

########################################################################
# Copyright (c) 2020,2023 Robert Bosch GmbH
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
Feeder parsing CAN data and sending to KUKSA.val
"""

import argparse
import configparser
import contextlib
import enum
import logging
import os
import queue
import json
import sys
import time
from signal import SIGINT, SIGTERM, signal
from typing import Any
from typing import Dict

import grpc

from kuksa_client import KuksaClientThread
import kuksa_client.grpc

from dbcfeederlib import canplayer
from dbcfeederlib import dbc2vssmapper
from dbcfeederlib import dbcreader
from dbcfeederlib import j1939reader
from dbcfeederlib import databroker
from dbcfeederlib import elm2canbridge

log = logging.getLogger("dbcfeeder")


class ServerType(str, enum.Enum):
    KUKSA_VAL_SERVER = 'kuksa_val_server'
    KUKSA_DATABROKER = 'kuksa_databroker'


def init_logging(loglevel):
    # create console handler and set level to debug
    console_logger = logging.StreamHandler()
    console_logger.setLevel(logging.DEBUG)

    # create formatter
    if sys.stdout.isatty():
        formatter = ColorFormatter()
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s %(levelname)s %(name)s: %(message)s"
        )

    # add formatter to console_logger
    console_logger.setFormatter(formatter)

    # add console_logger as a global handler
    root_logger = logging.getLogger()
    root_logger.setLevel(loglevel)
    root_logger.addHandler(console_logger)


class ColorFormatter(logging.Formatter):
    FORMAT = "{time} {{loglevel}} {logger} {msg}".format(
        time="\x1b[2m%(asctime)s\x1b[0m",  # grey
        logger="\x1b[2m%(name)s:\x1b[0m",  # grey
        msg="%(message)s",
    )
    FORMATS = {
        logging.DEBUG: FORMAT.format(loglevel="\x1b[34mDEBUG\x1b[0m"),  # blue
        logging.INFO: FORMAT.format(loglevel="\x1b[32mINFO\x1b[0m"),  # green
        logging.WARNING: FORMAT.format(loglevel="\x1b[33mWARNING\x1b[0m"),  # yellow
        logging.ERROR: FORMAT.format(loglevel="\x1b[31mERROR\x1b[0m"),  # red
        logging.CRITICAL: FORMAT.format(loglevel="\x1b[31mCRITICAL\x1b[0m"),  # red
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


class Feeder:
    def __init__(self, server_type: ServerType, kuksa_client_config: Dict[str, Any],
                 elmcan_config: Dict[str, Any]):
        self._shutdown = False
        self._reader = None
        self._player = None
        self._mapper = None
        self._provider = None
        self._connected = False
        self._registered = False
        self._can_queue : queue.Queue[dbc2vssmapper.VSSObservation] = queue.Queue()
        self._server_type = server_type
        self._kuksa_client_config = kuksa_client_config
        self._elmcan_config = elmcan_config
        self._exit_stack = contextlib.ExitStack()
        self._disconnect_time = 0.0
        self._kuksa = None

    def start(
        self,
        canport,
        dbcfile,
        mappingfile,
        candumpfile=None,
        use_j1939=False,
        use_strict_parsing=False,
        grpc_metadata=None,
    ):
        log.info("Using mapping: {}".format(mappingfile))
        self._mapper = dbc2vssmapper.Mapper(mappingfile)

        if use_j1939:
            log.info("Using J1939 reader")
            self._reader = j1939reader.J1939Reader(
                rxqueue=self._can_queue,
                dbcfile=dbcfile,
                mapper=self._mapper,
                use_strict_parsing=use_strict_parsing,
            )
        else:
            log.info("Using DBC reader")
            self._reader = dbcreader.DBCReader(
                rxqueue=self._can_queue,
                dbcfile=dbcfile,
                mapper=self._mapper,
                use_strict_parsing=use_strict_parsing,
            )

        if candumpfile:
            # use dumpfile
            log.info(
                "Using virtual bus to replay CAN messages (channel: %s)",
                canport,
            )
            self._reader.start_listening(
                bustype="virtual",
                channel=canport,
                bitrate=500000
            )
            self._player = canplayer.CANplayer(dumpfile=candumpfile)
            self._player.start_replaying(canport=canport)
        else:

            if canport == 'elmcan':

                log.info("Using elmcan. Trying to set up elm2can bridge")
                elm2canbridge.elm2canbridge(canport, self._elmcan_config, self._reader.canidwl)

            # use socketCAN
            log.info("Using socket CAN device '%s'", canport)
            self._reader.start_listening(bustype="socketcan", channel=canport)

        if self._server_type is ServerType.KUKSA_DATABROKER:
            databroker_address = f"{self._kuksa_client_config['ip']}:{self._kuksa_client_config['port']}"
            log.info("Connecting to Data Broker using %s", databroker_address)
            vss_client = self._exit_stack.enter_context(kuksa_client.grpc.VSSClient(
                host=self._kuksa_client_config['ip'],
                port=self._kuksa_client_config['port'],
            ))
            vss_client.channel.subscribe(
                lambda connectivity: self.on_broker_connectivity_change(connectivity),
                try_to_connect=False,
            )
            self._provider = databroker.Provider(vss_client, grpc_metadata)
        else:
            log.info("Will use kuksa-val-server")
        self._run()

    def stop(self):
        log.info("Shutting down...")
        self._shutdown = True
        # Tell others to stop
        if self._reader is not None:
            self._reader.stop()
        if self._player is not None:
            self._player.stop()
        if self._kuksa is not None:
            self._kuksa.stop()

        self._exit_stack.close()

    def is_stopping(self):
        return self._shutdown

    def on_broker_connectivity_change(self, connectivity):
        log.info("Connectivity to data broker changed to: %s", connectivity)
        if (
            connectivity == grpc.ChannelConnectivity.READY or
            connectivity == grpc.ChannelConnectivity.IDLE
        ):
            # Can change between READY and IDLE. Only act if coming from
            # unconnected state
            if not self._connected:
                log.info("Connected to data broker")
                self._connected = True
                self._disconnect_time = 0.0
        else:
            if self._connected:
                log.info("Disconnected from data broker")
            else:
                if connectivity == grpc.ChannelConnectivity.CONNECTING:
                    log.info("Trying to connect to data broker")
            self._connected = False
            self._registered = False

    def _register_datapoints(self) -> bool:
        """
        Check that data points are registered.
        May in the future also register missing datapoints.
        Returns True on success.
        """
        log.info("Check that datapoints are registered")
        all_registered = True
        for entry in self._mapper.mapping.values():
            for vss_mapping in entry:
                #for target_name, target_attr in self._mapper.mapping[entry]["targets"].items():
                registered = self._provider.check_registered(
                    vss_mapping.vss_name,
                    vss_mapping.datatype.upper(),
                    vss_mapping.description,
                )
                if not registered:
                    all_registered = False
        return all_registered

    def _run(self):
        if self._server_type is ServerType.KUKSA_VAL_SERVER:
            self._kuksa = KuksaClientThread(self._kuksa_client_config)
            self._kuksa.start()
            self._kuksa.authorize()

        processing_started = False
        messages_sent = 0
        last_sent_log_entry = 0
        queue_max_size = 0
        while self._shutdown is False:
            if self._server_type is ServerType.KUKSA_DATABROKER:
                if not self._connected:
                    sleep_time = 0.2
                    time.sleep(sleep_time)
                    self._disconnect_time += sleep_time
                    if self._disconnect_time > 5:
                        log.info("Databroker still not connected!")
                        self._disconnect_time = 0.0
                    continue
                if not self._registered:
                    time.sleep(1)
                    if not self._register_datapoints():
                        log.error("Not all datapoints registered, exiting!")
                        self.stop()
                        continue
                    self._registered = True
            try:
                if not processing_started:
                    processing_started = True
                    log.info("Starting to process CAN signals")
                queue_size = self._can_queue.qsize()
                if queue_size > queue_max_size:
                    queue_max_size = queue_size
                vss_observation = self._can_queue.get(timeout=1)
                vss_mapping = self._mapper.get_vss_mapping(vss_observation.dbc_name, vss_observation.vss_name)
                value = vss_mapping.transform_value(vss_observation.raw_value)
                if value is None:
                    log.warning(f"Value ignored for  dbc {vss_observation.dbc_name} to VSS {vss_observation.vss_name},"
                                f" from raw value {value} of type {type(value)}")
                elif not vss_mapping.change_condition_fulfilled(value):
                    log.debug(f"Value condition not fulfilled for VSS {vss_observation.vss_name}, value {value}")
                else:
                    # get values out of the canreplay and map to desired signals
                    target = vss_observation.vss_name
                    success = True
                    if self._server_type is ServerType.KUKSA_DATABROKER:
                        try:
                            self._provider.update_datapoint(target, value)
                        except kuksa_client.grpc.VSSClientError:
                            log.error(f"Error sending {target} to databroker", exc_info=True)
                            success = False
                    else:
                        # KUKSA server expects a string value without quotes
                        if isinstance(value,bool):
                            # For bool KUKSA server expects lower case (true/false) rather than Python case (True/False)
                            send_value = json.dumps(value)
                        else:
                            send_value = str(value)
                        resp = json.loads(self._kuksa.setValue(target, send_value))
                        if "error" in resp:
                            log.error(f"Error sending {target} to kuksa-val-server: {resp['error']}")
                            success = False
                    if success:
                        log.debug("Succeeded sending DataPoint(%s, %s, %f)", target, value,vss_observation.time)
                        # Give status message after 1, 2, 4, 8, 16, 32, 64, .... messages have been sent
                        messages_sent += 1
                        if messages_sent >= (2 * last_sent_log_entry):
                            log.info(f"Number of VSS messages sent so far: {messages_sent}, "
                                     f"queue max size: {queue_max_size}")
                            last_sent_log_entry = messages_sent
            except queue.Empty:
                pass
            except Exception:
                log.error("Exception caught in main loop", exc_info=True)


def parse_config(filename):
    configfile = None

    if filename:
        if not os.path.exists(filename):
            log.warning("Couldn't find config file {}".format(filename))
            raise Exception("Couldn't find config file {}".format(filename))
        configfile = filename
    else:
        config_candidates = [
            "/config/dbc_feeder.ini",
            "/etc/dbc_feeder.ini",
            "config/dbc_feeder.ini",
        ]
        for candidate in config_candidates:
            if os.path.isfile(candidate):
                configfile = candidate
                break

    log.info("Using config: {}".format(configfile))
    if configfile is None:
        return {}

    config = configparser.ConfigParser()
    readed = config.read(configfile)
    if log.level >= logging.DEBUG:
        log.debug(
            "# config.read({}):\n{}".format(
                readed,
                {section: dict(config[section]) for section in config.sections()},
            )
        )

    return config

def main(argv):
    # argument support
    parser = argparse.ArgumentParser(description="dbcfeeder")
    parser.add_argument("--config", metavar="FILE", help="Configuration file")
    parser.add_argument(
        "--dbcfile", metavar="FILE", help="DBC file used for parsing CAN traffic"
    )
    parser.add_argument(
        "--dumpfile", metavar="FILE", help="Replay recorded CAN traffic from dumpfile"
    )
    parser.add_argument("--canport", metavar="DEVICE", help="Read from this CAN device")
    parser.add_argument("--use-j1939", action="store_true", help="Use J1939")

    parser.add_argument(
        "--use-socketcan",
        action="store_true",
        help="Use SocketCAN (overriding any use of --dumpfile)",
    )
    parser.add_argument(
        "--mapping",
        metavar="FILE",
        help="Mapping file used to map CAN signals to databroker datapoints",
    )
    parser.add_argument(
        "--server-type",
        help="Which type of server the feeder should connect to",
        choices=[server_type.value for server_type in ServerType],
        type=ServerType,
    )
    parser.add_argument(
        "--lax-dbc-parsing",
        dest="strict",
        help="""
          Disable strict parsing of DBC files. This is helpful if the DBC file contains
          message length definitions that do not match the signals' bit-offsets and lengths.
          Processing DBC frames based on such DBC message definitions might still work, so
          providing this switch might allow using the (erroneous) DBC file without having to
          fix it first.
          """,
        action="store_false",
    )
    args = parser.parse_args()

    config = parse_config(args.config)

    if args.server_type:
        server_type = args.server_type
    elif os.environ.get("SERVER_TYPE"):
        server_type = ServerType(os.environ.get("SERVER_TYPE"))
    elif "general" in config and "server_type" in config["general"]:
        server_type = ServerType(config["general"]["server_type"])
    else:
        server_type = ServerType.KUKSA_VAL_SERVER

    if server_type is ServerType.KUKSA_VAL_SERVER:
        config.setdefault("kuksa_val_server", {})
        config["kuksa_val_server"].setdefault("ip", "localhost")
        config["kuksa_val_server"].setdefault("port", "8090")
        config["kuksa_val_server"].setdefault("protocol", "ws")
        config["kuksa_val_server"].setdefault("insecure", "False")
        kuksa_client_config = config["kuksa_val_server"]
    elif server_type is ServerType.KUKSA_DATABROKER:
        config.setdefault("kuksa_databroker", {})
        config["kuksa_databroker"].setdefault("ip", "127.0.0.1")
        config["kuksa_databroker"].setdefault("port", "55555")
        config["kuksa_databroker"].setdefault("protocol", "grpc")
        config["kuksa_databroker"].setdefault("insecure", "True")
        kuksa_client_config = config["kuksa_databroker"]

        if os.environ.get("DAPR_GRPC_PORT"):
            kuksa_client_config["ip"] = "127.0.0.1"
            kuksa_client_config["port"] = os.environ.get("DAPR_GRPC_PORT")
        elif os.environ.get("VDB_ADDRESS"):
            vdb_address, vdb_port = os.environ.get("VDB_ADDRESS").split(':', maxsplit=1)
            kuksa_client_config["ip"] = vdb_address
            kuksa_client_config["port"] = vdb_port
    else:
        raise ValueError(f"Unsupported server type: {server_type}")

    if args.mapping:
        mappingfile = args.mapping
    elif os.environ.get("MAPPING_FILE"):
        mappingfile = os.environ.get("MAPPING_FILE")
    elif "general" in config and "mapping" in config["general"]:
        mappingfile = config["general"]["mapping"]
    else:
        mappingfile = "mapping/vss_3.1.1/vss_dbc.json"

    if args.canport:
        canport = args.canport
    elif os.environ.get("CAN_PORT"):
        canport = os.environ.get("CAN_PORT")
    elif "can" in config and "port" in config["can"]:
        canport = config["can"]["port"]
    else:
        parser.print_help()
        print("ERROR:\nNo CAN port specified")
        return -1

    if args.use_j1939:
        use_j1939 = True
    elif os.environ.get("USE_J1939"):
        use_j1939 = os.environ.get("USE_J1939") == "1"
    elif "can" in config:
        use_j1939 = config["can"].getboolean("j1939", False)
    else:
        use_j1939 = False

    if args.dbcfile:
        dbcfile = args.dbcfile
    elif os.environ.get("DBC_FILE"):
        dbcfile = os.environ.get("DBC_FILE")
    elif "can" in config and "dbcfile" in config["can"]:
        dbcfile = config["can"]["dbcfile"]
    else:
        dbcfile = None

    if not dbcfile and not use_j1939:
        parser.print_help()
        print("\nERROR:\nNeither DBC file nor the use of J1939 specified")
        return -1

    candumpfile = None
    if not args.use_socketcan:
        if args.dumpfile:
            candumpfile = args.dumpfile
        elif os.environ.get("CANDUMP_FILE"):
            candumpfile = os.environ.get("CANDUMP_FILE")
        elif "can" in config and "candumpfile" in config["can"]:
            candumpfile = config["can"]["candumpfile"]

    if os.environ.get("VEHICLEDATABROKER_DAPR_APP_ID"):
        grpc_metadata = (
            ("dapr-app-id", os.environ.get("VEHICLEDATABROKER_DAPR_APP_ID")),
        )
    else:
        grpc_metadata = None

    elmcan_config = []
    if canport == "elmcan":
        if candumpfile != None:
            log.error("It is a contradiction specifying both elmcan and candumpfile!")
            sys.exit(-1)
        if not "elmcan" in config:
            log.error("Cannot use elmcan without elmcan config!")
            sys.exit(-1)
        elmcan_config = config["elmcan"]

    feeder = Feeder(server_type, kuksa_client_config, elmcan_config)

    def signal_handler(signal_received, frame):
        log.info(f"Received signal {signal_received}, stopping...")

        # If we get told to shutdown a second time. Just do it.
        if feeder.is_stopping():
            log.warning("Shutdown now!")
            sys.exit(-1)

        feeder.stop()

    signal(SIGINT, signal_handler)
    signal(SIGTERM, signal_handler)

    log.info("Starting CAN feeder")
    feeder.start(
        canport=canport,
        dbcfile=dbcfile,
        mappingfile=mappingfile,
        candumpfile=candumpfile,
        use_j1939=use_j1939,
        use_strict_parsing=args.strict,
        grpc_metadata=grpc_metadata,
    )

    return 0


def parse_env_log(env_log, default=logging.INFO):
    def parse_level(level, default=default):
        if type(level) is str:
            if level.lower() in [
                "debug",
                "info",
                "warn",
                "warning",
                "error",
                "critical",
            ]:
                return level.upper()
            else:
                raise Exception(f"could not parse '{level}' as a log level")
        return default

    loglevels = {}

    if env_log is not None:
        log_specs = env_log.split(",")
        for log_spec in log_specs:
            spec_parts = log_spec.split("=")
            if len(spec_parts) == 1:
                # This is a root level spec
                if "root" in loglevels:
                    raise Exception("multiple root loglevels specified")
                else:
                    loglevels["root"] = parse_level(spec_parts[0])
            if len(spec_parts) == 2:
                logger = spec_parts[0]
                level = spec_parts[1]
                loglevels[logger] = parse_level(level)

    if "root" not in loglevels:
        loglevels["root"] = default

    return loglevels


if __name__ == "__main__":
    # Example
    #
    # Set log level to debug
    #   LOG_LEVEL=debug ./dbcfeeder.py
    #
    # Set log level to INFO, but for dbcfeeder.broker set it to DEBUG
    #   LOG_LEVEL=info,dbcfeeder.broker_client=debug ./dbcfeeder.py
    #
    # Other available loggers:
    #   dbcfeeder
    #   dbcfeeder.broker_client
    #   databroker (useful for feeding values debug)
    #   dbcreader
    #   dbcmapper
    #   can
    #   j1939
    #

    loglevels = parse_env_log(os.environ.get("LOG_LEVEL"))

    # set root loglevel etc
    init_logging(loglevels["root"])

    # helper for debugging in vs code from project root
    # os.chdir(os.path.dirname(__file__))

    # set loglevels for other loggers
    for logger, level in loglevels.items():
        if logger != "root":
            logging.getLogger(logger).setLevel(level)

    sys.exit(main(sys.argv))
