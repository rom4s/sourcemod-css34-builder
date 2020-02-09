#!/bin/bash
#
SELF_PATH=${0%/*}
echo BUILDER_PATH = $(pwd)/${SELF_PATH}
cd sourcemod && python $SELF_PATH/../build.py