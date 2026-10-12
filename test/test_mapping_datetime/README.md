# Test case: datetime transformation support in `dbc2vssmapper.py`

This test case verifies parsing and runtime transformation for `transform.datetime`
with `format: iso8601`.

The mapper validates the datetime mapping definition when loading the mapping
file. Runtime tests call `transform_frame` with a `VSSObservation` containing a
dictionary of decoded date/time values; they do not exercise CAN decoding.

## Test data

- `Model3CAN.dbc` is loaded because mapper setup requires a DBC database, but it
  does not contain the test signal `S1`. `S1` is a synthetic mapping name used
  by the tests, which construct their `VSSObservation` values directly.
- The test module writes compact JSON mappings into pytest temporary folders,
  which allows each validation scenario to define only the datetime properties
  relevant for that case.
- Runtime transformation tests construct `VSSObservation` objects with
  `raw_value` dictionaries representing a decoded frame.

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

## Test cases and expected results

| Test | Description | Expected result |
|------|-------------|-----------------|
| `test_datetime_transform_is_parsed_into_mapping` | Loads a valid `datetime` transform. | Mapping contains the configured datetime transform including all input bindings. |
| `test_datetime_transform_frame_to_iso8601` | Transforms a valid decoded datetime frame. | Returns the expected ISO-8601 string. |
| `test_datetime_transform_supports_fractional_day` | Uses half a day and a fractional day with a sub-hour remainder. | The fractional day is reflected in the output timestamp to the nearest second, including remaining minutes. |
| `test_datetime_transform_supports_timezone_offset_inputs` | Uses local hour/minute offset inputs. | Returns ISO-8601 value with matching timezone offset. |
| `test_datetime_transform_invalid_frame_values_return_none` | Uses impossible calendar values. | Returns `None` and logs datetime creation error. |
| `test_datetime_transform_missing_frame_input_returns_none` | References a missing frame key in `inputs`. | Returns `None` and logs datetime input extraction error. |
| `test_invalid_datetime_definitions_are_rejected` | Parameterized invalid mapping definitions (type/format/inputs/key validation). | Mapper terminates with `sys.exit(-1)` and logs the expected validation error. |

## Running the tests

```bash
pytest test/test_mapping_datetime -v
```
