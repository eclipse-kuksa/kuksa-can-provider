# Mapping between VSS and DBC

## Introduction

The DBC feeder use JSON for configuring how DBC data shall be mapped to/from VSS signals.
The JSON file is supposed to contain valid VSS JSON, so that it theoretically also could be
used as configuration file for [KUKSA.val](https://github.com/eclipse/kuksa.val)
(kuksa-val-server or kuksa-databroker).
In addition to this DBC-specific information is needed for those signals that are of interest
for the DBC feeder, like in the example below.


```json
 "Pan": {
                    "datatype": "int8",
                    "dbc2vss": {
                      "interval_ms": 100,
                      "signal": "DBC_Signal_For_Actual_Pan",
                      "transform": {
                        "math": "floor((x*40)-100)"
                      }
                    },
                    "description": "Mirror pan as a percent. 0 = Center Position. 100 = Fully Left Position. -100 = Fully Right Position.",
                    "max": 100,
                    "min": -100,
                    "type": "actuator",
                    "unit": "percent",
                    "vss2dbc": {
                      "signal": "DBC_Signal_For_Wanted_Pan",
                      "transform": {
                        "math": "(x+100)/40"
                      }
                    }
 }
```

Two types of mapping exists.
`dbc2vss`(synonym `dbc` for historical reasons) specifies mapping from DBC to VSS.
The DBC value is read and injected to KUKSA.val as actual value.
`vss2dbc` specifies mapping from VSS to DBC.
The VSS target value is read and injected to DBC.

This is built on the assumption that the DBC provider always send target values to CAN, but read actual values.
Having separate configurations (`dbc2vss` and `vss2dbc`) is needed as wanted value and actual value never are sent
by the same DBC signal, they are not even part of the same CAN-frame.

*This means that `vss2dbc` only can be used for actuators, as only actuators have target values!*

## Example mapping files

Example mapping files for various VSS versions can be found in this folder.
By default dbc2val uses the `vss_dbc.json` file for the newest available VSS release.
If your KUKSA.val Server or Databroker use a different VSS-version then you should select a mapping file matching
that version.

## Creating a mapping file

There are two methods for creating a mapping file. The first method is to manually add DBC
information to an existing VSS file in JSON format. It is important that the VSS file is compatible
with the VSS file used by KUKSA.val. One way to ensure this is to use the same JSON file for both
KUKSA.val and DBC Feeder. If for example your KUKSA.val (kuksa-val-server or kuksa-databroker)
instance uses one of the JSON files in the [KUKSA.val repository](https://github.com/eclipse/kuksa.val/tree/master/data/vss-core)
then you can annotate that file and use the annotated file in both KUKSA.val and the feeder.

Annotating an existing VSS JSON file has however some drawbacks. If the JSON file is regenerated
to support a new VSS version then the annotations must be manually transferred to the new VSS JSON.
An alternative to this is to use the [VSS Overlay concept](https://covesa.github.io/vehicle_signal_specification/rule_set/overlay/)
described below.


### Generating mapping file based on overlay

The idea of overlays is to specify additions in a separate file and then apply this on top of
a VSS tree. An example dbc overlay exists in `dbc_overlay.vspec`.
An overlay file is a VSS `*.vspec` file, which shall in itself be a valid VSS tree.
The VSS tooling requires that type and datatype are defined in addition to the DBC specific data
needed by the DBC feeder, like in the example below:

```yaml
Vehicle.Speed:
  type: sensor
  datatype: float
  dbc2vss:
    signal: DI_uiSpeed
    interval_ms: 5000
```

To create a VSS JSON file considering the overlay file [vss-tools](https://github.com/COVESA/vss-tools)
must be used. Two alternatives exist. The first alternative is to use raw `*.vspec` file in the
[VSS repository](https://github.com/COVESA/vehicle_signal_specification) as base. To use that method
you must clone the repository, update submodules and then generate VSS JSON like in the example below:

```
git submodule update --init
vss-tools/vspec2json.py -e vss2dbc,dbc2vss,dbc -o dbc_overlay.vspec -u spec/units.yaml  --json-pretty ./spec/VehicleSignalSpecification.vspec vss_dbc.json
```

An alternative approach is download the `*.yaml` files from an [official VSS release](https://github.com/COVESA/vehicle_signal_specification/releases)
and use the included Yaml file as base.

```
vss-tools/vspec2json.py -e vss2dbc,dbc2vss,dbc -o dbc_overlay.vspec -u units.yaml --json-pretty vss_rel_4.0.yaml vss_dbc.json
```

_Note: The dbc feeder relies on correct VSS information in the JSON file. This means that if KUKSA.val Databroker VSS JSON file updated, then the file used in DBC-feeder possibly needs to be updated as well._


## Mapping syntax

The syntax for a DBC definition of a signal in an overlay is specified below.
The syntax if information instead is added directly to a VSS JSON file is similar, but not described here.
See `vss_dbc.json` in mapping folder for examples on DBC specification in JSON format.
Search for `dbc` to find the signals where DBC mapping has been defined.
If a signal does not have DBC mapping (`dbc`, `vss2dbc`, or `dbc2vss` it will be ignored by the DBC feeder.

Syntax

```yaml
<VSS Signal name>:
  type: <VSS type>
  datatype: <VSS datatype>
  vss2dbc:
    signal: <DBC signal name>
    [transform: ...]
  dbc2vss:
    signal: <DBC signal name>
    [interval_ms: <interval in milliseconds>]
    [on_change: {true|false}]
    [transform: ...]
```

(`dbc` can be used as synonym for `dbc2vss`)

Specifying DBC signal name is mandatory. It must correspond to a DBC signal name defined in a DBC file.
By default the DBC feeder use the [Model3CAN.dbc](../Model3CAN.dbc) example file.

`interval_ms` and `on_change` are optional and control under which conditions a value shall be forwarded.
The `interval_ms` value indicates the minimum interval between signals in milliseconds.
The `on_change: true` argument specifies that the VSS signal only shall be sent if the DBC value has changed.
If none of them are specified it corresponds to `interval_ms: 1000, on_change: false`.
If only `on_change: true` is specified it corresponds to `interval_ms: 0, on_change: true`

The `transform` entry can be used to specify how DBC values shall be mapped to VSS values.
If transform is not specified values will be transformed as is.

*Note: For `vss2dbc` the attributes`interval_ms` and `on_change` are currently ignored.*
*Instead the dbcfeeder send updated VSS values to CAN whenever it get a value from databroker!*

### Math Transformation

A Math transformation can be defined by the `math` attribute.
It accepts [py-expression-eval](https://github.com/AxiaCore/py-expression-eval/) formulas as argument.
The DBC feeder expects the DBC value to be represented as `x`.

When evaluating what transformation is needed one must study both the DBC signal and the VSS signal. An example is given below for mirror tilt of left mirror.

**DBC**

The signal `VCLEFT_mirrorTiltYPosition` provides mirror tilt.

```
SG_ VCLEFT_mirrorTiltYPosition : 41|8@1+ (0.02,0) [0|5] "V"  Receiver
```

An introduction to DBC file syntax can be found [here](https://www.csselectronics.com/pages/can-dbc-file-database-intro).
The specification above shows that on CAN the tilt is represented as 0-5 Volts.
The value is sent with a scaling of 0.02 and uses 8 bits, i.e. 5 Volts is transmitted as 250,
but that information is not needed when configuring the mapping of the kuksa-can-provider,
as the transformation defined in the DBC is performed automatically when CAN frames are read.
For the input to the mapping you will need to consider just a value between 0 and 5 V in this example.

**VSS**

The corresponding signal in VSS uses -100 percent to +100 percent as range and int8 as datatype:

```
Vehicle.Body.Mirrors.DriverSide.Tilt:
  datatype: int8
  unit: percent
  min: -100
  max: 100
  type: actuator
  description: Mirror tilt as a percent. 0 = Center Position. 100 = Fully Upward Position. -100 = Fully Downward Position.
  ```

With an assumptions that 5 Volts corresponds to fully upward (+100%) and 0 Volts corresponds to
fully downward (-100%) then one could define mapping like in the example below.
This results in that kuksa-can-provider will take the value from the CAN signal and inject to Databroker as actual value.

```yaml
  Vehicle.Body.Mirrors.DriverSide.Tilt:
  datatype: int8
  type: actuator
  dbc2vss:
    signal: VCLEFT_mirrorTiltYPosition
    interval_ms: 100
    transform:
      math: "floor((x*40)-100)"
```

I.e. 2 Volts corresponds to `(2*40)-100` = -20%.

Transformation may fail. Typical reasons may include that the DBC value is not numerical,
or that the transformation fails on certain values like division by zero.
If transformation fails the received CAN signal will be ignored.

### Mapping Transformation

A Mapping transformation can be specified with the `mapping` attribute.
It must consist of a list of `from`/`to` pairs like in the example below.
When a DBC value is received the feeder will look for a matching `from` value in the list,
and the corresponding `to` value will be sent to KUKSA.val.

```yaml
Vehicle.Powertrain.Transmission.CurrentGear:
  type: sensor
  datatype: int8
  dbc:
    signal: DI_gear
    transform:
       mapping:
        - from: DI_GEAR_D
          to: 1
        - from: DI_GEAR_P
          to: 0
        - from: DI_GEAR_INVALID
          to: 0
        - from: DI_GEAR_R
          to: -1
```

If no matching value is found the signal will be ignored.
It is allowed (but not recommended) to have multiple entries for the same from-value.
In that case the feeder will arbitrarily select one of the mappings.

The from/to values must be compatible with DBC and VSS type respectively.
Numerical values must be written without quotes.
For boolean signals `true` and `false` without quotes is recommended, as that is valid values in both Yaml and JSON.
If using Yaml (*.vspec) as source format quoting string values is optional.
Quotes may however be needed if the value otherwise could be misinterpreted as a [Yaml 1.1](https://yaml.org/type/bool.html)
literal. Typical examples are values like `yes` which is a considered as a synonym to `true`.
If using JSON all strings must be quoted.

## Evaluation Logics

For each VSS-DBC combination the feeder stores a timestamp and a value.
They are used for deciding if a signal shall be forwarded to KUKSA.val.
When a DBC signal matching a VSS signal is received the following logic applies:

* If there is a time condition the time of the observation is compared with the stored value.
  If the time difference is bigger than the explicitly or implicitly defined interval
  the stored time for the VSS-DBC combination is updated
  and evaluation continue with the next step.
* The DBC value is then transformed to VSS value. If transformation fails the signal is ignored.
* After transformation, if there is a change condition, the stored value is compared with the
  new value. If they are equal the signal is ignored. If they differ the stored value is updated.
* If all checks have passed the transformed value is transferred to KUKSA.val.

This means that the interval specified by `interval_ms` does not guarantee that the VSS signal
will be sent to KUKSA.val with exactly that interval, it only guarantees that there on average
will be at least that interval between signals. Due to internal queuing the interval between
actual transmissions may sometimes be less than the specified interval.

## Migrating old format

Previously DBC feeder used a different configuration format no longer supported.
If you use the old Yaml format you must convert it to the new format.
Below are examples on how that can be done.
All examples are shown as if using vspec overlays to define the mapping.
If adding mapping directly to JSON see examples in `vss_dbc.json` in mapping folder, search for `dbc`.

### Limitations

There are some minor changes in what constructs that are possible to specify in the mapping file:

* "Partial mapping" is not supported in the new format.
  That was a feature where the DBC value would be sent as is if no matching mapping was found.
  The work around is to specify mapping for all possible DBC values.
* It was previously theoretically possible to have a mapping multiple DBC signals to the same VSS signal.
  That is no longer possible as each VSS signal must appear at most once in the new format.

### Math Migration

Migrating Math-mapping is straightforward as shown in this example:

Old format:

```yaml
SteeringAngle129:
  minupdatedelay: 100
  targets:
    Vehicle.Chassis.SteeringWheel.Angle:  # taken from https://github.com/COVESA/vehicle_signal_specification/blob/master/spec/Chassis/Chassis.vspec
      vss:
        datatype: int16
        type: sensor
        unit: degrees
        description: Steering wheel angle. Positive = degrees to the left. Negative = degrees to the right.
      transform:
        math: "floor(x+0.5)"
```

New vspec overlay format:

```yaml
Vehicle.Chassis.SteeringWheel.Angle:
  type: sensor
  datatype: int16
  dbc:
    interval_ms: 100
    signal: SteeringAngle129
    transform:
      math: "floor(x+0.5)"
```

### Mapping Migration

Migrating mapping is also relative straightforward.
The example below also shows how to migrate a mapping where one DBC signal maps to multiple VSS signals.

Old format:

```yaml
DI_gear:
  minupdatedelay: 100
  targets:
    Vehicle.Powertrain.Transmission.CurrentGear:  # taken from https://github.com/COVESA/vehicle_signal_specification/blob/master/spec/Powertrain/Transmission.vspec
      vss:
        datatype: int8
        type: sensor
        unit: none
        description: The current gear. 0=Neutral, 1/2/..=Forward, -1/-2/..=Reverse
      transform:
        fullmapping:
          DI_GEAR_D: 1
          DI_GEAR_INVALID: 0
          DI_GEAR_P: 0
          DI_GEAR_R: -1
    Vehicle.Powertrain.Transmission.IsParkLockEngaged:  # taken from https://github.com/COVESA/vehicle_signal_specification/blob/master/spec/Powertrain/Transmission.vspec
      vss:
        datatype: boolean
        type: sensor
        unit: none
        description: Is the transmission park lock engaged or not. False = Disengaged. True = Engaged.
      transform:
        fullmapping:
          DI_GEAR_D: "false"
          DI_GEAR_INVALID: "false"
          DI_GEAR_P: "true"
          DI_GEAR_R: "false"
```

New vspec overlay format:

```yaml
Vehicle.Powertrain.Transmission.CurrentGear:
  type: sensor
  datatype: int8
  dbc:
    interval_ms: 100
    signal: DI_gear
    transform:
       mapping:
        - from: DI_GEAR_D
          to: 1
        - from: DI_GEAR_P
          to: 0
        - from: DI_GEAR_INVALID
          to: 0
        - from: DI_GEAR_R
          to: -1

Vehicle.Powertrain.Transmission.IsParkLockEngaged:
  type: sensor
  datatype: boolean
  dbc:
    interval_ms: 100
    signal: DI_gear
    transform:
       mapping:
        - from: DI_GEAR_D
          to: false
        - from: DI_GEAR_P
          to: true
        - from: DI_GEAR_INVALID
          to: false
        - from: DI_GEAR_R
          to: false
```
