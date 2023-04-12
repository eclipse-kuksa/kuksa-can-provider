# /********************************************************************************
# * Copyright (c) 2022 Contributors to the Eclipse Foundation
# *
# * See the NOTICE file(s) distributed with this work for additional
# * information regarding copyright ownership.
# *
# * This program and the accompanying materials are made available under the
# * terms of the Apache License 2.0 which is available at
# * http://www.apache.org/licenses/LICENSE-2.0
# *
# * SPDX-License-Identifier: Apache-2.0
# ********************************************************************************/


# Build stage, to create a Virtual Environent
FROM --platform=$TARGETPLATFORM python:3.10-alpine as builder

ARG TARGETPLATFORM
ARG BUILDPLATFORM

RUN echo "-- Running on $BUILDPLATFORM, building for $TARGETPLATFORM"

RUN apk update && apk add alpine-sdk linux-headers

COPY . /

RUN python3 -m venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH"

RUN /opt/venv/bin/python3 -m pip install --upgrade pip \
    && pip3 install --no-cache-dir -r requirements.txt


RUN pip3 install wheel scons && pip3 install pyinstaller

# By default we use certificates and tokens from kuksa_certificates, so they must be included
RUN pyinstaller --collect-data kuksa_certificates --hidden-import can.interfaces.socketcan --clean -F -s dbcfeeder.py
#   --debug=imports

WORKDIR /dist

WORKDIR /data
COPY ./config/* ./config/
COPY ./mapping/ ./mapping/
COPY ./*.dbc ./candump*.log ./

# Runner stage, to copy in the virtual environment and the app
FROM alpine:3


WORKDIR /dist

COPY --from=builder /dist/* .
COPY --from=builder /data/ ./

ENV PATH="/dist:$PATH"

# useful dumps about feeding values
ENV LOG_LEVEL="info"

# Vehicle Data Broker host:port
#ENV VDB_ADDRESS="localhost:55555"
# Override VDB_ADDRESS port if set
#ENV DAPR_GRPC_PORT="55555"
# VDB DAPR APP ID
ENV VEHICLEDATABROKER_DAPR_APP_ID=vehicledatabroker

ENV PYTHONUNBUFFERED=yes

ENTRYPOINT ["./dbcfeeder"]
