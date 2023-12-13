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
# FROM --platform=$TARGETPLATFORM python:3.10-alpine as builder
FROM --platform=$TARGETPLATFORM python:3.10-slim-bookworm as builder

ARG TARGETPLATFORM
ARG BUILDPLATFORM

RUN echo "-- Running on $BUILDPLATFORM, building for $TARGETPLATFORM"

RUN apt update && apt -yy install binutils git

# It seems 3.10-slim-bookworm shall have gcc, but for aarch64 where it is needed
# it does not seem to be present, needed to build bitstruct
# https://github.com/docker-library/python/blob/master/3.10/slim-bookworm/Dockerfile
RUN apt -yy install gcc
# cmake and opanblas-dev needed for aarch build
# RUN apk update && apk add alpine-sdk linux-headers cmake openblas-dev

# RUN python3 -m venv /opt/venv

# ENV PATH="/opt/venv/bin:$PATH"

#COPY requirements.txt /

# RUN /opt/venv/bin/python3 -m pip install --upgrade pip
# RUN pip3 install --no-cache-dir wheel scons
# RUN pip3 install --no-cache-dir pyinstaller
# RUN pip3 install --no-cache-dir -r requirements.txt

RUN pip install --upgrade --no-cache-dir pip build pyinstaller

COPY requirements.txt /

RUN pip3 install --no-cache-dir -r requirements.txt

# Copy "all" files first when dependencies have been installed to reuse
# cached layers as much as possible

COPY . /

# By default we use certificates and tokens from kuksa_certificates, so they must be included
RUN pyinstaller --collect-data kuksa_client --hidden-import can.interfaces.socketcan --clean -F -s dbcfeeder.py
#   --debug=imports

WORKDIR /dist

WORKDIR /data
COPY ./config/* ./config/
COPY ./mapping/ ./mapping/
COPY ./*.dbc ./candump*.log ./*.json ./

# Debian 12 is bookworm, so the glibc version matches. Distroless is a lot smaller than
# Debian slim versions
# For development add :debug like this
# FROM gcr.io/distroless/base-debian12:debug  to get a busybox shell as well
FROM gcr.io/distroless/base-debian12


WORKDIR /dist

COPY --from=builder /dist/* .
COPY --from=builder /data/ ./

# pyinstaller doesn't pick up transient libz dependency, so copying it manually
COPY --from=builder /usr/lib/*-linux-gnu/libz.so.1 /lib/

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
