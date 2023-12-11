# /********************************************************************************
# * Copyright (c) 2022,2023 Contributors to the Eclipse Foundation
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

name: kuksa_dbc_feeder

on:
  push:
    branches: [ main ]
  pull_request:
  workflow_dispatch:

concurrency:
      group: ${{ github.ref }}-${{ github.workflow }}
      cancel-in-progress: true

jobs:
  check_ghcr_push:
    uses: eclipse-kuksa/kuksa-actions/.github/workflows/check_ghcr_push.yml@2
    secrets: inherit

  build-can-provider-image:
    name: "Build can provider image"
    runs-on: self-hosted
    needs: check_ghcr_push

    steps:
    - name: Checkout Repository
      uses: actions/checkout@v3

    - name: Docker meta
      id: meta
      uses: docker/metadata-action@v4
      with:
        # list of Docker images to use as base name for tags
        images: |
          ghcr.io/eclipse-kuksa/kuksa-can-provider/can-provider
        # generate Docker tags based on the following events/attributes
        tags: |
          type=ref,event=branch
          type=ref,event=pr
          type=semver,pattern={{version}}
          type=semver,pattern={{major}}.{{minor}}
          type=semver,pattern={{major}}

    # only needed for runners without buildx setup, will be slow
    #- name: Set up QEMU
    #  uses: docker/setup-qemu-action@v2

    #- name: Set up Docker Buildx
    #  uses: docker/setup-buildx-action@v2

    - name: Log in to the Container registry
      if: needs.check_ghcr_push.outputs.push == 'true'
      uses: docker/login-action@v2
      with:
          registry: ghcr.io
          username: ${{ github.repository_owner }}
          password: ${{ secrets.GITHUB_TOKEN }}

    - name: Build DBC provider container container and push to ghcr.io (and ttl.sh)
      id: ghcr-build
      if: needs.check_ghcr_push.outputs.push == 'true'
      uses: docker/build-push-action@v4
      with:
        platforms: |
          linux/amd64
          linux/arm64
        file: ./Dockerfile
        context: ./
        push: true
        tags: |
          ${{ steps.meta.outputs.tags }}
          ttl.sh/eclipse-kuksa/kuksa-can-provider/can-provider-${{github.sha}}
        labels: ${{ steps.meta.outputs.labels }}

    - name: Build ephemeral DBC provider container and push to ttl.sh
      if: needs.check_ghcr_push.outputs.push == 'false'
      id: tmp-build
      uses: docker/build-push-action@v4
      with:
        platforms: |
          linux/amd64
          linux/arm64
        file: ./Dockerfile
        context: .
        push: true
        tags: "ttl.sh/eclipse-kuksa/kuksa-can-provider/can-provider-${{github.sha}}"
        labels: ${{ steps.meta.outputs.labels }}

    - name: Posting message
      uses: eclipse-kuksa/kuksa-actions/post-container-location@2
      with:
        image: ttl.sh/eclipse-kuksa/kuksa-can-provider/can-provider-${{github.sha}}


  run-can-provider-tests:
    name: "Run can provider test"
    runs-on: ubuntu-latest

    steps:
    - name: Checkout Repository
      uses: actions/checkout@v3

    - name: Run can tests
      run: |
        pip3 install --no-cache-dir -r requirements.txt -r requirements-dev.txt
        python -m pytest

    - name: Run pylint (fail on errors and above)
      run: |
        # First just show, never fail
        pylint --exit-zero dbcfeeder.py dbcfeederlib test
        # Fail on errors and above
        pylint -E dbcfeeder.py dbcfeederlib test

    - name: Run mypy, fail on errors.
      run: |
          # Also install some dependencies for analysis
          pip3 install mypy grpc-stubs
          python -m mypy *.py dbcfeederlib test
