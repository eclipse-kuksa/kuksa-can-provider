# Test case: datetime transformation support in `dbc2vssmapper.py`

This test case verifies parsing and runtime transformation for `transform.datetime`
with `format: iso8601` in the `dbc2vss` direction. Datetime transformations are
not supported in the `vss2dbc` direction and must be rejected while loading the
mapping.

The mapper validates the datetime mapping definition when loading the mapping
file. Runtime tests call `transform_frame` with a `VSSObservation` containing a
dictionary of decoded date/time values; they do not exercise CAN decoding.
Reader tests in `../test_readers/test_readers.py` additionally exercise
`CanReader._process_can_message` with mocked decoding and call
`_handle_decoded_frame` directly for input-validation matrices. Direct handler
calls ensure unexpected exceptions cannot be hidden by the outer CAN error
handler. No physical or virtual CAN bus is required.

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
- The reader validation fixture adds `LocalHourOffset=2` and
  `LocalMinuteOffset=30`, with explicit DBC bounds for all eight signals.
  Each case changes or removes exactly one input, leaving all other values
  valid. Except when testing `Seconds` itself, the trigger remains valid.
  These tests use decoded physical values, not encoded CAN bytes.

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
20. Before queueing a datetime observation, the reader must validate every
    configured input against its source signal's DBC minimum and maximum,
    including non-trigger signals and both optional offset inputs when bound.
21. If any configured input is missing or outside its DBC bounds, the entire
    datetime observation must be discarded: the queue receives no observation.
    A valid `Seconds` trigger must not bypass another input's validation.
22. DBC bounds are inclusive. The reader must preserve valid boundary values
    unchanged, including fractional seconds and days; it must not clamp,
    normalize, or modify the decoded dictionary.
23. Calendar validity is checked by the mapper, separately from DBC bounds.
    Impossible dates and clock values return `None` and log a creation error.
    A DBC-valid day such as `0.25` can therefore pass reader validation while
    still failing calendar construction. Reader acceptance alone does not
    guarantee a valid timestamp.
24. The mapper must return `None` and log an extraction error for missing
    configured fields or unusable values (`None`, nonnumeric text, lists),
    including offset fields, without raising an exception to its caller.
25. The mapper must reject total UTC offsets outside the open interval
    `(-24 hours, +24 hours)`. Valid positive, negative, zero, and extreme
    representable offsets must produce matching ISO-8601 suffixes.
26. DBC range validation must precede offset combination: a minute offset of
    `130` with an hour offset of `2` must be discarded by the reader, not
    normalized to `+04:10`. Likewise, an unavailable Year byte decoding to
    `2240` must not create a timestamp when the DBC maximum is `2235`.

  ## Reader input matrix

  The fixture uses a J1939-style profile with hour offsets bounded to `[-23, 23]`.
  Bounds are supplied by the message definition, not hard-coded in production;
  other DBC profiles may define different limits. Every row is tested with each
  listed invalid value, with the field missing, and with both inclusive bounds
  as positive controls. Expected results are no queued observation for invalid
  or missing inputs, and exactly one unchanged frame observation for boundaries.

  | Signal | Inclusive DBC bounds | Invalid decoded values tested |
  |--------|----------------------|-------------------------------|
  | `Year` | `1985..2235` | `1984`, `2236`, `2240` (`0xff`) |
  | `Month` | `1..12` | `0`, `13`, `255` (`0xff`) |
  | `Day` | `0.25..31.75` | `0`, `32`, `63.75` (`0xff`) |
  | `Hours` | `0..23` | `-1`, `24`, `255` (`0xff`) |
  | `Minutes` | `0..59` | `-1`, `60`, `255` (`0xff`) |
  | `Seconds` | `0..59.75` | `-0.25`, `60`, `63.75` (`0xff`) |
  | `LocalHourOffset` | `-23..23` | `-24`, `24`, `130` (`0xff`) |
  | `LocalMinuteOffset` | `-59..59` | `-60`, `60`, `130` (`0xff`) |

  These are representatives of each invalid range class, not an enumeration of
  all possible numeric values. Transformer tests separately cover calendar and
  type errors, because the reader's bounds check is not a calendar/type parser.

## Test cases and expected results

| Test | Description | Expected result |
|------|-------------|-----------------|
| `test_datetime_transform_is_parsed_into_mapping` | Loads a valid `datetime` transform. | Mapping contains the configured datetime transform including all input bindings. |
| `test_datetime_transform_frame_to_iso8601` | Transforms a valid decoded datetime frame. | Returns the expected ISO-8601 string. |
| `test_datetime_transform_normalizes_rounded_seconds` | Uses `59.75` seconds in four parameterized cases: minute rollover at `2026-10-05T14:07`, day rollover at `2026-10-05T23:59`, month rollover at `2026-10-31T23:59`, and year rollover at `2026-12-31T23:59`. | Returns `2026-10-05T14:08:00`, `2026-10-06T00:00:00`, `2026-11-01T00:00:00`, and `2027-01-01T00:00:00`, respectively; the observation is not dropped. |
| `test_datetime_transform_supports_fractional_day` | Uses half a day and a fractional day with a sub-hour remainder. | The fractional day is reflected in the output timestamp to the nearest second, including remaining minutes. |
| `test_datetime_transform_supports_timezone_offset_inputs` | Uses `(hours, minutes)` of `(2,30)`, `(-2,-30)`, `(0,0)`, `(23,59)`, `(-23,-59)`. | Returns suffixes `+02:30`, `-02:30`, `+00:00`, `+23:59`, `-23:59`. |
| `test_datetime_transform_invalid_frame_values_return_none` | Years `0/10000`, months `0/13`, days `0/32`, April 31, February 29 in 2026, February 30 in 2024, hours `-1/24`, minutes `-1/60`. | Returns `None` and logs datetime creation error in all 13 cases. |
| `test_datetime_transform_missing_frame_input_returns_none` | Removes each of the six required fields and two configured offset fields individually. | Returns `None` and logs datetime input extraction error in all eight cases. |
| `test_datetime_transform_invalid_input_types_return_none` | Assigns `None`, `"invalid"`, and `[]` to each of the eight fields. | Returns `None` and logs an extraction error in all 24 cases. |
| `test_datetime_transform_invalid_timezone_returns_none` | Offset pairs `(24,0)`, `(-24,0)`, `(23,60)`, `(-23,-60)`, `(130,0)`, `(-125,0)`. | Returns `None` and logs an extraction error for all six unrepresentable total offsets. |
| `test_invalid_datetime_definitions_are_rejected` | Parameterized invalid mapping definitions (type/format/inputs/key validation). | Mapper terminates with `sys.exit(-1)` and logs the expected validation error. |
| `test_datetime_transform_is_rejected_for_vss2dbc` | Defines an `iso8601` datetime transform for a `vss2dbc` actuator mapping. | Mapper terminates with `sys.exit(-1)` and logs that datetime transformation is unsupported for `vss2dbc`. |
| `TestCanReader.test_process_can_message_queues_datetime_frame` (`../test_readers/test_readers.py`) | Processes a known CAN message with six decoded date/time fields and a datetime mapping triggered only by `Seconds`. | Queues exactly one observation with `dbc_name == "Seconds"`, `vss_name == "Vehicle.CurrentDateTime"`, `raw_value` equal to the complete decoded frame (including unchanged `Seconds=59.75`), and `observation == "frame"`. |
| `TestCanReader.test_datetime_frame_rejects_out_of_range_input` | All 24 invalid values in the reader matrix, including unavailable bytes and non-trigger offsets. | No observation is queued. |
| `TestCanReader.test_datetime_frame_rejects_missing_input` | Removes each of the eight configured inputs individually. | No observation is queued in all eight cases. |
| `TestCanReader.test_datetime_frame_accepts_dbc_boundary` | Sets each of the eight inputs to its minimum and maximum individually. | Exactly one unchanged frame observation is queued in all 16 cases. |

## Running the tests

```bash
python -m pytest test/test_mapping_datetime test/test_readers/test_readers.py -v
```
