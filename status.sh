#!/bin/bash
# Elo Scoring Progress Monitor

DB_PATH="$HOME/.config/reader/reader.db"
LOG_PATH="/tmp/claude/tasks/bd668f9.output"

# Trap Ctrl+C to exit cleanly
trap 'echo ""; echo "Monitoring stopped."; exit 0' INT

# Function to display status
show_status() {
    clear
    echo "=================================================="
    echo "           ELO SCORING PROGRESS"
    echo "=================================================="
    echo ""

# Total articles to score
TOTAL=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM articles WHERE extraction_status = 'success'")

# Scored articles (7+ comparisons)
SCORED=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM articles WHERE elo_comparisons >= 7")

# In-progress (some comparisons but not 7 yet)
IN_PROGRESS=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM articles WHERE elo_comparisons > 0 AND elo_comparisons < 7")

# Not started
NOT_STARTED=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM articles WHERE elo_comparisons = 0 AND extraction_status = 'success'")

# Calculate percentage
PERCENT=$(awk "BEGIN {printf \"%.1f\", ($SCORED / $TOTAL) * 100}")

echo "📊 PROGRESS"
echo "  Total articles:    $TOTAL"
echo "  ✓ Scored:          $SCORED ($PERCENT%)"
echo "  ⏳ In progress:     $IN_PROGRESS"
echo "  ⏸  Not started:     $NOT_STARTED"
echo ""

# Elo statistics
if [ "$SCORED" -gt 0 ]; then
    echo "📈 ELO STATISTICS (Scored Articles)"
    sqlite3 "$DB_PATH" "SELECT
        '  Min:    ' || printf('%.1f', MIN(elo_rating)) || CHAR(10) ||
        '  Avg:    ' || printf('%.1f', AVG(elo_rating)) || CHAR(10) ||
        '  Median: ' || printf('%.1f', (SELECT elo_rating FROM articles WHERE elo_comparisons >= 7 ORDER BY elo_rating LIMIT 1 OFFSET (SELECT COUNT(*) FROM articles WHERE elo_comparisons >= 7) / 2)) || CHAR(10) ||
        '  Max:    ' || printf('%.1f', MAX(elo_rating))
    FROM articles WHERE elo_comparisons >= 7"
    echo ""
fi

# Distribution
if [ "$SCORED" -gt 20 ]; then
    echo "📊 ELO DISTRIBUTION"
    sqlite3 "$DB_PATH" "SELECT
        CASE
            WHEN elo_rating < 1400 THEN '  <1400:  '
            WHEN elo_rating < 1450 THEN '  1400-1450: '
            WHEN elo_rating < 1500 THEN '  1450-1500: '
            WHEN elo_rating < 1550 THEN '  1500-1550: '
            WHEN elo_rating < 1600 THEN '  1550-1600: '
            ELSE '  ≥1600:  '
        END || COUNT(*) || ' articles'
    FROM articles
    WHERE elo_comparisons >= 7
    GROUP BY CASE
        WHEN elo_rating < 1400 THEN 1
        WHEN elo_rating < 1450 THEN 2
        WHEN elo_rating < 1500 THEN 3
        WHEN elo_rating < 1550 THEN 4
        WHEN elo_rating < 1600 THEN 5
        ELSE 6
    END
    ORDER BY 1"
    echo ""
fi

# Recent activity
echo "📝 RECENT ACTIVITY (last 10 lines)"
echo "--------------------------------------------------"
tail -10 "$LOG_PATH" 2>/dev/null | grep -E "(Scoring article|Scored article|Comparison)" | sed 's/^.*INFO - //' || echo "  No log data yet..."
echo ""

# Current article being scored
CURRENT=$(tail -50 "$LOG_PATH" 2>/dev/null | grep "Scoring article [0-9]* with" | tail -1 | sed 's/.*Scoring article //' | sed 's/ with.*//')
if [ ! -z "$CURRENT" ]; then
    echo "🔄 Currently scoring: Article #$CURRENT"
    echo ""
fi

# Estimated time remaining
if [ "$SCORED" -gt 10 ]; then
    # Get timestamp of first and last scored article
    FIRST_TIME=$(grep "Scored article" "$LOG_PATH" | head -1 | cut -d' ' -f1-2)
    LAST_TIME=$(grep "Scored article" "$LOG_PATH" | tail -1 | cut -d' ' -f1-2)

    if [ ! -z "$FIRST_TIME" ] && [ ! -z "$LAST_TIME" ]; then
        FIRST_EPOCH=$(date -j -f "%Y-%m-%d %H:%M:%S" "$FIRST_TIME" +%s 2>/dev/null)
        LAST_EPOCH=$(date -j -f "%Y-%m-%d %H:%M:%S" "$LAST_TIME" +%s 2>/dev/null)

        if [ ! -z "$FIRST_EPOCH" ] && [ ! -z "$LAST_EPOCH" ]; then
            ELAPSED=$((LAST_EPOCH - FIRST_EPOCH))
            if [ "$ELAPSED" -gt 0 ] && [ "$SCORED" -gt 0 ]; then
                AVG_TIME=$((ELAPSED / SCORED))
                REMAINING=$((NOT_STARTED * AVG_TIME))
                HOURS=$((REMAINING / 3600))
                MINS=$(((REMAINING % 3600) / 60))
                echo "⏱  Estimated time remaining: ${HOURS}h ${MINS}m"
                echo ""
            fi
        fi
    fi
fi

    echo "=================================================="
    echo "Last updated: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "Refreshing every 3 seconds... (Press Ctrl+C to exit)"
}

# Main loop
while true; do
    show_status
    sleep 3
done
