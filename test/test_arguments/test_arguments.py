########################################################################
# Copyright (c) 2023 Contributors to the Eclipse Foundation
#
# See the NOTICE file(s) distributed with this work for additional
# information regarding copyright ownership.
#
# This program and the accompanying materials are made available under the
# terms of the Apache License 2.0 which is available at
# http://www.apache.org/licenses/LICENSE-2.0
#
# SPDX-License-Identifier: Apache-2.0
########################################################################

import pytest

from dbcfeeder import _get_command_line_args_parser, _parse_address


def test_infinite_argument():
    parser = _get_command_line_args_parser()

    assert parser.parse_args([]).infinite is None
    assert parser.parse_args(["--infinite"]).infinite is True
    assert parser.parse_args(["--no-infinite"]).infinite is False


def test_address_argument():
    parser = _get_command_line_args_parser()

    assert parser.parse_args([]).address is None
    assert parser.parse_args(["grpc://127.0.0.1:55555"]).address == "grpc://127.0.0.1:55555"
    assert parser.parse_args(["grpcs://localhost:55555"]).address == "grpcs://localhost:55555"


@pytest.mark.parametrize(
    "address, expected",
    [
        ("grpc://127.0.0.1:55555", ("127.0.0.1", 55555, False)),
        ("grpcs://localhost:55555", ("localhost", 55555, True)),
        ("grpc://127.0.0.1", ("127.0.0.1", 55555, False)),
        ("127.0.0.1:55555", ("127.0.0.1", 55555, False)),
        ("127.0.0.1", ("127.0.0.1", 55555, False)),
        ("localhost:55556", ("localhost", 55556, False)),
        ("grpcs://[::1]:55555", ("::1", 55555, True)),
    ],
)
def test_parse_address(address, expected):
    assert _parse_address(address) == expected


@pytest.mark.parametrize(
    "address",
    [
        "ws://127.0.0.1:55555",
        "grpc://",
    ],
)
def test_parse_address_invalid(address):
    with pytest.raises(ValueError):
        _parse_address(address)
