#!/bin/sh
# Runs Compose setup for Interledger demo
# and removes shared volumes afterwards
docker-compose -f docker-compose.yaml run --rm interledger_demo
docker-compose -f docker-compose.yaml down -v
