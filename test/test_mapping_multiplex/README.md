# Test case: multiplexer support in `dbc2vssmapper.py` and `canreader.py`

This test case verifies the evaluation of the `multiplexer` property in the
mapping configuration. It allows the same CAN signal to be mapped to
different VSS data entries depending on the value of a second ("selector")
signal. The multiplexing is configured exclusively in the JSON mapping files;
the DBC file does not contain any native DBC multiplexer syntax
(`M`/`m0`/`SG_MUL_VAL_`).

## Test data

- [`test_mux.dbc`](test_mux.dbc): Defines two CAN messages.
  - `MuxMessage` (frame ID 100) with the signals `MuxSelector` and
    `AlwaysPresent`.
  - `OtherMessage` (frame ID 200) with the signal `OtherSignal`. Used to
    simulate an invalid multiplexer configuration where the selector and data
    signal originate from different messages.
- [`mapping_multiplex.json`](mapping_multiplex.json): Maps the signal
  `AlwaysPresent` twice:
  - `A.AlwaysPresentModeA`, valid when `MuxSelector == 0`.
  - `A.AlwaysPresentModeB`, valid when `MuxSelector == 1`.
  - `A.NoMultiplexer` without a `multiplexer` property, used as a reference
    for the behavior without a condition.
- [`mapping_multiplex_mismatch.json`](mapping_multiplex_mismatch.json): Maps
  `OtherSignal` (frame 200) with a multiplexer referencing `MuxSelector`
  (frame 100), i.e. from a different CAN message.
- [`mapping_multiplex_no_signal.json`](mapping_multiplex_no_signal.json): A
  multiplexer entry without a `signal` property.
- [`mapping_multiplex_invalid_signal.json`](mapping_multiplex_invalid_signal.json):
  A multiplexer entry referencing a signal (`NonExistentSignal`) that does not
  exist in the DBC file.
- [`mapping_multiplex_invalid_value.json`](mapping_multiplex_invalid_value.json):
  A multiplexer entry whose `value` is a string instead of an integer.
- [`mapping_multiplex_no_value.json`](mapping_multiplex_no_value.json): A
  multiplexer entry without a `value` property.

## Requirements

1. The `multiplexer` property of a mapping definition must be correctly
   parsed into a `VSSMapping` object (a `VSSMultiplexer` with signal and
   value) when the mapping is loaded.
2. Mappings without a `multiplexer` property must continue to be supported
   (`multiplexer` is `None`).
3. The same CAN signal may be mapped multiple times, each with a different
   multiplexer value, to different VSS data entries.
4. When parsing, it must be verified that the selector signal and the data
   signal belong to the same CAN message. If this is not the case, the
   mapping must abort with `sys.exit(-1)` and log a corresponding error
   message.
5. When a CAN message is received (`CanReader._process_can_message` /
   `_handle_decoded_frame`), a signal must only be queued for processing if
   the current value of the selector signal matches the value configured in
   the mapping definition.
6. Mappings without a `multiplexer` property must always be queued,
   regardless of the value of any selector signal.
7. A multiplexer entry without a `signal` property, or referencing a signal
   that is not a valid/existing signal on the same CAN message as the data
   signal, must abort parsing with `sys.exit(-1)` and log an error.
8. A multiplexer entry without a `value` property, or whose `value` is not
   an integer, must abort parsing with `sys.exit(-1)` and log an error.
9. The `VSSMultiplexer` class itself must behave correctly in isolation:
   `append()`/`size()`/`get_signal()`/`get_value()` for valid indices, and a
   logged error plus a safe fallback return value (`''` / `-1`) for indices
   that exceed the configured size.

## Test cases and expected results

| Test | Description | Expected result |
|------|-------------|------------------|
| `test_multiplexer_is_parsed_for_mapping` | Loads `mapping_multiplex.json` and reads the mapping for `A.AlwaysPresentModeA`. | `mapping.multiplexer` is set, referencing signal `MuxSelector` with value `0`. |
| `test_multiplexer_is_none_when_not_configured` | Reads the mapping for `A.NoMultiplexer`. | `mapping.multiplexer` is `None`. |
| `test_multiplexer_allows_multiple_mappings_for_same_signal` | Reads all mappings for the DBC signal `AlwaysPresent`. | Two mappings exist (`A.AlwaysPresentModeA` with value `0`, `A.AlwaysPresentModeB` with value `1`). |
| `test_multiplexer_signal_and_data_signal_must_share_can_frame` | Loads `mapping_multiplex_mismatch.json`, in which the selector and data signal originate from different messages. | The `Mapper` constructor terminates the program with `sys.exit(-1)` and logs an error message stating that both signals do not belong to the same CAN message. |
| `test_multiplexer_fails_when_signal_is_missing` | Loads `mapping_multiplex_no_signal.json`, in which the multiplexer entry has no `signal` property. | The `Mapper` constructor terminates with `sys.exit(-1)` and logs "No signal provided in multiplexer for AlwaysPresent". |
| `test_multiplexer_fails_when_signal_is_not_valid` | Loads `mapping_multiplex_invalid_signal.json`, in which the multiplexer references the non-existing signal `NonExistentSignal`. | The `Mapper` constructor terminates with `sys.exit(-1)` and logs that `AlwaysPresent` and `NonExistentSignal` do not belong to the same CAN message. |
| `test_multiplexer_fails_when_value_is_not_an_integer` | Loads `mapping_multiplex_invalid_value.json`, in which `value` is the string `"0"`. | The `Mapper` constructor terminates with `sys.exit(-1)` and logs "Value for multiplexer in signal AlwaysPresent is not an integer". |
| `test_multiplexer_fails_when_value_is_missing` | Loads `mapping_multiplex_no_value.json`, in which the multiplexer entry has no `value` property. | The `Mapper` constructor terminates with `sys.exit(-1)` and logs "No value provided in multiplexer for AlwaysPresent". |
| `test_vss_multiplexer_append_and_size` | Appends multiple signal/value pairs directly to a `VSSMultiplexer` instance. | `size()` and the getters return the appended signals/values for valid indices. |
| `test_vss_multiplexer_get_signal_out_of_range` | Calls `get_signal()` with an index beyond the configured size. | Returns `''` and logs "Access to multiplexer exceeds size". |
| `test_vss_multiplexer_get_value_out_of_range` | Calls `get_value()` with an index beyond the configured size. | Returns `-1` and logs "Access to multiplexer exceeds size". |
| `test_reader_queues_signal_matching_multiplexer_value` | Simulates receiving a message with `MuxSelector == 0` for a mapping that is only valid for `MuxSelector == 0`. | The signal is queued (`queue.put` called once), with the correct `dbc_name` and `vss_name`. |
| `test_reader_discards_signal_not_matching_multiplexer_value` | Simulates receiving a message with `MuxSelector == 0` for a mapping that is only valid for `MuxSelector == 1`. | The signal is discarded, `queue.put` is not called. |
| `test_reader_queues_signal_without_multiplexer_regardless_of_selector` | Simulates receiving a message for a mapping without a `multiplexer` property. | The signal is queued regardless of the value of `MuxSelector`. |

## Running the tests

```bash
pytest test/test_mapping_multiplex -v
```
