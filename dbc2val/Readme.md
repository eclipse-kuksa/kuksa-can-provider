# Feeder CAN for real CAN interface or dumpfile replay

This is an a DBC CAN feeder for the [KUKSA.val](https://github.com/eclipse/kuksa.val) server and databroker. The basic operation is as follows:
The feeder connects to a socket CAN interface and reads raw CAN data, that will be parsed based on a DBC file. The mapping file describes which DBC signal
should be matched to which part in the VSS tree. The respective data point can then be sent to the kuksa.val databroker or kuksa.val server.
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
                             +-------------+       |--->|  Databroker |
                             | mapping.yml |            |             |
                             +-------------+            +-------------+

```

## Prerequisites for using socket CAN or virtual socket CAN

1. Install can utils, e.g. in Ubuntu do:

```console
$ sudo apt update
$ sudo apt install can-utils
```

2. Check that at least python version 3 is installed

```console
$ python -V
```

3. Install the needed python packages

```console
$ pip install -r requirements.txt
```

## Steps for a local test with socket can or virtual socket can

1. Use the argument --use-socketcan or you can remove the line with the dumpfile in `config/dbc_feeder.ini`

2. Start the can player

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

<!--
[candump_Manual_SOC_DogMode_CabinTemp.log](./candump_Manual_SOC_DogMode_CabinTemp.log): Contains state-of-charge, dog mode, and cabin temperature signals. Take this if using the [dog mode example in the vehicle-app-python-sdk repo](https://github.com/SoftwareDefinedVehicle/vehicle-app-python-sdk/tree/main/examples).
-->

[candump-2021-12-08_151848.log.xz](./candump-2021-12-08_151848.log.xz)
Is a CAN trace from  2018 Tesla M3 with software 2021.40.6.
This data is interpreted using the [Model3CAN.dbc](./Model3CAN.dbc) [maintained by Josh Wardell](https://github.com/joshwardell/model3dbc).

The canlog in the repo is compressed, to uncompress it (will be around 150MB) do
```
unxz candump-2021-12-08_151848.log.xz
```

[candump.log](./candump.log):
A smaller excerpt from the above sample, with less signals.

## Configuration

| parameter                     | default value   | config file          | Env var                       | command line argument | description                                                                                             |
|-------------------------------|-----------------|----------------------|-------------------------------|-----------------------|---------------------------------------------------------------------------------------------------------|
| config                        | -               | -                    | -                             | `--config`            | Configuration file                                                                                      |
| dbcfile                       | -               | [can].dbc            | DBC_FILE                      | `--dbcfile`           | DBC file used for parsing CAN traffic                                                                   |
| dumpfile                      | -               | [can].candumpfile    | CANDUMP_FILE                  | `--dumpfile`          | Replay recorded CAN traffic from dumpfile                                                               |
| canport                       | -               | [can].port           | CAN_PORT                      | `--canport`           | Read from this CAN interface                                                                            |
| use-j1939                     | False           | [can].j1939          | USE_J1939                     | `--use-j1939`         | Use J1939                                                                                               |
| use-socketcan                 | False           | -                    | -                             | `--use-socketcan`     | Use SocketCAN (overriding any use of --dumpfile)                                                        |
| mapping                       | mapping.yml     | [general].mapping    | MAPPING_FILE                  | `--mapping`           | Mapping file used to map CAN signals to databroker datapoints. Take a look on usage of the mapping file |
| server-type                   | kuksa_val_server | [general].server_type | SERVER_TYPE                 | `--server-type`       | Which type of server the feeder should connect to (kuksa_val_server or kuksa_databroker |
| DAPR_GRPC_PORT                | -               | -                    | DAPR_GRPC_PORT                | -                     | Override broker address & connect to DAPR sidecar @ 127.0.0.1:DAPR_GRPC_PORT                            |
| VEHICLEDATABROKER_DAPR_APP_ID | -               | -                    | VEHICLEDATABROKER_DAPR_APP_ID | -                     | Add dapr-app-id metadata                                                                                |

Configuration options have the following priority (highest at top).

1. command line argument
2. environment variable
3. configuration file
4. default value

## Using kuksa-val-server

1. To make the feeder communicate with this server, use the `--server-type kuksa_val_server` CLI option or refer to [Configuration](#configuration) for `server-type`.

2. Use the latest release from here:
https://github.com/eclipse/kuksa.val/tree/master/kuksa-val-server

After you download for example the relase 0.21 you can run it with this command, this is also described in the kuksa val server readme:

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

## Using mapping.yml

Please replace the values xxx with our content for a new signal template:

```yaml
xxx: # CAN signal name taken from the used dbc file
  minupdatedelay: xxx # update interval of the signal in ms, if no delay given default is 1000ms
  targets:
    xxx: {} # Name of the VSS signal
      vss: # vss definition
        datatype: xxx # type of the data
        type: xxx # type of the value
        unit: xxx # unit of the value
        description: # description of the value
      transform: {}  # which (math) transformations to apply to the signal
```

example:

```yaml
UIspeed_signed257: # CAN signal name taken from the used dbc file
  minupdatedelay: 100 # 100ms update interval of the signal
  targets:
    Vehicle.OBD.Speed:  # Name of the VSS signal
      vss: # vss definition
        datatype: float # type of the data
        type: sensor # type of the value
        unit: km/h # unit of the value
        description: vehicle speed # description of the value
```

Please note, the minimal set to map a signal for KUKSA.val server, where all data model knwoledge is in the data server itself,  is just a CAN signal name and at least one target.
For KUKSA.val databroker, an architecture that requires Clients to know somehting about the VSS model, a CAN signal name, a target and at least a datatype in the vss section is required. In most cases, you would probably require a `transform`, unless the DBC already describes the exact semantics and/or scaling of a VSS signal.

### Mapping examples


```yaml
VCFRONT_brakeFluidLevel:
  minupdatedelay: 1000
  targets:
    Vehicle.Chassis.Axle.Row1.Wheel.Left.Brake.FluidLevelLow:
      transform:
        fullmapping:
          LOW: "true"
          NORMAL: "false"
    Vehicle.Chassis.Axle.Row1.Wheel.Right.Brake.FluidLevelLow:
      transform:
        fullmapping:
          LOW: "true"
          NORMAL: "false"
```
Here the same DBC signal `VCFRONT_brakeFluidLevel`is mapped to different VSS path. Also _fullmapping_ transform is applied. The value `LOW` from the DBC is mapped to the value `true` in the VSS path and `NORMAL`is mapped to `false`. In the _fullmapping_ transform, if no match is found, the value will be ignored. There also exists a _partialmapping_ transform, which works similarly, with the difference, that if no match is found the value from the DBC will be written as-is to KUKSA.val.

Another transform is the _math_ transform

```yaml
VCLEFT_mirrorTiltXPosition:
   minupdatedelay: 100
   targets:
    Vehicle.Body.Mirrors.Left.Pan:
      transform: #scale 0..5 to -100..100
        math: floor((x*40)-100)
```

This can be used if the scale of a signal as described in the DBC is not compatible with the VSS model.  The value - with all transforms described in the DBC -  is used as `x` on the formula given by the _math_ transform. For available operators, functions and constants supported by the _math_ transform check https://pypi.org/project/py-expression-eval/.


Take a look at the [mapping.yml](./mapping.yml) to see more examples.


## Logging

The log level of `dbcfeeder.py` can be set using the LOG_LEVEL environment variable

To set the log level to DEBUG

```console
$ LOG_LEVEL=debug ./dbcfeeder.py
```

Set log level to INFO, but for dbcfeeder.broker set it to DEBUG

```console
$ LOG_LEVEL=info,dbcfeeder.broker_client=debug ./dbcfeeder.py
```

or, since INFO is the default log level, this is equivalent to:

```console
$ LOG_LEVEL=dbcfeeder.broker_client=debug ./dbcfeeder.py
```

Available loggers:
- dbcfeeder
- dbcfeeder.broker_client
- databroker
- dbcreader
- dbcmapper
- can
- j1939

## ELM/OBDLink support

The feeder works best with a real CAN interface. If you use an OBD Dongle the feeder can configure it to use it as a CAN Sniffer
(using  `STM` or `STMA` mode). The elmbridge will talk to the OBD Adapter using its custom AT protocol, parse the received CAN frames,
and put them into a virtual CAN device. The DBC feeder can not tell the differenc

There are some limitations in this mode
 * Does not support generic ELM327 adapters but needs to have the ST commands from the OBDLink Devices available:
 This code has been tested with the STN2120 that is available on the KUKSA dongle, but should work on other STN chips too
 * Bandwidth/buffer overrun on Raspberry Pi internal UARTs:When connecting the STN to one of the Pis internal UARTs you will
 loose messages on fully loaded CAN busses (500kbit does not work when it is very loaded). The problem is not the raw bandwith
 (The Pi `/dev/ttyAMA0` UART can go up to 4 MBit when configured accordingly), but rather that the Pi UART IP block does not support
 DMA and has only an 8 bytes buffer. If the system is loaded, and you get scheduled a little too late, the overrun already occuured.
 While this makes this setup a little useless for a generic sniffer, in most use cases it is fine, as the code configures a dynamic
 whitelist according to the confgured signals, i.e. the STN is instructed to only let CAN messages containing signals of interest pass.

When using the OBD chipset, take special attention to the `obdcanack` configuration option: On a CAN bus there needs to be _some_ device
to acknowledge CAN frames. The STN2120 can do this. However, when tapping a vehicle bus, you probbably do not want it (as there are otehr
ECUs on the bus doing it, and we want to be as passive as possible). On theother hand, on a desk setup where you have one CAN sender and
the OBD chipst, you need to enable Acks, otherwise the CAN sender will go into error mode, if no acknowledgement is received.

## SAE-J1939 support

When the target DBC file and ECU follow the SAE-J1939 standard, the CAN reader application of the feeder should read
PGN(Parameter Group Number)-based Data rather than CAN frames directly. Otherwise it is possible to miss signals from
large-sized messages that are delivered with more than one CAN frame because the size of each of these messages is bigger
than a CAN frame's maximum payload of 8 bytes. To enable the J1939 mode, simply put `--j1939` in the command when running `dbcfeeder.py`.
Prior to using this feature, j1939 and the relevant wheel-packages should be installed first:

```console
$ pip install j1939
$ git clone https://github.com/benkfra/j1939.git
$ cd j1939
$ pip install .
```

The detailed documentation to this feature can be found here https://dias-kuksa-doc.readthedocs.io/en/latest/contents/j1939.html

