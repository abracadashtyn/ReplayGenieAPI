#!/bin/bash

START_TIME=$(date +%s)
START_TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
echo "========================================="
echo "Job started: ${START_TIMESTAMP}"
echo "-----------------------------------------"

source /root/ReplayGenieAPI/.env.production
cd /root/ReplayGenieAPI

/root/ReplayGenieAPI/venv/bin/flask showdown scrape -f 2

P1_EXIT_CODE=$?
END_P1_TIME=$(date +%s)
END_P1_TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
DURATION=$((END_P1_TIME - START_TIME))
MINUTES=$((DURATION / 60))
SECONDS=$((DURATION % 60))
echo "-----------------------------------------"
echo "Scraped all new matches in current format (Reg I): ${END_P1_TIMESTAMP}"
echo "Duration: ${MINUTES}m ${SECONDS}s (${DURATION} seconds)"
echo "Exit code: ${P1_EXIT_CODE}"
echo "-----------------------------------------"

/root/ReplayGenieAPI/venv/bin/flask showdown scrape -f 1

P2_EXIT_CODE=$?
END_P2_TIME=$(date +%s)
END_P2_TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
DURATION=$((END_P2_TIME - END_P1_TIME))
MINUTES=$((DURATION / 60))
SECONDS=$((DURATION % 60))
echo "-----------------------------------------"
echo "Scraped all new matches in legacy format (Reg F): ${END_P2_TIMESTAMP}"
echo "Duration: ${MINUTES}m ${SECONDS}s (${DURATION} seconds)"
echo "Exit code: ${P2_EXIT_CODE}"
echo "-----------------------------------------"

/root/ReplayGenieAPI/venv/bin/flask showdown assign-set

P3_EXIT_CODE=$?
END_P3_TIME=$(date +%s)
END_P3_TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
DURATION=$((END_P3_TIME - END_P2_TIME))
MINUTES=$((DURATION / 60))
SECONDS=$((DURATION % 60))
echo "-----------------------------------------"
echo "Assigned a set id to all newly ingested matches: ${END_P3_TIMESTAMP}"
echo "Duration: ${MINUTES}m ${SECONDS}s (${DURATION} seconds)"
echo "Exit code: ${P3_EXIT_CODE}"
echo "-----------------------------------------"


TOTAL_DURATION=$((END_P3_TIME - START_TIME))
MINUTES=$((DURATION / 60))
SECONDS=$((DURATION % 60))
echo "-----------------------------------------"
echo "Job completed: ${END_P3_TIMESTAMP}"
echo "Duration: ${MINUTES}m ${SECONDS}s (${DURATION} seconds)"
echo "========================================="
echo ""
