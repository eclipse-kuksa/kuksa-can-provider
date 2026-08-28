# /********************************************************************************
# * Copyright (c) 2022-2026 Contributors to the Eclipse Foundation
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


# Build stage
ARG TARGETARCH

FROM python:3.14-slim-trixie AS builder

# In case arm64 builds via buildx/qemu are EXTREMELY slow, check these
# https://bugs.debian.org/cgi-bin/bugreport.cgi?bug=1113951
# https://www.linaro.org/blog/qemu-a-tale-of-performance-analysis/

ARG TARGETPLATFORM
ARG BUILDPLATFORM
ARG TARGETARCH

RUN echo "-- Running on $BUILDPLATFORM, building for $TARGETPLATFORM"


# pyinstaller needs binutils
RUN apt update && apt -y install \
    binutils

# RISCV
# pyinstaller needs to build some components,
# grpcio also needs to build as no wheels exist currently (08/2026)
# so we need compilers and dependencies.
RUN if [ "$TARGETARCH" = "riscv64" ]; then \
        apt -y install gcc zlib1g-dev g++ cmake libatomic1; \
    fi

# Collect runtime .so files the final distroless stage needs but doesn't ship,
# so the final stage can COPY them unconditionally regardless of TARGETARCH.
# libz is always needed (pyinstaller doesn't pick up the transient dependency).
# libstdc++ is only needed on riscv64, where grpcio is compiled from source
# (no manylinux wheel available) and cygrpc*.so links against it dynamically;
# without it you get "undefined symbol: _ZTVN10__cxxabiv117__class_type_infoE".
RUN mkdir -p /rtlibs && \
    cp /usr/lib/*-linux-gnu/libz.so.1 /rtlibs/ && \
    if [ "$TARGETARCH" = "riscv64" ]; then \
        cp /usr/lib/*-linux-gnu/libstdc++.so.6 /rtlibs/; \
    fi


RUN pip install --upgrade --no-cache-dir pip build pyinstaller

COPY requirements.txt /

RUN pip install --no-cache-dir -r requirements.txt

# Copy "all" files first when dependencies have been installed to reuse
# cached layers as much as possible

COPY . /

# By default we use certificates and tokens from kuksa_client, so they must be included
# Do not strip, becasue strip destroys numpy
# you would get errors like
# "libscipyopenblas64-128b20d9.so: ELF load command address/offset not page-aligned"
RUN pyinstaller --collect-data kuksa_client --hidden-import can.interfaces.socketcan --clean -F  dbcfeeder.py
#   --debug=imports

WORKDIR /data
COPY ./config/* ./config/
COPY ./mapping/ ./mapping/
COPY ./*.dbc ./candump*.log ./*.json ./

# Debian 13 is trixie, so the glibc version matches.
# Distroless is a lot smaller than Debian slim versions
#
# For development (to add a busybox shell) add :debug like this
# FROM gcr.io/distroless/base-debian13:debug
# riscv64 needs more libs at runtime (grpcio is built from source there, unlike
# the prebuilt manylinux wheels used on other arches), which "base" doesn't ship
FROM gcr.io/distroless/base-debian13 AS runtimeamd64
FROM gcr.io/distroless/base-debian13 AS runtimearm64
FROM gcr.io/distroless/cc-debian13:debug AS runtimeriscv64
# grpcio's cygrpc*.so is built without a NEEDED entry for libstdc++.so.6 (even
# though it references libstdc++ symbols), so the dynamic linker never loads
# it on its own - preload it so its symbols are already globally available
# when cygrpc.so is dlopen'd, avoiding
# "undefined symbol: _ZTVN10__cxxabiv117__class_type_infoE".
ENV LD_PRELOAD="/lib/libstdc++.so.6"

# Buildkit quirk: Without explicitely setting platform targetarch is not
# auto-populated outside of stages, so we will use the default options here.
FROM gcr.io/distroless/base-debian13 AS runtime

FROM runtime${TARGETARCH}

WORKDIR /dist

COPY --from=builder /dist/* .
COPY --from=builder /data/ ./

# see /rtlibs collection in builder stage above
COPY --from=builder /rtlibs/ /lib/

ENV PATH="/dist:$PATH"

# useful dumps about feeding values
ENV LOG_LEVEL="info"


ENV PYTHONUNBUFFERED=yes

ENTRYPOINT ["./dbcfeeder"]
