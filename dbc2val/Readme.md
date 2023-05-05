# Feeder CAN for real CAN interface or dumpfile replay

This is an a DBC CAN feeder for the [KUKSA.val](https://github.com/eclipse/kuksa.val) server and databroker. The basic operation is as follows:
The feeder connects to a socket CAN interface and reads raw CAN data, that will be parsed based on a DBC file.
The mapping file (called `vss_dbc.json` in the picture) describes mappings between VSS signals and DBC signals. The respective data point can then be sent to the kuksa.val databroker or kuksa.val server.
It is also possible to replay CAN dumpfiles without the SocketCAN interface being available, e.g. in a CI test environment.
See "Steps for a local test with replaying a can dump file"

```console
                             +-------------+
                             |   DBCFile   |
                             +-------------+            +-------------+
                                    |                   |             |
                                    |              |--->|  VSS Server |
                                    |              |    |             |
                                    |              |    +-------------+
+-----------------+                 |              |
|                 |         +-------|------+       |
|  CAN Interface  |         |              |       |
|       or        |------- >|  DBCFeeder   | --OR--|
| dumpfile replay |         |              |       |
|                 |         +--------------+       |
+-----------------+                 |              |    +-------------+
                                    |              |    |             |
                            +--------------+       |--->|  Databroker |
                            | vss_dbc.json |            |             |
                            +--------------+            +-------------+

```

## General Setup Requirements

1. Install can utils, e.g. in Ubuntu do:

```console
$ sudo apt update
$ sudo apt install can-utils
```

2. Check that at least Python version 3.8 is installed

```console
$ python -V
```

3. Install the needed python packages

```console
$ pip install --pre -r requirements.txt
```

*Note - `--pre` currently needed as dbcfeeder relies on a pre-release of kuksa-client*

4. If you want to run tests and linters, you will also need to install development dependencies

```console
$ pip install -r requirements-dev.txt
```

## Steps for a local test with socket can or virtual socket can

1. Use the argument --use-socketcan or you can remove the line with the dumpfile in `config/dbc_feeder.ini`

2. Start the can player

_This is only needed if you want feed data from a dumpfile!_

```console
$ ./createvcan.sh vcan0
$ canplayer vcan0=elmcan -v -I candump.log -l i -g 1
```

3. Start the kuksa val server or the databroker, for further infomation see [Using kuksa-val-server](#using-kuksa-val-server) or [Using kuksa-databroker](#using-kuksa-databroker).

4. Run the dbcfeeder.py

```console
$ ./dbcfeeder.py
```

## Steps for a local test with replaying a can dump file

1. Set the a path to a dumpfile e.g. candump.log in the config file `config/dbc_feeder.ini` or use the argument --dumpfile to use a different dumpfile

2. Start the kuksa val server or the databroker, for further infomation see [Using kuksa-val-server](#using-kuksa-val-server) or [Using kuksa-databroker](#using-kuksa-databroker).

3. Run the dbcfeeder.py

```console
$ ./dbcfeeder.py
```

## Provided can-dump files

[candump-2021-12-08_151848.log.xz](./candump-2021-12-08_151848.log.xz)
is a CAN trace from  2018 Tesla M3 with software 2021.40.6.
This data is interpreted using the [Model3CAN.dbc](./Model3CAN.dbc) [maintained by Josh Wardell](https://github.com/joshwardell/model3dbc).

The canlog in the repo is compressed, to uncompress it (will be around 150MB) do
```
unxz candump-2021-12-08_151848.log.xz
```

[candump.log](./candump.log):
A smaller excerpt from the above sample, with fewer signals.

## Configuration

| Command Line Argument | Environment Variable            | Config File Property    | Default Value                    | Description         |
|:----------------------|:--------------------------------|:------------------------|:---------------------------------|---------------------|
| *--config*            | -                               | -                       | *See below*                      | Configuration file  |
| *--dbcfile*           | *DBC_FILE*                      | *[can].dbc*             |                                  | DBC file used for parsing CAN traffic  |
| *--dumpfile*          | *CANDUMP_FILE*                  | *[can].candumpfile*     |                                  | Replay recorded CAN traffic from dumpfile |
| *--canport*           | *CAN_PORT*                      | *[can].port*            |                                  | Read from this CAN interface |
| *--use-j1939*         | *USE_J1939*                     | *[can].j1939*           | `False`                          | Use J1939 when decoding CAN frames. Setting the environment value to any value is equivalent to activating the switch on the command line. |
| *--use-socketcan*     | -                               | -                       | `False`                          | Use SocketCAN (overriding any use of --dumpfile) |
| *--mapping*           | *MAPPING_FILE*                  | *[general].mapping*     | `mapping/vss_4.0/vss_dbc.json` | Mapping file used to map CAN signals to databroker datapoints. |
| *--server-type*       | *SERVER_TYPE*                   | *[general].server_type* | `kuksa_databroker`               | Which type of server the feeder should connect to (`kuksa_val_server` or `kuksa_databroker`) |
| -                     | *KUKSA_ADDRESS*                 | *[general].ip*          | `127.0.0.1`                      | IP address for Server/Databroker |
| -                     | *KUKSA_PORT*                    | *[general].port*        | `55555`                          | Port for Server/Databroker |
| *--tls*               | -                               | *[general].tls*         | `False`                          | Shall tls be used for Server/Databroker connection? |
| -                     | -                               | *[general].token*       | *Undefined*                      | Token path. Only needed if Databroker/Server requires authentication |
| -                     | *VEHICLEDATABROKER_DAPR_APP_ID* | -                       | -                                | Add dapr-app-id metadata. Only relevant for KUKSA.val Databroker |

*Note that the [default config file](config/dbc_feeder.ini) include default Databroker settings and must be modified if you intend to use it for KUKSA.val Server*

If `--config` is not given, the dbcfeeder will look for configuration files in the following locations:

* `/config/dbc_feeder.in`
* `/etc/dbc_feeder.ini`
* `config/dbc_feeder.ini`

The first one found will be used.

Configuration options have the following priority (highest at top).

1. command line argument
2. environment variable
3. configuration file
4. default value

## Using kuksa-val-server

1. To make the feeder communicate with this server, use the `--server-type kuksa_val_server` CLI option or refer to [Configuration](#configuration) for `server-type`.

2. Use the latest release from here:
https://github.com/eclipse/kuksa.val/tree/master/kuksa-val-server

After you download for example the release 0.2.1 you can run it with this command, this is also described in the kuksa val server [readme](https://github.com/eclipse/kuksa.val/blob/master/kuksa-val-server/README.md):

```console
$ docker run -it --rm -v $HOME/kuksaval.config:/config  -p 127.0.0.1:8090:8090 -e LOG_LEVEL=ALL ghcr.io/eclipse/kuksa.val/kuksa-val:0.2.1-amd64
```

3. After server is started also start the dbcfeeder you should got some similar output in the kuksa val server terminal

```console
VERBOSE: Receive action: set
VERBOSE: Set request with id 05dd9d59-c9a7-4073-9d86-69c8cee85d4c for path: Vehicle.OBD.EngineLoad
VERBOSE: SubscriptionHandler::publishForVSSPath: set value "0" for path Vehicle.OBD.EngineLoad
VERBOSE: Receive action: set
VERBOSE: Set request with id cbde247f-944a-4335-ad87-1062a6d7f28b for path: Vehicle.Chassis.ParkingBrake.IsEngaged
VERBOSE: SubscriptionHandler::publishForVSSPath: set value true for path Vehicle.Chassis.ParkingBrake.IsEngaged
```

## Using kuksa-databroker

1. To make the feeder communicate with this server, use the `--server-type kuksa_databroker` CLI option or refer to [Configuration](#configuration) for `server-type`.

2. Start kuksa_databroker server:

```console
$ cd kuksa.val/kuksa_databroker
$ cargo run --bin databroker -- --metadata ../data/vss-core/vss_release_3.0.json
    Finished dev [unoptimized + debuginfo] target(s) in 0.07s
     Running `/home/ler2so/Repo/kuksa.val/target/debug/databroker --metadata ../data/vss-core/vss_release_3.0.json`
2022-12-01T13:53:58.933749Z  INFO databroker: Init logging from RUST_LOG (environment variable not found)
2022-12-01T13:53:58.933781Z  INFO databroker: Starting Kuksa Data Broker 0.17.0
2022-12-01T13:53:58.933865Z  INFO databroker: Populating metadata... from file '../data/vss-core/vss_release_3.0.json'
2022-12-01T13:53:58.944068Z  INFO databroker: Listening on 127.0.0.1:55555
2022-12-01T13:53:58.944095Z  INFO databroker::broker: Starting housekeeping task
```

> **Warning**
> Automatic data entry registration is not yet supported so you **do need** to specify a metadata path using `--metadata`.
> If you don't, running `./dbcfeeder.py` against databroker will raise ``2022-12-05 18:10:18,226 ERROR dbcfeeder: Failed to register datapoints``.

3. Start the vehicle data client cli

```console
$ cd kuksa.val/kuksa_databroker
$ cargo run --bin databroker-cli
    Finished dev [unoptimized + debuginfo] target(s) in 0.06s
     Running `/home/ler2so/Repo/kuksa.val/target/debug/databroker-cli`
client>
```

4. After dbcfeeder is running use vehicle data client cli to subcribe to datapoints

```console
client> subscribe SELECT Vehicle.OBD.Speed

# press 2 times Enter

-> status: OK
-> subscription1:
Vehicle.OBD.Speed: 14.00

-> subscription1:
Vehicle.OBD.Speed: 13.00

-> subscription1:
Vehicle.OBD.Speed: 12.00
```

> **Note**
> To end the subscription currently you have to stop the client cli via 'quit' and Enter.

## Using Docker

It is possible to build dbcfeeder as a Docker container

```console
docker build -f Dockerfile --progress=plain --build-arg TARGETPLATFORM=linux/amd64 -t dbcfeeder:latest .
```

The same container can be used for both connecting to Databroker and Server:

```console
docker run  --net=host -e LOG_LEVEL=INFO dbcfeeder:latest --server-type kuksa_databroker

docker run  --net=host -e LOG_LEVEL=INFO dbcfeeder:latest --server-type kuksa_val_server
```

### KUKSA.val Server/Databroker Authentication when using Docker

The docker container contains default certificates for KUKSA.val server, and if the configuration file does not
specify token file the [default token file](https://github.com/eclipse/kuksa.val/blob/master/kuksa_certificates/jwt/all-read-write.json.token)
provided by [kuksa-client](https://github.com/eclipse/kuksa.val/tree/master/kuksa-client) will be used.

No default token is included for KUKSA.val Databroker. Instead the user must specify the token file in the config file.
The token must also be available for the running docker container, for example by mounting the directory container
when starting the container. Below is an example based on that the token file
[provide-all.token](https://github.com/eclipse/kuksa.val/blob/master/jwt/provide-all.token) is used and that `kuksa.val`
is cloned to `/home/user/kuksa.val`. Then the token can be accessed by mounting the `jwt`folder using the `-v`
and specify `token=/jwt/provide-all.token` in the [default configuration file](config/dbc_feeder.ini).


```console
docker run  --net=host -e LOG_LEVEL=INFO -v /home/user/kuksa.val/jwt:/jwt dbcfeeder:latest
```

*Note that authentication in KUKSA.val Databroker by default is deactivated, and then no token needs to be given!*

## Mapping file

The mapping file describes mapping between VSS signals and DBC signals.
It shall be a JSON file with VSS syntax with metadata for dbc information.
Please see [mapping documentation](mapping/mapping.md) for more information.

## Logging

The log level of `dbcfeeder.py` can be set using the LOG_LEVEL environment variable

To set the log level to DEBUG

```console
$ LOG_LEVEL=debug ./dbcfeeder.py
```

Set log level to INFO, but for dbcfeederlib.databrokerclientwrapper set it to DEBUG

```console
$ LOG_LEVEL=info,dbcfeederlib.databrokerclientwrapper=debug ./dbcfeeder.py
```

or, since INFO is the default log level, this is equivalent to:

```console
$ LOG_LEVEL=dbcfeederlib.databrokerclientwrapper=debug ./dbcfeeder.py
```

Available loggers:
- dbcfeeder
- dbcfeederlib.* (one for every file in the dbcfeeder directory)
- kuksa-client (to control loggings provided by [kuksa-client](https://github.com/eclipse/kuksa.val/tree/master/kuksa-client))

## ELM/OBDLink support

The feeder works best with a real CAN interface. If you use an OBD Dongle the feeder can configure it to use it as a CAN Sniffer
(using  `STM` or `STMA` mode). The elmbridge will talk to the OBD Adapter using its custom AT protocol, parse the received CAN frames,
and put them into a virtual CAN device. The DBC feeder can not tell the difference.

There are some limitations in this mode
 * Does not support generic ELM327 adapters but needs to have the ST commands from the OBDLink Devices available:
 This code has been tested with the STN2120 that is available on the KUKSA dongle, but should work on other STN chips too
 * Bandwidth/buffer overrun on Raspberry Pi internal UARTs:When connecting the STN to one of the Pis internal UARTs you will
 loose messages on fully loaded CAN busses (500kbit does not work when it is very loaded). The problem is not the raw bandwith
 (The Pi `/dev/ttyAMA0` UART can go up to 4 MBit when configured accordingly), but rather that the Pi UART IP block does not support
 DMA and has only an 8 bytes buffer. If the system is loaded, and you get scheduled a little too late, the overrun already occurred.
 While this makes this setup a little useless for a generic sniffer, in most use cases it is fine, as the code configures a dynamic
 whitelist according to the configured signals, i.e. the STN is instructed to only let CAN messages containing signals of interest pass.

When using the OBD chipset, take special attention to the `obdcanack` configuration option: On a CAN bus there needs to be _some_ device
to acknowledge CAN frames. The STN2120 can do this. However, when tapping a vehicle bus, you probably do not want it (as there are other
ECUs on the bus doing it, and we want to be as passive as possible). On the other hand, on a desk setup where you have one CAN sender and
the OBD chipset, you need to enable Acks, otherwise the CAN sender will go into error mode, if no acknowledgement is received.

## SAE-J1939 support

When the target DBC file and ECU follow the SAE-J1939 standard, the CAN reader application of the feeder should read
PGN(Parameter Group Number)-based Data rather than CAN frames directly. Otherwise it is possible to miss signals from
large-sized messages that are delivered with more than one CAN frame because the size of each of these messages is bigger
than a CAN frame's maximum payload of 8 bytes. To enable the J1939 mode, simply put `--use-j1939` in the command when running `dbcfeeder.py`.

Support for J1939 is provided by means of the [can-j1939 package](https://pypi.org/project/can-j1939/).
