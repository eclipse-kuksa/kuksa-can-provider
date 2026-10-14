# Test case: datetime transformation support in `dbc2vssmapper.py`

This test case verifies parsing and runtime transformation for `transform.datetime`
with `format: iso8601` in the `dbc2vss` direction. Datetime transformations are
not supported in the `vss2dbc` direction and must be rejected while loading the
mapping.

The mapper validates the datetime mapping definition when loading the mapping
file. Runtime tests call `transform_frame` with a `VSSObservation` containing a
dictionary of decoded date/time values; they do not exercise CAN decoding.
An additional reader integration test in `../test_readers/test_readers.py`
calls `CanReader._process_can_message` and verifies the queued datetime
observation. CAN decoding is mocked; no physical or virtual CAN bus is required.

## Test data

- `Model3CAN.dbc` is loaded because mapper setup requires a DBC database.
- The `dbc2vss` runtime tests use `S1` as a synthetic mapping name and construct
  their `VSSObservation` values directly. The `vss2dbc` rejection test uses the
  DBC signal `UI_audioActive` so mapping validation reaches the datetime check.
- The test module writes compact JSON mappings into pytest temporary folders,
  which allows each validation scenario to define only the datetime properties
  relevant for that case.
- Runtime transformation tests construct `VSSObservation` objects with
  `raw_value` dictionaries representing a decoded frame.
- The reader integration test uses a synthetic `DateTimeMessage` with decoded
  values `Year=2026`, `Month=10`, `Day=14`, `Hours=23`, `Minutes=59`, and
  `Seconds=59.75`. Only `Seconds` triggers a datetime mapping to
  `Vehicle.CurrentDateTime`; the mapper lookup and queue are mocked.

## Requirements

1. A `transform.datetime` definition must be an object.
2. `transform.datetime.format` is required and must be a string.
3. Only `format: iso8601` is supported.
4. For `iso8601`, `inputs` is required and must be an object.
5. Required `inputs` keys are: `year`, `month`, `day`, `hour`, `minute`,
   `second`.
6. Optional `inputs` keys are: `local_hour_offset`, `local_minute_offset`.
7. Unsupported or missing `inputs` keys must reject the mapping and terminate
   parsing with `sys.exit(-1)`.
8. Each `inputs` value must be a string naming a source signal in the decoded
   frame.
9. A valid datetime frame must be transformed to an ISO-8601 string.
10. A fractional `day` value must be added as elapsed time, preserving its
  hours, minutes, and seconds to the nearest second.
11. Optional local offset inputs must be converted to timezone information and
    reflected in the produced ISO-8601 value.
12. Invalid frame values (for example impossible calendar values) must not crash
    processing; transformation returns `None` and logs an error.
13. Missing frame inputs referenced by `inputs` must not crash processing;
    transformation returns `None` and logs an error.
14. Datetime transformations are supported only for `dbc2vss`; an
  `iso8601` datetime transform in `vss2dbc` must reject the mapping with
  `sys.exit(-1)`.
15. The `iso8601` format is a semantic token for producing an ISO-8601 value,
  not a `strftime` format string.
16. Seconds must be rounded to the nearest whole second and normalized using
    `timedelta`. A valid J1939 TD seconds value of `59.75` rounds to `60` and
    must carry into the next minute, including day, month, and year transitions,
    rather than rejecting the observation.
  17. For a datetime mapping, the reader must queue the complete decoded frame
    dictionary as `VSSObservation.raw_value`, not just the triggering signal's
    scalar value. Values must remain unchanged for subsequent transformation.
  18. A queued datetime observation must use `observation == "frame"` so it is
    identified as a frame observation rather than a single-signal observation.
  19. With one matching datetime mapping and no mappings for the other frame
    signals, the reader must queue exactly one observation. Its `dbc_name` and
    `vss_name` must identify the triggering signal and configured VSS target.

## Test cases and expected results

| Test | Description | Expected result |
|------|-------------|-----------------|
| `test_datetime_transform_is_parsed_into_mapping` | Loads a valid `datetime` transform. | Mapping contains the configured datetime transform including all input bindings. |
| `test_datetime_transform_frame_to_iso8601` | Transforms a valid decoded datetime frame. | Returns the expected ISO-8601 string. |
| `test_datetime_transform_normalizes_rounded_seconds` | Uses `59.75` seconds in four parameterized cases: minute rollover at `2026-10-05T14:07`, day rollover at `2026-10-05T23:59`, month rollover at `2026-10-31T23:59`, and year rollover at `2026-12-31T23:59`. | Returns `2026-10-05T14:08:00`, `2026-10-06T00:00:00`, `2026-11-01T00:00:00`, and `2027-01-01T00:00:00`, respectively; the observation is not dropped. |
| `test_datetime_transform_supports_fractional_day` | Uses half a day and a fractional day with a sub-hour remainder. | The fractional day is reflected in the output timestamp to the nearest second, including remaining minutes. |
| `test_datetime_transform_supports_timezone_offset_inputs` | Uses local hour/minute offset inputs. | Returns ISO-8601 value with matching timezone offset. |
| `test_datetime_transform_invalid_frame_values_return_none` | Uses impossible calendar values. | Returns `None` and logs datetime creation error. |
| `test_datetime_transform_missing_frame_input_returns_none` | References a missing frame key in `inputs`. | Returns `None` and logs datetime input extraction error. |
| `test_invalid_datetime_definitions_are_rejected` | Parameterized invalid mapping definitions (type/format/inputs/key validation). | Mapper terminates with `sys.exit(-1)` and logs the expected validation error. |
| `test_datetime_transform_is_rejected_for_vss2dbc` | Defines an `iso8601` datetime transform for a `vss2dbc` actuator mapping. | Mapper terminates with `sys.exit(-1)` and logs that datetime transformation is unsupported for `vss2dbc`. |
| `TestCanReader.test_process_can_message_queues_datetime_frame` (`../test_readers/test_readers.py`) | Processes a known CAN message with six decoded date/time fields and a datetime mapping triggered only by `Seconds`. | Queues exactly one observation with `dbc_name == "Seconds"`, `vss_name == "Vehicle.CurrentDateTime"`, `raw_value` equal to the complete decoded frame (including unchanged `Seconds=59.75`), and `observation == "frame"`. |

## Running the tests

```bash
python -m pytest test/test_mapping_datetime test/test_readers/test_readers.py -v
```
