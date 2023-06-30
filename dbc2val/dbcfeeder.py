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
import enum
import logging
import os
import queue
import sys
import time
import threading
import asyncio

from signal import SIGINT, SIGTERM, signal
from typing import Any
from typing import Dict

from dbcfeederlib import canclient
from dbcfeederlib import canplayer
from dbcfeederlib import dbc2vssmapper
from dbcfeederlib import dbcreader
from dbcfeederlib import dbcparser
from dbcfeederlib import j1939reader
from dbcfeederlib import databrokerclientwrapper
from dbcfeederlib import serverclientwrapper
from dbcfeederlib import clientwrapper
from dbcfeederlib import elm2canbridge

log = logging.getLogger("dbcfeeder")


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
    def __init__(self, client_wrapper: clientwrapper.ClientWrapper,
                 elmcan_config: Dict[str, Any], dbc2val: bool = True, val2dbc: bool = False):
        self._shutdown = False
        self._reader = None
        self._player = None
        self._mapper = None
        self._registered = False
        self._can_queue: queue.Queue[dbc2vssmapper.VSSObservation] = queue.Queue()
        self._client_wrapper = client_wrapper
        self._elmcan_config = elmcan_config
        self._disconnect_time = 0.0
        self._dbc2val = dbc2val
        self._val2dbc = val2dbc
        self._canclient = None
        self._transmit = False
        self._dbc_parser = None

    def start(
        self,
        canport,
        dbcfile,
        mappingfile,
        dbc_default_file,
        candumpfile=None,
        use_j1939=False,
        use_strict_parsing=False
    ):

        # Read DBC file
        self._dbc_parser = dbcparser.DBCParser(dbcfile, use_strict_parsing)

        log.info("Using mapping: {}".format(mappingfile))
        self._mapper = dbc2vssmapper.Mapper(mappingfile, self._dbc_parser, dbc_default_file)

        self._client_wrapper.start()
        threads = []

        if self._dbc2val and self._mapper.has_dbc2val_mapping():
            log.info("Setting up reception of CAN signals")
            if use_j1939:
                log.info("Using J1939 reader")
                self._reader = j1939reader.J1939Reader(
                    rxqueue=self._can_queue,
                    mapper=self._mapper,
                    dbc_parser=self._dbc_parser
                )
            else:
                log.info("Using DBC reader")
                self._reader = dbcreader.DBCReader(
                    rxqueue=self._can_queue,
                    mapper=self._mapper,
                    dbc_parser=self._dbc_parser
                )

            if candumpfile:
                # use dumpfile
                log.info(
                    "Using virtual bus to replay CAN messages (channel: %s) (dumpfile: %s)",
                    canport,
                    candumpfile
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

            receiver = threading.Thread(target=self._run_receiver)
            receiver.start()
            threads.append(receiver)
        else:
            log.info("No dbc2val mappings found or dbc2val disabled!")

        if self._val2dbc and self._mapper.has_val2dbc_mapping():
            if not self._client_wrapper.supports_subscription():
                log.error("Subscribing to VSS signals not supported by chosen client!")
                self.stop()
            else:
                log.info(f"Starting transmit thread, using {canport}")
                # For now creating another bus
                # Maybe support different buses for downstream/upstream in the future

                self._canclient = canclient.CANClient(bustype="socketcan", channel=canport)

                transmitter = threading.Thread(target=self._run_transmitter)
                transmitter.start()
                threads.append(transmitter)
        else:
            log.info("No val2dbc mappings found or val2dbc disabled!!")
        # Wait for all of them to finish
        for thread in threads:
            thread.join()

    def stop(self):
        log.info("Shutting down...")
        self._shutdown = True
        # Tell others to stop
        if self._reader is not None:
            self._reader.stop()
        if self._player is not None:
            self._player.stop()
        self._client_wrapper.stop()
        if self._canclient:
            self._canclient.stop()
            self._canclient = None
        self._mapper = None
        self._transmit = False

    def is_stopping(self):
        return self._shutdown

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
            resp = self._client_wrapper.is_signal_defined(vss_name)
            if not resp:
                all_registered = False
        return all_registered

    def _run_receiver(self):
        processing_started = False
        messages_sent = 0
        last_sent_log_entry = 0
        queue_max_size = 0
        while self._shutdown is False:
            if self._client_wrapper.is_connected():
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
                queue_size = self._can_queue.qsize()
                if queue_size > queue_max_size:
                    queue_max_size = queue_size
                vss_observation = self._can_queue.get(timeout=1)
                vss_mapping = self._mapper.get_dbc2val_mapping(vss_observation.dbc_name, vss_observation.vss_name)
                value = vss_mapping.transform_value(vss_observation.raw_value)
                if value is None:
                    log.warning(f"Value ignored for  dbc {vss_observation.dbc_name} to VSS {vss_observation.vss_name},"
                                f" from raw value {value} of type {type(value)}")
                elif not vss_mapping.change_condition_fulfilled(value):
                    log.debug(f"Value condition not fulfilled for VSS {vss_observation.vss_name}, value {value}")
                else:
                    # get values out of the canreplay and map to desired signals
                    target = vss_observation.vss_name

                    success = self._client_wrapper.update_datapoint(target, value)
                    if success:
                        log.debug("Succeeded sending DataPoint(%s, %s, %f)", target, value, vss_observation.time)
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

    async def vss_update(self, updates):
        log.debug("vss-Update callback!")
        dbc_ids = set()
        for update in updates:
            if update.entry.value is not None:
                # This shall currently never happen as we do not subscribe to this
                log.warning(f"Current value for {update.entry.path} is now: "
                            f"{update.entry.value.value} of type {type(update.entry.value.value)}")

            if update.entry.actuator_target is not None:
                log.debug(f"Target value for {update.entry.path} is now: {update.entry.actuator_target} "
                          f"of type {type(update.entry.actuator_target.value)}")
                new_dbc_ids = self._mapper.handle_update(update.entry.path, update.entry.actuator_target.value)
                dbc_ids.update(new_dbc_ids)

        can_ids = set()
        for dbc_id in dbc_ids:
            can_id = self._dbc_parser.get_canid_for_signal(dbc_id)
            can_ids.add(can_id)

        for can_id in can_ids:
            log.debug(f"CAN id to be sent, this is {can_id}")
            sig_dict = self._mapper.get_value_dict(can_id)
            message_data = self._dbc_parser.db.get_message_by_frame_id(can_id)
            data = message_data.encode(sig_dict)
            self._canclient.send(arbitration_id=message_data.frame_id, data=data)

    async def _run_subscribe(self):
        """
        Requests the client wrapper to start subscription.
        Checks every second if we have requested to stop reception and if so exits
        """
        asyncio.create_task(self._client_wrapper.subscribe(self._mapper.get_val2dbc_entries(), self.vss_update))
        while self._transmit:
            await asyncio.sleep(1)

    def _run_transmitter(self):
        """
        Starts subscription to selected VSS signals and on updates transmit to CAN
        """
        self._transmit = True
        asyncio.run(self._run_subscribe())


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
    """Main entrypoint for dbcfeeder"""
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
        help="Mapping file used to map CAN signals to VSS datapoints",
    )
    parser.add_argument(
        "--dbc-default",
        metavar="FILE",
        help="File containing default values for DBC signals. Needed for all CAN signals used if using val2dbc",
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

    args = parser.parse_args()

    config = parse_config(args.config)

    if args.server_type:
        server_type = args.server_type
    elif os.environ.get("SERVER_TYPE"):
        server_type = ServerType(os.environ.get("SERVER_TYPE"))
    elif "server_type" in config["general"]:
        server_type = ServerType(config["general"]["server_type"])
    else:
        server_type = ServerType.KUKSA_VAL_SERVER

    if server_type not in [ServerType.KUKSA_VAL_SERVER, ServerType.KUKSA_DATABROKER]:
        raise ValueError(f"Unsupported server type: {server_type}")

    # The wrappers contain default settings, so we only need to change settings
    # if given by dbcfeeder configs/arguments/env-variables
    if server_type is ServerType.KUKSA_VAL_SERVER:
        client_wrapper = serverclientwrapper.ServerClientWrapper()
    elif server_type is ServerType.KUKSA_DATABROKER:
        client_wrapper = databrokerclientwrapper.DatabrokerClientWrapper()

    if os.environ.get("KUKSA_ADDRESS"):
        client_wrapper.set_ip(os.environ.get("KUKSA_ADDRESS"))
    elif "ip" in config["general"]:
        client_wrapper.set_ip(config["general"]["ip"])

    if os.environ.get("KUKSA_PORT"):
        client_wrapper.set_port(os.environ.get("KUKSA_PORT"))
    elif "port" in config["general"]:
        client_wrapper.set_port(config["general"]["port"])

    if "tls" in config["general"]:
        client_wrapper.set_tls(config["general"].getboolean("tls"))

    if "root_ca_path" in config["general"]:
        path = config['general']['root_ca_path']
        log.info(f"Given root CA path: {path}")
        client_wrapper.set_root_ca_path(path)
    elif client_wrapper.get_tls():
        # We do not want to rely on kuksa-client default
        log.error("Root CA must be given when using TLS")

    if "tls_server_name" in config["general"]:
        name = config['general']['tls_server_name']
        log.info(f"Given TLS server name: {name}")
        client_wrapper.set_tls_server_name(name)

    if "token" in config["general"]:
        log.info(f"Given token information: {config['general']['token']}")
        client_wrapper.set_token_path(config["general"]["token"])
    else:
        log.info("Token information not given")

    if args.mapping:
        mappingfile = args.mapping
    elif os.environ.get("MAPPING_FILE"):
        mappingfile = os.environ.get("MAPPING_FILE")
    elif "general" in config and "mapping" in config["general"]:
        mappingfile = config["general"]["mapping"]
    else:
        mappingfile = "mapping/vss_4.0/vss_dbc.json"

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
        use_j1939 = True
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

        if args.val2dbc and candumpfile is not None:
            log.error("Cannot use dumpfile and val2dbc at the same time!")
            sys.exit(-1)

    client_wrapper.get_client_specific_configs()

    elmcan_config = []
    if canport == "elmcan":
        if candumpfile is not None:
            log.error("It is a contradiction specifying both elmcan and candumpfile!")
            sys.exit(-1)
        if "elmcan" not in config:
            log.error("Cannot use elmcan without elmcan config!")
            sys.exit(-1)
        elmcan_config = config["elmcan"]

    if args.dbc_default:
        dbc_default = args.dbc_default
    elif os.environ.get("DBC_DEFAULT_FILE"):
        dbc_default = os.environ.get("DBC_DEFAULT_FILE")
    elif "can" in config and "dbc_default_file" in config["can"]:
        dbc_default = config["can"]["dbc_default_file"]
    else:
        dbc_default = "dbc_default_values.json"

    if args.dbc2val:
        use_dbc2val = True
    elif args.no_dbc2val:
        use_dbc2val = False
    elif os.environ.get("USE_DBC2VAL"):
        use_dbc2val = True
    elif os.environ.get("NO_USE_DBC2VAL"):
        use_dbc2val = False
    elif "general" in config and "dbc2val" in config["general"]:
        use_dbc2val = config["general"].getboolean("dbc2val", False)
    else:
        # By default enabled
        log.info("Alt5")
        use_dbc2val = True
    log.info(f"DBC2VAL mode is: {use_dbc2val}")

    if args.val2dbc:
        use_val2dbc = True
    elif args.no_val2dbc:
        use_val2dbc = False
    elif os.environ.get("USE_VAL2DBC"):
        use_val2dbc = True
    elif os.environ.get("NO_USE_VAL2DBC"):
        use_val2dbc = False
    elif "general" in config and "val2dbc" in config["general"]:
        use_val2dbc = config["general"].getboolean("val2dbc", True)
    else:
        # By default disabled
        use_val2dbc = False
    log.info(f"VAL2DBC mode is: {use_val2dbc}")

    feeder = Feeder(client_wrapper, elmcan_config, dbc2val=use_dbc2val, val2dbc=use_val2dbc)

    def signal_handler(signal_received, *_):
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
        dbc_default_file=dbc_default,
        candumpfile=candumpfile,
        use_j1939=use_j1939,
        use_strict_parsing=args.strict
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
            raise Exception(f"could not parse '{specified_level}' as a log level")
        return default

    parsed_loglevels = {}

    if env_log is not None:
        log_specs = env_log.split(",")
        for log_spec in log_specs:
            spec_parts = log_spec.split("=")
            if len(spec_parts) == 1:
                # This is a root level spec
                if "root" in parsed_loglevels:
                    raise Exception("multiple root loglevels specified")
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
