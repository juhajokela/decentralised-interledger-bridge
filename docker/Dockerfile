# build with "export DOCKER_BUILDKIT=1"
FROM python:3.8 AS build

RUN apt-get update && \
	apt-get -y install gcc g++ linux-headers-amd64 libffi-dev libgnutls28-dev rustc && \
	rm -rf /var/lib/apt/lists/*
COPY ./configs /var/interledger/configs
COPY ./ledgers/solidity/contracts/ /var/interledger/ledgers/solidity/contracts/
COPY ./setup.py /var/interledger/setup.py
COPY ./scripts /var/interledger/scripts
COPY ./src /var/interledger/src
WORKDIR /var/interledger
RUN python3 -m pip install setuptools-rust
RUN python3 -m pip install .


# Run Interledger CLI demo
FROM build AS run_demo
COPY ./demo /var/interledger/demo
CMD [ "python3", "demo/cli/cli.py", "configs/local-config.cfg" ]

# Run DIB Interledger
FROM build as run_dib
COPY ./ledgers/solidity/contracts/ /var/interledger/ledgers/solidity/contracts/
COPY ./start_dib.py /var/interledger/start_dib.py
CMD [ "python3", "start_dib.py", "configs/local-config.cfg" ]
