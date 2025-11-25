#!/bin/bash
cd /home/laptop/reversible_text_optimizer
rm -f testing/stress_stats.json testing/stress_test.log testing/final_report.txt
clear
echo "Starting RTO Stress Test..."
echo "File range: 1 byte to 40MB"
echo ""
exec ./testing/parallel_stress_test.sh
