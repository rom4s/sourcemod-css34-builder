#!/bin/bash
#
SELF_PATH=$(python -c "import os; print(os.path.realpath('${0%/*}'))")
echo BUILDER_PATH = ${SELF_PATH}
cd sourcemod && python ${SELF_PATH}/../build.py