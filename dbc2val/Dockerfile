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
FROM --platform=$TARGETPLATFORM python:3.9-slim-bullseye as builder

ARG TARGETPLATFORM
ARG BUILDPLATFORM

RUN echo "-- Running on $BUILDPLATFORM, building for $TARGETPLATFORM"

RUN apt-get update -qqy && apt-get upgrade -qqy && apt-get install -qqy binutils g++

COPY . /

RUN python3 -m venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH"

RUN /opt/venv/bin/python3 -m pip install --upgrade pip \
    && pip3 install --no-cache-dir -r requirements.txt

RUN pip3 install wheel && pip3 install scons && pip3 install pyinstaller && pip3 install patchelf && pip3 install staticx

RUN pyinstaller --clean -F -s dbcfeeder.py
#   --debug=imports

WORKDIR /dist
RUN staticx dbcfeeder dbcfeeder-exe

WORKDIR /data
COPY ./config/* ./config/
COPY ./*.yml ./*.dbc ./candump*.log ./

# Runner stage, to copy in the virtual environment and the app
FROM scratch

LABEL org.opencontainers.image.source="https://github.com/eclipse/kuksa.val.feeders"

LABEL org.opencontainers.image.licenses="APACHE-2.0"

# needed as /dist/binary unpacks and runs from /tmp
WORKDIR /tmp
# optional volume mapping
WORKDIR /conf

WORKDIR /dist

COPY --from=builder /dist/dbcfeeder-exe .
COPY --from=builder /data/ ./

ENV PATH="/dist:$PATH"

# useful dumps about feeding values
ENV LOG_LEVEL="info,databroker=error,dbcfeeder=error,dbcfeeder.broker_client=error"

# Vehicle Data Broker host:port
#ENV VDB_ADDRESS="localhost:55555"
# Override VDB_ADDRESS port if set
#ENV DAPR_GRPC_PORT="55555"
# VDB DAPR APP ID
ENV VEHICLEDATABROKER_DAPR_APP_ID=vehicledatabroker

ENV PYTHONUNBUFFERED=yes

CMD ["./dbcfeeder-exe"]
