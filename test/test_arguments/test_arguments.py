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
import os


@pytest.fixture
def change_test_dir(request, monkeypatch):
    # To make sure we run from test directory
    monkeypatch.chdir(request.fspath.dirname)


@pytest.mark.parametrize("requested_server, ok_expected", [
    ('kuksa_databroker', True),
    ('kuksa_val_server', True),
    ('KUKSA_DATABROKER', False),
    ('KUKSA_VAL_SERVER', False)])
def test_server_type(requested_server, ok_expected, change_test_dir):
    test_str = "../../dbcfeeder.py --server-type " + requested_server + "  --help > out.txt 2>&1"
    result = os.system(test_str)
    assert os.WIFEXITED(result)
    if ok_expected:
        assert os.WEXITSTATUS(result) == 0
        # Check that we get normal help
        test_str = r'grep "\-\-server-type {kuksa_val_server,kuksa_databroker}" out.txt > /dev/null'
    else:
        assert os.WEXITSTATUS(result) != 0
        # Check that we get error
        test_str = r'grep "(choose from ' + r"'kuksa_val_server', 'kuksa_databroker')" + r'" out.txt > /dev/null'

    result = os.system(test_str)
    os.system("cat out.txt")
    os.system("rm -f out.json out.txt")
    assert os.WIFEXITED(result)
    assert os.WEXITSTATUS(result) == 0
