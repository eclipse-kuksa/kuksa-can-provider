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

from dbcfeeder import _get_command_line_args_parser


def test_infinite_argument():
    parser = _get_command_line_args_parser()

    assert parser.parse_args([]).infinite is None
    assert parser.parse_args(["--infinite"]).infinite is True
    assert parser.parse_args(["--no-infinite"]).infinite is False
