#!/bin/bash
exec flock -n /tmp/scrape-matches.lock "$0" "$@" || exit 1

START_TIME=$(date +%s)
START_TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
echo "========================================="
echo "Job started: ${START_TIMESTAMP}"
echo "-----------------------------------------"

source /root/ReplayGenieAPI/.env.production
cd /root/ReplayGenieAPI
/root/ReplayGenieAPI/venv/bin/flask showdown scrape-new -w
P1_EXIT_CODE=$?
END_P1_TIME=$(date +%s)
END_P1_TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
DURATION=$((END_P1_TIME - START_TIME))
MINUTES=$((DURATION / 60))
SECONDS=$((DURATION % 60))

echo "Scraped all new matches in current format (Reg I): ${END_P1_TIMESTAMP}"
echo "Duration: ${MINUTES}m ${SECONDS}s (${DURATION} seconds)"
echo "Exit code: ${EXIT_CODE}"

/root/ReplayGenieAPI/venv/bin/flask showdown scrape-new -f 1 -w

P2_EXIT_CODE=$?
END_P2_TIME=$(date +%s)
END_P2_TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
DURATION=$((END_P2_TIME - END_P1_TIME))
MINUTES=$((DURATION / 60))
SECONDS=$((DURATION % 60))
echo "Scraped all new matches in legacy format (Reg F): ${END_P2_TIMESTAMP}"
echo "Duration: ${MINUTES}m ${SECONDS}s (${DURATION} seconds)"
echo "Exit code: ${EXIT_CODE}"

TOTAL_DURATION=$((END_P2_TIME - START_TIME))
MINUTES=$((DURATION / 60))
SECONDS=$((DURATION % 60))
echo "-----------------------------------------"
echo "Job completed: ${END_P2_TIMESTAMP}"
echo "Duration: ${MINUTES}m ${SECONDS}s (${DURATION} seconds)"
echo "========================================="
echo ""
