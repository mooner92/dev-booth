#!/bin/bash
source /dev-booth/env/bin/activate

echo "Starting Task-Booth agents..."

python /dev-booth/bots/openclaw.py &
OPENCLAW_PID=$!

python /dev-booth/bots/hermes.py a &
HERMES_A_PID=$!

python /dev-booth/bots/hermes.py b &
HERMES_B_PID=$!

echo "OpenClaw PID: $OPENCLAW_PID"
echo "Hermes-A PID: $HERMES_A_PID"
echo "Hermes-B PID: $HERMES_B_PID"

wait
