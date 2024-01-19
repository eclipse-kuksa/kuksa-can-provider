#!/usr/bin/env python

########################################################################
# Copyright (c) 2020,2023 Contributors to the Eclipse Foundation
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
import asyncio
import configparser
import enum
import errno
import logging
import os
import queue
import sys
import threading
import time

from signal import SIGINT, SIGTERM, signal
from typing import Any, Dict, List, Optional, Set

from cantools.database import Message
from kuksa_client.grpc import EntryUpdate  # type: ignore

from dbcfeederlib.canclient import CANClient
from dbcfeederlib.canreader import CanReader
from dbcfeederlib import dbc2vssmapper
from dbcfeederlib import dbcreader
from dbcfeederlib import j1939reader
from dbcfeederlib import databrokerclientwrapper
from dbcfeederlib import serverclientwrapper
from dbcfeederlib import clientwrapper
from dbcfeederlib import elm2canbridge

log = logging.getLogger("dbcfeeder")

CONFIG_SECTION_CAN = "can"
CONFIG_SECTION_ELMCAN = "elmcan"
CONFIG_SECTION_GENERAL = "general"

CONFIG_OPTION_CAN_DUMP_FILE = "candumpfile"
CONFIG_OPTION_DBC_DEFAULT_FILE = "dbc_default_file"
CONFIG_OPTION_IP = "ip"
CONFIG_OPTION_J1939 = "j1939"
CONFIG_OPTION_MAPPING = "mapping"
CONFIG_OPTION_PORT = "port"
CONFIG_OPTION_ROOT_CA_PATH = "root_ca_path"
CONFIG_OPTION_TLS_ENABLED = "tls"
CONFIG_OPTION_TLS_SERVER_NAME = "tls_server_name"
CONFIG_OPTION_TOKEN = "token"


class ServerType(str, enum.Enum):
    """Enum class to indicate type of server dbcfeeder is connecting to"""
    KUKSA_VAL_SERVER = 'kuksa_val_server'
    KUKSA_DATABROKER = 'kuksa_databroker'


def init_logging(loglevel):
    """Set up console logger"""
    # create console handler and set level to debug. This just means that it can show DEBUG messages.
    # What actually is shown is controlled by logging configuration
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
    """Color formatter that can be used for terminals"""
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
    """
    The feeder is responsible for setting up a queue.
    It will get a mapping config as input (in start) and will then:
    Start a DBCReader that extracts interesting CAN messages and adds to the queue.
    Start a CANplayer if you run with a CAN dump file as input.
    Start listening to the queue and transform CAN messages to VSS data and if conditions
    are fulfilled send them to the client wrapper which in turn send it to the bckend supported by the wrapper.
    """

    def __init__(self, kuksa_client: clientwrapper.ClientWrapper,
                 elmcan_config: Dict[str, Any], dbc2vss: bool = True, vss2dbc: bool = False):
        self._running: bool = False
        self._reader: Optional[CanReader] = None
        self._mapper: Optional[dbc2vssmapper.Mapper] = None
        self._registered: bool = False
        self._dbc2vss_queue: queue.Queue[dbc2vssmapper.VSSObservation] = queue.Queue()
        self._kuksa_client = kuksa_client
        self._elmcan_config = elmcan_config
        self._disconnect_time = 0.0
        self._dbc2vss_enabled = dbc2vss
        self._vss2dbc_enabled = vss2dbc
        self._canclient: Optional[CANClient] = None
        self._transmit: bool = False

    def start(
        self,
        canport: str,
        can_fd: bool,
        dbc_file_names: List[str],
        mappingfile: str,
        dbc_default_file: Optional[str],
        candumpfile: Optional[str],
        use_j1939: bool = False,
        use_strict_parsing: bool = False
    ):

        self._running = True
        self._mapper = dbc2vssmapper.Mapper(
            mapping_definitions_file=mappingfile,
            dbc_file_names=dbc_file_names,
            use_strict_parsing=use_strict_parsing,
            expect_extended_frame_ids=use_j1939,
            can_signal_default_values_file=dbc_default_file)

        self._kuksa_client.start()
        threads = []

        if not self._dbc2vss_enabled:
            log.info("Mapping of CAN signals to VSS Data Entries is disabled.")
        elif not self._mapper.has_dbc2vss_mapping():
            log.info("No mappings from CAN signals to VSS Data Entries defined.")
        else:
            log.info("Setting up reception of CAN signals")
            if use_j1939:
                log.info("Using J1939 reader")
                self._reader = j1939reader.J1939Reader(self._dbc2vss_queue, self._mapper, canport, candumpfile)
            else:
                log.info("Using DBC reader")
                self._reader = dbcreader.DBCReader(self._dbc2vss_queue, self._mapper, canport, can_fd, candumpfile)

            if canport == 'elmcan':
                log.info("Using elmcan. Trying to set up elm2can bridge")
                whitelisted_frame_ids: List[int] = []
                for filter in self._mapper.can_frame_id_whitelist():
                    whitelisted_frame_ids.append(filter.can_id)  # type: ignore
                elm2canbridge.elm2canbridge(canport, self._elmcan_config, whitelisted_frame_ids)

            self._reader.start()

            receiver = threading.Thread(target=self._run_receiver)
            receiver.start()
            threads.append(receiver)

        if not self._vss2dbc_enabled:
            log.info("Mapping of VSS Data Entries to CAN signals is disabled.")
        elif not self._mapper.has_vss2dbc_mapping():
            log.info("No mappings from VSS Data Entries to CAN signals defined.")
        elif not self._kuksa_client.supports_subscription():
            log.error(
                "The configured kuksa.val client [%s] does not support subscribing to VSS Data Entry changes!",
                type(self._kuksa_client)
            )
            self.stop()
        else:
            log.info("Starting thread for processing VSS Data Entry changes, writing to CAN device %s", canport)
            # For now creating another bus
            # Maybe support different buses for downstream/upstream in the future

            self._canclient = CANClient(interface="socketcan", channel=canport, can_fd=can_fd)

            transmitter = threading.Thread(target=self._run_transmitter)
            transmitter.start()
            threads.append(transmitter)

        # Wait for all of them to finish
        for thread in threads:
            thread.join()

    def stop(self):
        log.info("Shutting down...")
        self._running = False
        # Tell others to stop
        if self._reader is not None:
            self._reader.stop()
        self._kuksa_client.stop()
        if self._canclient:
            self._canclient.stop()
        self._transmit = False

    def is_running(self) -> bool:
        return self._running

    def _register_datapoints(self) -> bool:
        """
        Check that data points are registered.
        May in the future also register missing datapoints.
        Returns True on success.
        """
        log.info("Check that datapoints are registered")
        if self._mapper is None:
            log.error("_register_datapoints called before feeder has been started")
            return False
        all_registered = True
        for vss_name in self._mapper.get_vss_names():
            log.debug("Checking if signal %s is registered", vss_name)
            resp = self._kuksa_client.is_signal_defined(vss_name)
            if not resp:
                all_registered = False
        return all_registered

    def _run_receiver(self):
        processing_started = False
        messages_sent = 0
        last_sent_log_entry = 0
        queue_max_size = 0
        while self._running is True:
            if self._kuksa_client.is_connected():
                self._disconnect_time = 0.0
            else:
                # As we actually cannot register
                self._registered = False
                sleep_time = 0.2
                time.sleep(sleep_time)
                self._disconnect_time += sleep_time
                if self._disconnect_time > 5:
                    log.info("Server/Databroker still not connected!")
                    self._disconnect_time = 0.0
                continue
            if not self._registered:
                if not self._register_datapoints():
                    log.error("Not all datapoints registered, exiting!")
                    self.stop()
                    continue
                self._registered = True
            try:
                if not processing_started:
                    processing_started = True
                    log.info("Starting to process CAN signals")
                queue_size = self._dbc2vss_queue.qsize()
                if queue_size > queue_max_size:
                    queue_max_size = queue_size
                vss_observation = self._dbc2vss_queue.get(timeout=1)
                vss_mapping = self._mapper.get_dbc2vss_mapping(vss_observation.dbc_name, vss_observation.vss_name)
                value = vss_mapping.transform_value(vss_observation.raw_value)
                if value is None:
                    log.warning(
                        "Value ignored for dbc %s to VSS %s, from raw value %s of type %s",
                        vss_observation.dbc_name, vss_observation.vss_name, value, type(value)
                    )
                elif not vss_mapping.change_condition_fulfilled(value):
                    log.debug("Value condition not fulfilled for VSS %s, value %s", vss_observation.vss_name, value)
                else:
                    # update current value in KUKSA.val
                    target = vss_observation.vss_name

                    success = self._kuksa_client.update_datapoint(target, value)
                    if success:
                        log.debug("Succeeded sending DataPoint(%s, %s, %f)", target, value, vss_observation.time)
                        # Give status message after 1, 2, 4, 8, 16, 32, 64, .... messages have been sent
                        messages_sent += 1
                        if messages_sent >= (2 * last_sent_log_entry):
                            log.info(
                                """
                                Update datapoint requests sent to kuksa.val so far: %d,
                                maximum number of queued CAN messages so far: %d
                                """,
                                messages_sent, queue_max_size
                            )
                            last_sent_log_entry = messages_sent
            except queue.Empty:
                pass
            except Exception:
                log.error("Exception caught in main loop", exc_info=True)

    async def _vss_update(self, updates: List[EntryUpdate]):
        if self._mapper is None:
            # this should not happen because we always create a mapper
            log.warning("Ignoring updated VSS Data Entries, no mapping information available")
        elif self._canclient is None:
            # this should not happen because we always create a CAN client
            log.warning("Ignoring updated VSS Data Entries, no CAN bus client available")
        else:
            log.debug("Processing %d VSS Data Entry updates", len(updates))
            dbc_signal_names: Set[str] = set()
            for update in updates:
                if update.entry.value is not None:
                    # This should never happen as we do not subscribe to current value
                    log.warning(
                        "Current value for %s is now: %s of type %s",
                        update.entry.path, update.entry.value.value, type(update.entry.value.value)
                    )

                if update.entry.actuator_target is not None:
                    log.debug(
                        "Target value for %s is now: %s of type %s",
                        update.entry.path, update.entry.actuator_target, type(update.entry.actuator_target.value)
                    )
                    affected_signals = self._mapper.handle_update(update.entry.path, update.entry.actuator_target.value)
                    dbc_signal_names.update(affected_signals)

            messages_to_send: Set[Message] = set()
            for signal_name in dbc_signal_names:
                messages_to_send.update(self._mapper.get_messages_for_signal(signal_name))

            for message_definition in messages_to_send:
                log.debug(
                    "sending CAN message %s with frame ID %#x",
                    message_definition.name, message_definition.frame_id
                )
                sig_dict = self._mapper.get_value_dict(message_definition.frame_id)
                data = message_definition.encode(sig_dict)
                self._canclient.send(arbitration_id=message_definition.frame_id, data=data)

    async def _run_subscribe(self):
        """
        Requests the client wrapper to start subscription.
        Checks every second if we have requested to stop reception and if so exits
        """
        asyncio.create_task(self._kuksa_client.subscribe(self._mapper.get_vss2dbc_entries(), self._vss_update))
        while self._transmit:
            await asyncio.sleep(1)

    def _run_transmitter(self):
        """
        Starts subscription to selected VSS signals and on updates transmit to CAN
        """
        self._transmit = True
        asyncio.run(self._run_subscribe())


def _parse_config(filename: str) -> configparser.ConfigParser:
    configfile = None

    if filename:
        if not os.path.exists(filename):
            log.warning("Couldn't find config file %s", filename)
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), filename)
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

    config = configparser.ConfigParser()
    log.info("Reading configuration from file: %s", configfile)
    if configfile:
        readed = config.read(configfile)
        if log.isEnabledFor(logging.DEBUG):
            log.debug("using configuration (%s):\n%s", readed, config)

    return config


def _get_kuksa_val_client(command_line_parser: argparse.Namespace,
                          config: configparser.ConfigParser) -> clientwrapper.ClientWrapper:

    if command_line_parser.server_type:
        server_type_name = command_line_parser.server_type
    elif os.environ.get("SERVER_TYPE"):
        server_type_name = os.environ.get("SERVER_TYPE")
    else:
        server_type_name = config.get(CONFIG_SECTION_GENERAL, "server_type", fallback=ServerType.KUKSA_VAL_SERVER.name)

    server_type = ServerType(server_type_name)

    # The wrappers contain default settings, so we only need to change settings
    # if given by dbcfeeder configs/arguments/env-variables
    if server_type is ServerType.KUKSA_VAL_SERVER:
        client: clientwrapper.ClientWrapper = serverclientwrapper.ServerClientWrapper()
    elif server_type is ServerType.KUKSA_DATABROKER:
        client = databrokerclientwrapper.DatabrokerClientWrapper()
    else:
        raise ValueError(f"Unsupported server type: {server_type}")

    kuksa_ip = os.environ.get("KUKSA_ADDRESS")
    if kuksa_ip is not None:
        client.set_ip(kuksa_ip)
    elif config.has_option(CONFIG_SECTION_GENERAL, CONFIG_OPTION_IP):
        client.set_ip(config.get(CONFIG_SECTION_GENERAL, CONFIG_OPTION_IP))

    kuksa_port = os.environ.get("KUKSA_PORT")
    if kuksa_port is not None:
        client.set_port(int(kuksa_port))
    elif config.has_option(CONFIG_SECTION_GENERAL, CONFIG_OPTION_PORT):
        client.set_port(config.getint(CONFIG_SECTION_GENERAL, CONFIG_OPTION_PORT))

    if config.has_option(CONFIG_SECTION_GENERAL, CONFIG_OPTION_TLS_ENABLED):
        client.set_tls(config.getboolean(CONFIG_SECTION_GENERAL, CONFIG_OPTION_TLS_ENABLED, fallback=False))

    if config.has_option(CONFIG_SECTION_GENERAL, CONFIG_OPTION_ROOT_CA_PATH):
        path = config.get(CONFIG_SECTION_GENERAL, CONFIG_OPTION_ROOT_CA_PATH)
        client.set_root_ca_path(path)
    elif client.get_tls():
        # We do not want to rely on kuksa-client default
        log.error("Root CA must be given when using TLS")

    if config.has_option(CONFIG_SECTION_GENERAL, CONFIG_OPTION_TLS_SERVER_NAME):
        name = config.get(CONFIG_SECTION_GENERAL, CONFIG_OPTION_TLS_SERVER_NAME)
        client.set_tls_server_name(name)

    if config.has_option(CONFIG_SECTION_GENERAL, CONFIG_OPTION_TOKEN):
        token_path = config.get(CONFIG_SECTION_GENERAL, CONFIG_OPTION_TOKEN)
        client.set_token_path(token_path)
    else:
        log.info("Path to token information not given")

    return client


def _get_command_line_args_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="dbcfeeder")
    parser.add_argument("--config", metavar="FILE", help="The file to read configuration properties from")
    parser.add_argument(
        "--dbcfile", metavar="FILE", help="A (comma sparated) list of DBC files to read message definitions from."
    )
    parser.add_argument(
        "--dumpfile", metavar="FILE", help="Replay recorded CAN traffic from dumpfile"
    )
    parser.add_argument("--canport", metavar="DEVICE", help="The name of the device representing the CAN bus")
    parser.add_argument("--use-j1939", action="store_true", help="Use j1939 messages on the CAN bus")

    parser.add_argument(
        "--use-socketcan",
        action="store_true",
        help="Use SocketCAN (overriding any use of --dumpfile)",
    )
    parser.add_argument(
        '--canfd',
        action='store_true',
        help="Open bus interface in CAN-FD mode"
    )
    parser.add_argument(
        "--mapping",
        metavar="FILE",
        help="The file to read definitions for mapping CAN signals to VSS datapoints from",
    )
    parser.add_argument(
        "--dbc-default",
        metavar="FILE",
        help="A file containing default values for DBC signals. Needed for all CAN signals used if using val2dbc",
    )
    parser.add_argument(
        "--server-type",
        help="The type of KUKSA.val server to write/read VSS signal to/from",
        choices=[server_type.value for server_type in ServerType]
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
    # By default we work as bidirectional provider
    parser.add_argument('--dbc2val', action='store_true',
                        help="Monitor CAN and send mapped signals to KUKSA.val")
    parser.add_argument('--no-dbc2val', action='store_true',
                        help="Do not monitor signals on CAN")
    # By default we disable sending to CAN, for backward compatibility
    parser.add_argument('--val2dbc', action='store_true',
                        help="Monitor mapped signals in KUKSA.val and send to CAN")
    parser.add_argument('--no-val2dbc', action='store_true',
                        help="Do not monitor mapped signals in KUKSA.val")

    return parser


def main(argv):
    """Main entrypoint for dbcfeeder"""
    parser = _get_command_line_args_parser()
    args = parser.parse_args()
    config = _parse_config(args.config)

    if args.dbc2val:
        use_dbc2val = True
    elif args.no_dbc2val:
        use_dbc2val = False
    elif os.environ.get("USE_DBC2VAL"):
        use_dbc2val = True
    elif os.environ.get("NO_USE_DBC2VAL"):
        use_dbc2val = False
    else:
        # By default enabled
        use_dbc2val = config.getboolean(CONFIG_SECTION_GENERAL, "dbc2val", fallback=True)
    log.info("DBC2VAL mode is: %s", use_dbc2val)

    if args.val2dbc:
        use_val2dbc = True
    elif args.no_val2dbc:
        use_val2dbc = False
    elif os.environ.get("USE_VAL2DBC"):
        use_val2dbc = True
    elif os.environ.get("NO_USE_VAL2DBC"):
        use_val2dbc = False
    else:
        # By default disabled
        use_val2dbc = config.getboolean(CONFIG_SECTION_GENERAL, "val2dbc", fallback=False)
    log.info("VAL2DBC mode is: %s", use_val2dbc)

    if not (use_dbc2val or use_val2dbc):
        parser.error("Either DBC2VAL or VAL2DBC must be enabled")

    if args.dbcfile:
        dbcfile = args.dbcfile
    elif os.environ.get("DBC_FILE"):
        dbcfile = os.environ.get("DBC_FILE")
    else:
        dbcfile = config.get(CONFIG_SECTION_CAN, "dbcfile", fallback=None)

    if not dbcfile:
        parser.error("No DBC file(s) specified")

    if args.canport:
        canport = args.canport
    elif os.environ.get("CAN_PORT"):
        canport = os.environ.get("CAN_PORT")
    else:
        canport = config.get(CONFIG_SECTION_CAN, CONFIG_OPTION_PORT, fallback=None)

    if not canport:
        parser.error("No CAN port specified")

    if args.dbc_default:
        dbc_default = args.dbc_default
    elif os.environ.get("DBC_DEFAULT_FILE"):
        dbc_default = os.environ.get("DBC_DEFAULT_FILE")
    else:
        dbc_default = config.get(CONFIG_SECTION_CAN, CONFIG_OPTION_DBC_DEFAULT_FILE, fallback="dbc_default_values.json")

    if args.mapping:
        mappingfile = args.mapping
    elif os.environ.get("MAPPING_FILE"):
        mappingfile = os.environ.get("MAPPING_FILE")
    else:
        mappingfile = config.get(CONFIG_SECTION_GENERAL, CONFIG_OPTION_MAPPING, fallback="mapping/vss_4.0/vss_dbc.json")

    if args.use_j1939:
        use_j1939 = True
    elif os.environ.get("USE_J1939"):
        use_j1939 = True
    else:
        use_j1939 = config.getboolean(CONFIG_SECTION_CAN, CONFIG_OPTION_J1939, fallback=False)

    candumpfile = None
    if not args.use_socketcan:
        if args.dumpfile:
            candumpfile = args.dumpfile
        elif os.environ.get("CANDUMP_FILE"):
            candumpfile = os.environ.get("CANDUMP_FILE")
        else:
            candumpfile = config.get(CONFIG_SECTION_CAN, CONFIG_OPTION_CAN_DUMP_FILE, fallback=None)

        if args.val2dbc and candumpfile is not None:
            parser.error("Cannot use dumpfile and val2dbc at the same time!")

    elmcan_config = []
    if canport == "elmcan":
        if candumpfile is not None:
            parser.error("It is a contradiction specifying both elmcan and candumpfile!")
        if not config.has_section(CONFIG_SECTION_ELMCAN):
            parser.error("Cannot use elmcan without configuration in [elmcan] section!")
        elmcan_config = config[CONFIG_SECTION_ELMCAN]

    kuksa_val_client = _get_kuksa_val_client(args, config)
    feeder = Feeder(kuksa_val_client, elmcan_config, dbc2vss=use_dbc2val, vss2dbc=use_val2dbc)

    def signal_handler(signal_received, *_):
        log.info("Received signal %s, stopping...", signal_received)

        # If we get told to shutdown a second time. Just do it.
        if not feeder.is_running():
            log.warning("Shutting down now!")
            sys.exit(-1)

        feeder.stop()

    signal(SIGINT, signal_handler)
    signal(SIGTERM, signal_handler)

    log.info("Starting CAN feeder")
    feeder.start(
        canport=canport,
        dbc_file_names=dbcfile.split(','),
        mappingfile=mappingfile,
        dbc_default_file=dbc_default,
        candumpfile=candumpfile,
        use_j1939=use_j1939,
        use_strict_parsing=args.strict,
        can_fd=args.canfd
    )

    return 0


def parse_env_log(env_log, default=logging.INFO):
    def parse_level(specified_level, default=default):
        if isinstance(specified_level, str):
            if specified_level.lower() in [
                "debug",
                "info",
                "warn",
                "warning",
                "error",
                "critical",
            ]:
                return specified_level.upper()
            raise ValueError(f"could not parse '{specified_level}' as a log level")
        return default

    parsed_loglevels = {}

    if env_log is not None:
        log_specs = env_log.split(",")
        for log_spec in log_specs:
            spec_parts = log_spec.split("=")
            if len(spec_parts) == 1:
                # This is a root level spec
                if "root" in parsed_loglevels:
                    raise ValueError("multiple root loglevels specified")
                parsed_loglevels["root"] = parse_level(spec_parts[0])
            if len(spec_parts) == 2:
                logger_name = spec_parts[0]
                logger_level = spec_parts[1]
                parsed_loglevels[logger_name] = parse_level(logger_level)

    if "root" not in parsed_loglevels:
        parsed_loglevels["root"] = default

    return parsed_loglevels


if __name__ == "__main__":
    # Example
    #
    # Set log level to debug
    #   LOG_LEVEL=debug ./dbcfeeder.py
    #
    # Set log level to INFO, but for dbcfeederlib.databrokerclientwrapper set it to DEBUG
    #   LOG_LEVEL=info,dbcfeederlib.databrokerclientwrapper=debug ./dbcfeeder.py
    #
    # Other available loggers:
    #   dbcfeeder (main dbcfeeder file)
    #   dbcfeederlib.* (Every file have their own logger, like dbcfeederlib.databrokerclientwrapper)
    #   kuksa_client (If you want to get additional information from kuksa-client python library)
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
