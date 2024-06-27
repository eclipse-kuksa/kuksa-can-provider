# KUKSA CAN Provider and Docker

It is possible to build can-provider as a Docker container

```console
docker build -f Dockerfile --progress=plain -t can-provider:latest .
```

The same container can be used for both connecting to Databroker and Server:

```console
docker run  --net=host -e LOG_LEVEL=INFO can-provider:latest --server-type kuksa_databroker

docker run  --net=host -e LOG_LEVEL=INFO can-provider:latest --server-type kuksa_val_server
```

## Building for a different architecture

You can build for a different architecture by using `buildx`and the `--platform` argument.
You might need to install `qemu-user-static` depending on your distribution.

```console
docker buildx build -f Dockerfile --progress=plain --platform=linux/arm64 -t can-provider:latest .
```

## Pre-built Docker container

A pre-built Docker container is available in the repository. The container is availablat the github container registry via

```console
docker pull ghcr.io/eclipse-kuksa/kuksa-can-provider/can-provider
```

If the ghcr registry is not easily accessible to you, e.g. if you are a China mainland user, starting from release 0.4.4 we  also made the container images available at quay.io:

```console
docker pull quay.io/eclipse-kuksa/can-provider
```

## KUKSA.val Server/Databroker Authentication when using Docker

The docker container contains default certificates for KUKSA.val server, and if the configuration file does not
specify token file the [default token file](https://github.com/eclipse/kuksa.val/blob/master/kuksa_certificates/jwt/all-read-write.json.token)
provided by [kuksa-client](https://github.com/eclipse/kuksa.val/tree/master/kuksa-client) will be used.

No default token is included for KUKSA Databroker. Instead the user must specify the token file in the config file.
The token must also be available for the running docker container, for example by mounting the directory container
when starting the container. Below is an example based on that the token file
[provide-all.token](https://github.com/eclipse/kuksa.val/blob/master/jwt/provide-all.token) is used and that `kuksa.val`
is cloned to `/home/user/kuksa.val`. Then the token can be accessed by mounting the `jwt`folder using the `-v`
and specify `token=/jwt/provide-all.token` in the [default configuration file](../config/dbc_feeder.ini).

```console
docker run  --net=host -e LOG_LEVEL=INFO -v /home/user/kuksa.val/jwt:/jwt can-provider:latest
```

*Note that authentication in KUKSA Databroker by default is deactivated, and then no token needs to be given!*
