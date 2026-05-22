#!/bin/bash
#
# refresh_all_data.sh
# Automated data refresh for OpenRouter Infrastructure Mapper
#
# This script runs the complete data pipeline:
# 1. Fetch latest models and providers from OpenRouter API
# 2. Map infrastructure providers for all models
# 3. Integrate provider research data (if available)
# 4. Generate daily report with advanced features
# 5. Regenerate standalone HTML
#

set -e  # Exit on error

echo "========================================================================"
echo "OpenRouter Infrastructure Mapper - Full Data Refresh"
echo "========================================================================"
echo ""

# Step 1: Fetch base data
echo "Step 1/5: Fetching latest data from OpenRouter API..."
python3 fetch_openrouter.py
echo "✓ Fetch complete"
echo ""

# Step 2: Map infrastructure
echo "Step 2/5: Mapping infrastructure providers (this takes ~2 minutes)..."
python3 map_infrastructure_providers.py
echo "✓ Infrastructure mapping complete"
echo ""

# Step 3: Integrate research (skip if file doesn't exist)
if [ -f "provider_research.json" ]; then
    echo "Step 3/5: Integrating provider research data..."
    python3 integrate_research.py
    echo "✓ Research integration complete"
else
    echo "Step 3/5: Skipping research integration (provider_research.json not found)"
fi
echo ""

# Step 4: Generate daily report
echo "Step 4/5: Generating daily report with advanced features..."
python3 generate_daily_report.py
echo "✓ Daily report generated"
echo ""

# Step 5: Regenerate standalone HTML
echo "Step 5/5: Regenerating standalone HTML..."
python3 << 'EOF'
import json

with open('infrastructure_provider_map.json') as f:
    data = json.load(f)

with open('index.html') as f:
    html = f.read()

# Replace the entire loadData function - must match exact structure
html = html.replace(
    '''async function loadData() {
            try {
                const response = await fetch('infrastructure_provider_map.json');
                infraData = await response.json();
                initializeUI();
            } catch (error) {
                console.error('Error loading data:', error);
                document.getElementById('providers-table-container').innerHTML =
                    '<div class="no-results">Error loading data. Make sure infrastructure_provider_map.json exists in the same directory.<br><br>If opening directly as a file, use index_standalone.html instead or run a web server.</div>';
            }
        }''',
    '''async function loadData() {
            // Data embedded in standalone version
            infraData = ''' + json.dumps(data) + ''';
            initializeUI();
        }'''
)

with open('index_standalone.html', 'w') as f:
    f.write(html)

print(f"✓ Generated index_standalone.html ({len(html):,} bytes)")
EOF
echo ""

# Summary
echo "========================================================================"
echo "✓ ALL STEPS COMPLETE"
echo "========================================================================"
echo ""
echo "Generated files:"
echo "  • openrouter_models.json (raw models data)"
echo "  • openrouter_providers.json (raw providers data)"
echo "  • infrastructure_provider_map.json (main data file)"
echo "  • daily_report.md (human-readable report)"
echo "  • daily_report.json (machine-readable report)"
echo "  • index_standalone.html (standalone web UI)"
echo ""
echo "View reports:"
echo "  • cat daily_report.md"
echo "  • python3 view_daily_report.py summary"
echo "  • python3 view_daily_report.py audio-providers"
echo ""
echo "View web UI:"
echo "  • python3 serve.py (then open http://localhost:8000)"
echo "  • open index_standalone.html (no server needed)"
echo ""
