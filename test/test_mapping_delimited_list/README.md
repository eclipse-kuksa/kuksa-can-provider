# Test case: delimiter-separated list support in `dbc2vssmapper.py`

This test case verifies parsing and transformation of a list-valued DBC signal
into one VSS string value. The mapper receives the DBC signal as a list of
integer character codes, joins those characters, splits the resulting string
at the configured delimiter, and selects an item by its zero-based index.

## Test data

- `Model3CAN.dbc` supplies the existing `S1` signal used to construct mappings.
- The test module writes small JSON mapping files into pytest's temporary
  directory. This allows valid and invalid `delimited_list` definitions to be
  tested without adding redundant static mapping fixtures.
- Test values are encoded as lists of character codes to match the value shape
  produced by the J1939 multipacket reader.

## Requirements

1. A valid `delimited_list` object must be parsed and attached to its
   `VSSMapping` with the configured delimiter and index.
2. `delimited_list` is supported for `dbc2vss` string mappings without an
   explicit transformation, when the decoded DBC value is a list of integer
   character codes.
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
