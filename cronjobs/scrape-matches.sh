#!/bin/bash

START_TIME=$(date +%s)
START_TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
echo "========================================="
echo "Job started: ${START_TIMESTAMP}"
echo "-----------------------------------------"

source /root/ReplayGenieAPI/.env.production
cd /root/ReplayGenieAPI
/root/ReplayGenieAPI/venv/bin/flask showdown scrape-new

EXIT_CODE=$?
END_TIME=$(date +%s)
END_TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
DURATION=$((END_TIME - START_TIME))
MINUTES=$((DURATION / 60))
SECONDS=$((DURATION % 60))

echo "-----------------------------------------"
echo "Job completed: ${END_TIMESTAMP}"
echo "Duration: ${MINUTES}m ${SECONDS}s (${DURATION} seconds)"
echo "Exit code: ${EXIT_CODE}"
echo "========================================="
echo ""
