#!/bin/bash
#
SELF_PATH=$(realpath ${0%/*})
echo BUILDER_PATH = ${SELF_PATH}
cd sourcemod && python $SELF_PATH/../build.py