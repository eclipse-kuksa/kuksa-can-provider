# Test case: delimiter-separated list support in `dbc2vssmapper.py`

This test case verifies parsing of `delimited_list` mapping definitions and
transformation of character-code lists into one VSS string value. It calls
`VSSMapping.transform_value()` directly with synthetic values; it does not
decode a CAN frame or a signal from the DBC file. The transformation joins the
character codes, splits the resulting string at the configured delimiter, and
selects an item by its zero-based index.

## Test data

- `Model3CAN.dbc` is passed to `Mapper` and loaded by its `DBCParser` base class,
   because constructing a mapper requires at least one CAN database. It does not
   provide the test signal: there is no signal named `S1` in this DBC. The
   mapping parser accepts the configured `S1` anyway; its lookup in the database
   finds no messages, which is not an error for these tests.
- For each test, the test module writes a small JSON mapping to pytest's
   temporary directory. That mapping associates the synthetic signal name `S1`
   with `A.DelimitedValue`, optionally including a `delimited_list` definition.
- Tests retrieve that mapping with `get_dbc2vss_mapping()` and call
   `transform_value()` directly. They do not decode CAN frames or obtain the
   values from `Model3CAN.dbc`.
- Input values are built in the test as lists of `ord(character)` values. This
   simulates the character-code list shape handled for J1939 multipacket data;
   the configured delimiter and index are then checked against those values.

## Requirements

1. A valid `delimited_list` object must be parsed and attached to its
   `VSSMapping` with the configured delimiter and index.
2. For `dbc2vss` string mappings without an explicit transformation,
   `transform_value()` must handle an input list of integer character codes.
   This unit test supplies that list directly; it does not test DBC decoding or
   the J1939 reader path.
3. The list of character codes must be joined into a string, split using the
   configured delimiter, and selected using a zero-based index.
4. Multi-character delimiters and empty list items must be preserved during
   splitting and item selection.
5. If the configured index is outside the split list, the mapper must log a
   warning and return an empty string.
6. Without `delimited_list`, existing string conversion must continue to join
   the character codes without selecting an item.
7. A `delimited_list` option must not change values mapped to a non-string VSS
   datatype; the original list value is returned.
8. The `delimited_list` definition must be an object with a non-empty string
   `delimiter` and a non-negative integer `index`. Missing or invalid
   properties, including a boolean index, must log an error and abort mapping
   construction with `sys.exit(-1)`.

## Test cases and expected results

| Test | Description | Expected result |
|------|-------------|-----------------|
| `test_delimited_list_selects_zero_based_item` | Selects first, middle, and final items; also tests a multi-character delimiter and an empty item. | Each configured zero-based item is returned exactly, including an empty string item. |
| `test_delimited_list_out_of_range_logs_warning_and_returns_empty_string` | Requests an item beyond the split list. | Returns `""` and logs the out-of-range warning. |
| `test_delimited_list_is_parsed_into_mapping` | Loads a valid mapping definition. | `VSSMapping.delimited_list` contains the configured delimiter and index. |
| `test_list_without_delimited_list_keeps_legacy_join_behavior` | Transforms a string-valued character list without the option. | Returns the joined string without splitting it. |
| `test_delimited_list_does_not_change_non_string_values` | Transforms a character list mapped to a non-string datatype with the option configured. | Returns the original list unchanged. |
| `test_invalid_delimited_list_definition_is_rejected` | Tests a non-object, missing properties, invalid or empty delimiter, string or negative index, and boolean index. | Each definition logs the expected error and exits with code `-1`. |
| `test_delimited_list_get_item_handles_out_of_range_index` | Calls `VSSDelimitedList.get_item()` directly for an absent item. | Returns `(False, "")`. |

## Running the tests

```bash
pytest test/test_mapping_delimited_list -v
```
