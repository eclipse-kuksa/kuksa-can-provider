# KUKSA Can provider Configuration

This file describes available configurations including examples on how they can be used.

## General configuration mechanism

KUKSA CAN Provider consider command line arguments, environment variables and configurations in configuration files.

Configuration options have the following priority (highest at top).

1. command line argument
2. environment variable
3. configuration file
4. default value

The general approach is that only a subset of configurations will be possible to set using
command line argument and environment variables, but all configurations shall be possible
to set in a configuration file.


| Command Line Argument | Environment Variable            | Config File Property    | Default Value                    | Description         |
|:----------------------|:--------------------------------|:------------------------|:---------------------------------|---------------------|
| *--config*            | -                               | -                       | *See below*                      | Configuration file  |
| *--dbcfile*           | *DBC_FILE*                      | *[can].dbc*             |                                  | DBC file(s) used for parsing CAN traffic. You may specify multiple file names separated by comma. Supports parsing of [arbitrary DB file types](https://github.com/cantools/cantools#about). |
| *--dumpfile*          | *CANDUMP_FILE*                  | *[can].candumpfile*     |                                  | Replay recorded CAN traffic from dumpfile |
| *--canport*           | *CAN_PORT*                      | *[can].port*            |                                  | Read from this CAN interface |
| *--use-j1939*         | *USE_J1939*                     | *[can].j1939*           | `False`                          | Use J1939 when decoding CAN frames. Setting the environment variable to any value is equivalent to activating the switch on the command line. |
| *--use-socketcan*     | -                               | -                       | `False`                          | Use SocketCAN (overriding any use of --dumpfile) |
| *--mapping*           | *MAPPING_FILE*                  | *[general].mapping*     | `mapping/vss_4.0/vss_dbc.json` | Mapping file used to map CAN signals to databroker datapoints. |
| *--server-type*       | *SERVER_TYPE*                   | *[general].server_type* | `kuksa_databroker`               | Which type of server the provider should connect to (`kuksa_val_server` or `kuksa_databroker`) |
| -                     | *KUKSA_ADDRESS*                 | *[general].ip*          | `127.0.0.1`                      | IP address for Server/Databroker |
| -                     | *KUKSA_PORT*                    | *[general].port*        | `55555`                          | Port for Server/Databroker |
| -                     | -                               | *[general].tls*         | `False`                          | Shall tls be used for Server/Databroker connection? |
| -                     | -                               | *[general].root_ca_path* | *Undefined*                      | Path to root CA: Only needed if using TLS |
| -                     | -                               | *[general].tls_server_name* | *Undefined*                   | TLS server name, may be needed if addressing a server by IP-name |
| -                     | -                               | *[general].token*       | *Undefined*                      | Token path. Only needed if Databroker/Server requires authentication |
| -                     | *VEHICLEDATABROKER_DAPR_APP_ID* | -                       | -                                | Add dapr-app-id metadata. Only relevant for KUKSA.val Databroker |
| *--dbc2val /--no-dbc2val* | *USE_DBC2VAL* / *NO_USE_DBC2VAL* | *[can].dbc2val*    | dbc2val enabled                  | Specifies if sending data from CAN to KUKSA.val is enabled. Setting the environment variable to any value is equivalent to activating the switch on the command line.|
| *--val2dbc /--no-val2dbc* | *USE_VAL2DBC* / *NO_USE_VAL2DBC* | *[can].val2dbc*    | val2dbc nor enabled              | Specifies if sending data from KUKSA.val to CAN is enabled. Setting the environment variable to any value is equivalent to activating the switch on the command line. |
| *--dbc_default <file_path>* | -                         | -                       | dbc_default_values.json          | Default values for val2dbc. Needed for all DBCs in sent CAN signals |

*Note that the [default config file](../config/dbc_feeder.ini) include default Databroker settings and must be modified if you intend to use it for KUKSA.val Server*

If `--config` is not given, the dbcfeeder will look for configuration files in the following locations:

* `/config/dbc_feeder.in`
* `/etc/dbc_feeder.ini`
* `config/dbc_feeder.ini`

The first one found will be used.


## Steps for a local dbc2val test with socket can or virtual socket can

1. Use the argument --use-socketcan or you can remove the line with the dumpfile in `config/dbc_feeder.ini`

2. Start the can player

_This is only needed if you want feed data from a dumpfile, and do not want dbcfeeder to feed data itself!_

```console
$ ./createvcan.sh vcan0
$ canplayer vcan0=elmcan -v -I candump.log -l i -g 1
```

3. Start the kuksa val server or the databroker, for further infomation see [Using kuksa-val-server](#using-kuksa-val-server) or [Using kuksa-databroker](#using-kuksa-databroker).

4. Run the dbcfeeder.py

```console
$ ./dbcfeeder.py
```

## Steps for a local dbc2val test with replaying a can dump file

1. Set the a path to a dumpfile e.g. candump.log in the config file `config/dbc_feeder.ini` or use the argument --dumpfile to use a different dumpfile

2. Start the kuksa val server or the databroker, for further infomation see [Using kuksa-val-server](#using-kuksa-val-server) or [Using kuksa-databroker](#using-kuksa-databroker).

3. Run the dbcfeeder.py

```console
$ ./dbcfeeder.py
```

## Steps for val2dbc test with socketcan

Make sure socketcan is started

```console
$ ./createvcan.sh vcan0
```

Make also sure KUKSA.val Databroker is started. You cannot user val2dbc together with KUKSA.val Server.

Start dbcfeeder. Consider using debug-printouts to be able to verify that KUKSA.val updates reaches the dbcfeeder.
If KUKSA.val Databroker already has values for some of the signals expect something like below

```console
$ LOG_LEVEL="INFO,dbcfeederlib.dbc2vssmapper=DEBUG" ./dbcfeeder.py --val2dbc --no-dbc2val --use-socketcan
...
2023-06-02 11:01:22,474 INFO dbcfeeder: Starting CAN feeder
2023-06-02 11:01:22,474 INFO dbcfeederlib.dbcparser: Reading DBC file Model3CAN.dbc
2023-06-02 11:01:22,982 INFO dbcfeeder: Using mapping: mapping/vss_4.0/vss_dbc.json
2023-06-02 11:01:22,985 INFO dbcfeederlib.dbc2vssmapper: Reading dbc configurations from mapping/vss_4.0/vss_dbc.json
...
2023-06-02 11:01:22,999 INFO dbcfeeder: No dbc2val mappings found or dbc2val disabled!
2023-06-02 11:01:22,999 INFO dbcfeeder: Starting transmit thread, using vcan0
2023-06-02 11:01:23,001 INFO dbcfeederlib.databrokerclientwrapper: Connectivity to data broker changed to: ChannelConnectivity.READY
2023-06-02 11:01:23,002 INFO dbcfeederlib.databrokerclientwrapper: Connected to data broker
2023-06-02 11:01:23,003 INFO can.interfaces.socketcan.socketcan: Created a socket
2023-06-02 11:01:23,004 INFO dbcfeederlib.databrokerclientwrapper: Subscribe entry: SubscribeEntry(path='Vehicle.Body.Mirrors.DriverSide.Pan', view=<View.FIELDS: 10>, fields=[<Field.ACTUATOR_TARGET: 3>])
2023-06-02 11:01:23,004 INFO dbcfeederlib.databrokerclientwrapper: Subscribe entry: SubscribeEntry(path='Vehicle.Body.Mirrors.DriverSide.Tilt', view=<View.FIELDS: 10>, fields=[<Field.ACTUATOR_TARGET: 3>])
2023-06-02 11:01:23,004 INFO dbcfeederlib.databrokerclientwrapper: Subscribe entry: SubscribeEntry(path='Vehicle.Body.Trunk.Rear.IsOpen', view=<View.FIELDS: 10>, fields=[<Field.ACTUATOR_TARGET: 3>])
2023-06-02 11:01:23,004 INFO dbcfeederlib.databrokerclientwrapper: Subscribe entry: SubscribeEntry(path='Vehicle.Powertrain.ElectricMotor.Temperature', view=<View.FIELDS: 10>, fields=[<Field.ACTUATOR_TARGET: 3>])
2023-06-02 11:01:23,015 DEBUG dbcfeederlib.dbc2vssmapper: Transformed value 4.525 for Vehicle.Body.Mirrors.DriverSide.Pan
2023-06-02 11:01:23,015 DEBUG dbcfeederlib.dbc2vssmapper: Transformed value 3.775 for Vehicle.Body.Mirrors.DriverSide.Tilt
2023-06-02 11:01:23,015 DEBUG dbcfeederlib.dbc2vssmapper: Using stored information to create CAN-frame for 258
2023-06-02 11:01:23,016 DEBUG dbcfeederlib.dbc2vssmapper: Using DBC id VCLEFT_mirrorTiltXPosition with value 4.525
2023-06-02 11:01:23,016 DEBUG dbcfeederlib.dbc2vssmapper: Using DBC id VCLEFT_mirrorTiltYPosition with value 3.775
```

In val2dbc mode the provider subscribes to target values. To test that that updates reach the provider use for example the
[KUKSA.val Client](https://github.com/eclipse/kuksa.val/tree/master/kuksa-client) and set wanted target value
for one of the signals mentioned in the mapping.

```console
Test Client> setTargetValue Vehicle.Body.Mirrors.DriverSide.Pan 85
OK

```

## Steps for a bidirectional test

For bidirectional use you can either have separate instances of dbcfeeder or a joint instance

### Separate Instances

./dbcfeeder.py --val2dbc --dbc2val --use-socketcan

Start the val2dbc instance like this:

```console
./dbcfeeder.py --val2dbc --no-dbc2val --use-socketcan
```

... and the dbc2val instance like this:

```console
./dbcfeeder.py --no-val2dbc --dbc2val --use-socketcan
```

### Joint instance

It is also possible to use the same instance for both sending and receiving, like this:

```console
./dbcfeeder.py --val2dbc --dbc2val --use-socketcan
```

### Verifying expected behavior

Use the [KUKSA.val Python Client](https://github.com/eclipse/kuksa.val/tree/master/kuksa-client).
If connecting to KUKSA Databroker it is also possible to use [KUKSA Databroker CLI](https://github.com/eclipse/kuksa.val/tree/master/kuksa_databroker#test-the-databroker-using-cli).
Set target value and verify that actual value is updated. This happens as the example mapping
in this repository uses the same DBC signal for both val2dbc (`vss2dbc`) and val2dbc (`vss2dbc`). This is not
a realistic scenario, but is good for test purposes as it shows that when val2dbc sends the CAN-signal the
CAN-signal will be kept up by the dbc2val mode and then be treated as actual value.
In a realistic example some other application would listen to CAN, actuate the mirror and report back progress
on a different CAN signal.

The example below shows a possible output if using KUKSA Python Client. Note that you may not get back exactly the same value.
This is caused by the transformations.

* We set wanted value to +81%
* vss2dbc conversion first converts it to (81+100)/40 = 4.525 Volts (DBC range is 0-5 Volts)
* CAN tools then use DBC scaling of 0.02 to convert it to 4.525/0.02 = 226,25, truncated to 226 which is sent on CAN
* CAN tools when reading from CAN converts the value to 226*0.02 = 4.52
* dbc2vss mapping converts it to floor((4.52*40)-100) = floor(80.8) = 80 (Here one can argue that "round" possibly would be a better choice)

```console
Test Client> setTargetValue Vehicle.Body.Mirrors.DriverSide.Pan 81
OK

Test Client> getValue Vehicle.Body.Mirrors.DriverSide.Pan
{
    "path": "Vehicle.Body.Mirrors.DriverSide.Pan",
    "value": {
        "value": 80,
        "timestamp": "2023-06-02T09:11:07.214058+00:00"
    }
}
```

## Specifying multiple DBC files

It is possible to specify that KUKSA CAN Provider shall read multiple files by giving a comma separated list of
DBC files. Whitespace characters may be used but will stripped before file is read.
If whitespace characters is used on the command line then the string must be quoted

Below is two functionally equivalent methods to list two DBC files:

```console
./dbcfeeder.py --dbcfile test/test_dbc/test1_1.dbc,test/test_dbc/test1_2.dbc --config config/dbc_feeder.ini

./dbcfeeder.py --dbcfile "test/test_dbc/test1_1.dbc, test/test_dbc/test1_2.dbc" --config config/dbc_feeder.ini
```

If using a configuration file no quotes are needed, even if whitespaces are used
```
dbcfile = test/test_dbc/test1_1.dbc, test/test_dbc/test1_2.dbc
```

### Using kuksa-client with a server requiring Authorization

The [default configuration file](../config/dbc_feeder.ini) does not specify any token to use.
If the KUKSA.val Databroker or KUKSA.val Server requires authorization the `token` attribute in the config file
must be set. The default config file include (commented) values to use if using KUKSA.val example tokens.

*Note: Production deployments are strongly recommend to use Authorization but must NOT use the example tokens available in the KUKSA.val repository!*

### Using kuksa-client with a server requiring TLS

The [default configuration file](../config/dbc_feeder.ini) does not specify that TLS shall be used.
If the KUKSA.val Databroker or KUKSA.val Server requires authentication the `tls` attribute in the config file
must be set to `True` and `root_ca_path` must be set.
The default config file include (commented) values to use if using KUKSA.val example certificates.

The provider verifies that the Databroker/Server presents a certificate with a name matching the server.
The KUKSA.val default server certificate include `Server`, `localhost` and `127.0.0.1` as names, but due to a limitation
name validation does not work when using gRPC and a numeric IP-address, so for that combination you must as a work around
specify the `tls_server_name` to use in name validation, like in the example below.

```
ip = 127.0.0.1
tls = True
root_ca_path=../../kuksa.val/kuksa_certificates/CA.pem
tls_server_name=localhost
```

*Note: Production deployments are strongly recommend to use TLS but must NOT use the example certificates available in the KUKSA.val repository!*

## Using kuksa-val-server

1. To make the provider communicate with this server, use the `--server-type kuksa_val_server` CLI option or refer to [Configuration](#configuration) for `server-type`.

2. Use the latest release from here:
https://github.com/eclipse/kuksa.val/tree/master/kuksa-val-server

After you download for example the release 0.2.1 you can run it with this command, this is also described in the [KUKSA Server readme](https://github.com/eclipse/kuksa.val/blob/master/kuksa-val-server/README.md):

```console
$ docker run -it --rm -v $HOME/kuksaval.config:/config  -p 127.0.0.1:8090:8090 -e LOG_LEVEL=ALL ghcr.io/eclipse/kuksa.val/kuksa-val:0.2.1-amd64
```

3. After server is started also start the dbcfeeder you should got some similar output in the KUKSA Server terminal

```console
VERBOSE: Receive action: set
VERBOSE: Set request with id 05dd9d59-c9a7-4073-9d86-69c8cee85d4c for path: Vehicle.OBD.EngineLoad
VERBOSE: SubscriptionHandler::publishForVSSPath: set value "0" for path Vehicle.OBD.EngineLoad
VERBOSE: Receive action: set
VERBOSE: Set request with id cbde247f-944a-4335-ad87-1062a6d7f28b for path: Vehicle.Chassis.ParkingBrake.IsEngaged
VERBOSE: SubscriptionHandler::publishForVSSPath: set value true for path Vehicle.Chassis.ParkingBrake.IsEngaged
```

## Using kuksa-databroker

1. To make the provider communicate with this server, use the `--server-type kuksa_databroker` CLI option or refer to [Configuration](#configuration) for `server-type`.

2. Start KUKSA Databroker according to the [Quickstart](https://github.com/eclipse/kuksa.val/blob/master/doc/quickstart.md).
   Automatic data entry registration is not yet supported so you **do need** to specify a metadata path using `--metadata`.
3. To control that values are fed as expected to KUKSA Databroker you can use the [KUKSA.val Python Client](https://github.com/eclipse/kuksa.val/tree/master/kuksa-client)
   or the  [KUKSA Databroker CLI](https://github.com/eclipse/kuksa.val/tree/master/kuksa_databroker#test-the-databroker-using-cli)
   to connect to the Databroker.

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
