#!/usr/bin/env python3

#################################################################################
# Copyright (c) 2022 Contributors to the Eclipse Foundation
#
# See the NOTICE file(s) distributed with this work for additional
# information regarding copyright ownership.
#
# This program and the accompanying materials are made available under the
# terms of the Apache License 2.0 which is available at
# http://www.apache.org/licenses/LICENSE-2.0
#
# SPDX-License-Identifier: Apache-2.0
#################################################################################

import logging

import grpc
from gen_proto.sdv.databroker.v1 import (
    broker_pb2,
    broker_pb2_grpc,
    collector_pb2,
    collector_pb2_grpc,
)
from gen_proto.sdv.databroker.v1 import types_pb2 as types  # for export

log = logging.getLogger(__name__)


class BrokerClient:
    def __init__(self, channel, grpc_metadata=None):
        self._stub = broker_pb2_grpc.BrokerStub(channel)
        self._grpc_meta_data = grpc_metadata

    def get_datapoints(self, datapoints):
        if type(datapoints) is str:
            datapoints = [datapoints]

        request = broker_pb2.GetDatapointsRequest()
        request.datapoints.extend(datapoints)
        return self._stub.GetDatapoints(
            request, metadata=self._grpc_meta_data
        ).datapoints

    def get_metadata(self, datapoints=[]):
        if type(datapoints) is str:
            datapoints = [datapoints]
        request = broker_pb2.GetMetadataRequest()
        request.names.extend(datapoints)
        return self._stub.GetMetadata(request, metadata=self._grpc_meta_data).list

    def subscribe(self, query):
        request = broker_pb2.SubscribeRequest()
        request.query = query
        return self._stub.Subscribe(request, metadata=self._grpc_meta_data)


class Provider:
    def __init__(self, channel, grpc_metadata=None):
        self._name_to_id = {}
        self._name_to_type = {}
        self._grpc_meta_data = grpc_metadata
        log.info("Using metadata: {}".format(self._grpc_meta_data))
        self._stub = collector_pb2_grpc.CollectorStub(channel)
        self._broker = BrokerClient(channel, self._grpc_meta_data)

    def register(self, name, data_type, change_type, description):
        try:
            log.debug(
                "register(%s, data_type: %d, change: %d, '%s')",
                name,
                data_type,
                change_type,
                description,
            )
            metadata = self._broker.get_metadata(name)
            if len(metadata) == 1:
                self._name_to_id[name] = metadata[0].id
                self._name_to_type[name] = metadata[0].data_type
                log.info(
                    "%s was already registered with id %d, type %d",
                    name,
                    self._name_to_id[name],
                    metadata[0].data_type,
                )
                return
        except grpc.RpcError:
            log.debug("Failed to get metadata", exc_info=True)

        self._register(name, data_type, change_type, description)

    def _register(self, name, data_type, change_type, description):
        request = collector_pb2.RegisterDatapointsRequest()
        request.list.append(
            collector_pb2.RegistrationMetadata(
                name=name,
                data_type=data_type,
                change_type=change_type,
                description=description,
            )
        )

        # Error handling for grpc connection to the databroker
        # https://github.com/avinassh/grpc-errors/blob/master/python/client.py
        try:
            response = self._stub.RegisterDatapoints(
                request, metadata=self._grpc_meta_data
            )
            # Store datapoint IDs
            self._name_to_id[name] = response.results[name]
            self._name_to_type[name] = data_type
            log.info(
                "%s was registered with id %d, type %d",
                name,
                response.results[name],
                data_type,
            )
        except grpc.RpcError:
            log.warning("Failed to register datapoint {}".format(name), exc_info=True)
            raise

    def update_with_failure(self, name, reason="INVALID_VALUE"):
        request = collector_pb2.UpdateDatapointsRequest()

        id = self._name_to_id[name]
        request.datapoints[id].failure_value = types.Datapoint.Failure.Value(reason)

        self._stub.UpdateDatapoints(request, metadata=self._grpc_meta_data)
        log.debug("[%d] %s => Failure(%s)", id, name, reason)

    def update_datapoint(self, name, value):
        request = collector_pb2.UpdateDatapointsRequest()
        id = self._name_to_id[name]
        type = self._name_to_type[name]
        if type == types.STRING:
            request.datapoints[id].string_value = value
        elif type == types.BOOL:
            request.datapoints[id].bool_value = value
        elif type == types.INT8 or type == types.INT16 or type == types.INT32:
            request.datapoints[id].int32_value = value
        elif type == types.INT64:
            request.datapoints[id].int64_value = value
        elif type == types.UINT8 or type == types.UINT16 or type == types.UINT32:
            request.datapoints[id].uint32_value = value
        elif type == types.UINT64:
            request.datapoints[id].uint64_value = value
        elif type == types.FLOAT:
            request.datapoints[id].float_value = value
        elif type == types.DOUBLE:
            request.datapoints[id].double_value = value
        elif type == types.STRING_ARRAY:
            request.datapoints[id].string_array.values.extend(value)
        elif type == types.BOOL_ARRAY:
            request.datapoints[id].bool_array.values.extend(value)
        elif (
            type == types.INT8_ARRAY
            or type == types.INT16_ARRAY
            or type == types.INT32_ARRAY
        ):
            request.datapoints[id].int32_array.values.extend(value)
        elif type == types.INT64_ARRAY:
            request.datapoints[id].int64_array.values.extend(value)
        elif (
            type == types.UINT8_ARRAY
            or type == types.UINT16_ARRAY
            or type == types.UINT32_ARRAY
        ):
            request.datapoints[id].uint32_array.values.extend(value)
        elif type == types.UINT64_ARRAY:
            request.datapoints[id].uint64_array.values.extend(value)
        elif type == types.FLOAT_ARRAY:
            request.datapoints[id].float_array.values.extend(value)
        elif type == types.DOUBLE_ARRAY:
            request.datapoints[id].double_array.values.extend(value)
        else:
            raise Exception("Unknown datapoint")

        # log.debug(request)
        # Send the data to the databroker
        self._stub.UpdateDatapoints(request, metadata=self._grpc_meta_data)
        log.debug("[%d] %s => %s", id, name, value)
