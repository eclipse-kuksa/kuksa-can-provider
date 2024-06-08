# KUKSA CAN Provider

![KUKSA Logo](./doc/img/logo.png)

This is a DBC CAN provider for the
[KUKSA.val](https://raw.githubusercontent.com/eclipse-kuksa/kuksa-can-provider/main/doc/img/logo.png) Server and Databroker.
For [KUKSA Server](https://github.com/boschglobal/kuksa.val/tree/master/kuksa-val-server)
it supports receiving data from CAN and sending to Server.
For [KUKSA Databroker](https://github.com/boschglobal/kuksa.val/tree/master/kuksa_databroker)
it supports both receiving data from CAN and sending to Databroker as well as subscribing to VSS signals in Databroker
and sending to CAN.

The basic operation is as follows:

The provider connects to a socket CAN interface. In dbc2val-mode it reads raw CAN data, that will be parsed based on a DBC file.
The mapping file (called `vss_dbc.json` in the picture) describes mappings between VSS signals and DBC signals.
The respective data point is then sent to KUKSA Databroker or Server.
It is also possible to replay CAN dumpfiles without the SocketCAN interface being available, e.g. in a CI test environment.
See "Steps for a local dbc2val test with replaying a can dump file"

Val2dbc-mode works similar, but in the opposite direction, taking data from KUKSA and sending on CAN.
The CAN sending functionality relies on that all signals in the CAN frame must have a value.
This is solved by using default values, if the provider does not have a VSS mapping for a specific DBC signal,
or has not received a value from KUKSA, then the default value will be used.
Default values shall be provided by a JSON file, an example file exists in [dbc_default_values.json](dbc_default_values.json).

*Note: If you use the files provided in this repository default values are only included for CAN id 258!*

```console
                             +-------------+
                             |   DBCFile   |
                             +-------------+            +------------------+
                                    |                   |                  |
                                    |              |--->| KUKSA Server     |
                                    |              |    |                  |
                                    |              |    +------------------+
+-----------------+                 |              |
|                 |         +-------|------+       |
|  CAN Interface  |         |              |       |
|       or        |<------ >| CAN Provider |<--OR--|
| dumpfile replay |         |              |       |
|                 |         +--------------+       |
+-----------------+                 |              |    +------------------+
                                    |              |    |                  |
                            +--------------+       |--->| KUKSA Databroker |
                            | vss_dbc.json |            |                  |
                            +--------------+            +------------------+

```

*By default only dbc2val-mode is enabled!*

## General Setup Requirements

Install can utils, e.g. in Ubuntu do:

```console
sudo apt update
sudo apt install can-utils
```

Check that at least Python version 3.9 is installed

```console
python -V
```

Install the needed python packages

```console
pip install -r requirements.txt
```

*Note - Sometimes DBC provider on main branch rely on a kuksa-client pre-release. Then you must add `--pre` to the command above!*

If you want to run tests and linters, you will also need to install development dependencies

```console
pip install -r requirements-dev.txt
```

## CAN Mapping

The CAN provider requires a mapping file as input.
The mapping file describes mapping between VSS signals and CAN (DBC) signals.
It shall be a JSON file with VSS syntax with metadata for dbc information.
Please see [mapping documentation](mapping/README.md) for more information.

## Configuring and Using the CAN Provider

The CAN provider support a wide range of configurations.

Please see [CAN Provider Configuration](doc/configuration.md) for more information on how to use the
CAN Provider for different scenarios.

## Using CAN provider as a Docker container

The KUKSA project publish the CAN provider as a Docker container.
Please see [CAN Provider Docker Setup](doc/docker.md) for more information on how to build and use
the CAN Provider as a Docker container.

## Provided can-dump  and DBC files

CAN dump files are usable for test purposes. This repository contain two dump files which are used for testing and also used as basis for the examples in this repository.

[candump-2021-12-08_151848.log.xz](./candump-2021-12-08_151848.log.xz)
is a CAN trace from  2018 Tesla M3 with software 2021.40.6.
This data is interpreted using the [Model3CAN.dbc](./Model3CAN.dbc) [maintained by Josh Wardell](https://github.com/joshwardell/model3dbc).

The canlog in the repo is compressed, to uncompress it (will be around 150MB) do

```console
unxz candump-2021-12-08_151848.log.xz
```

[candump.log](./candump.log):
A smaller excerpt from the above sample, with fewer signals.

## Other topics

* [ELM/OBDLink support](doc/elm.md)
* [SAE-J1939 support](doc/j1939.md)

## Pre-commit set up

This repository is set up to use [pre-commit](https://pre-commit.com/) hooks.
Use `pip install pre-commit` to install pre-commit.
After you clone the project, run `pre-commit install` to install pre-commit into your git hooks.
Pre-commit will now run on every commit.
Every time you clone a project using pre-commit running pre-commit install should always be the first thing you do.
