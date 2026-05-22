# Web UI Guide

## 🚀 Quick Start

### Start the Web Server

```bash
# Option 1: Using the Python script (recommended)
python3 serve.py

# Option 2: Using Python's built-in server
python3 -m http.server 8000

# Option 3: Just open index.html directly in your browser
open index.html  # Mac
# or
start index.html  # Windows
```

Then open: **http://localhost:8000/index.html**

---

## 🎨 Features

### Dashboard Overview
- **Real-time Stats**: Total providers, models, countries, average uptime
- **Interactive Charts**: Visual representation of key metrics
- **Color-coded Badges**: Countries identified by color

### 4 Main Views

#### 1️⃣ All Providers
The main table showing all infrastructure providers with:
- **Sortable Columns**: Click any column header to sort
  - Provider name
  - Location (country)
  - Number of models
  - Uptime percentage
  - Average latency
  - Price range
- **Click Provider Name**: Opens detailed modal with all models
- **View Details Button**: Same as clicking provider name

#### 2️⃣ By Geography
Providers organized by country/region:
- Grouped by headquarters location
- Shows provider count and model count per region
- Sorted by number of providers (US first with 37 providers)
- Includes "Unknown" for providers without location data

#### 3️⃣ Performance Leaders
Two leaderboards:
- **Best Uptime**: Top 15 providers by 24-hour uptime
- **Lowest Latency**: Top 15 providers by p50 latency
- Ranked with position numbers
- Shows location, model count, and key metric

#### 4️⃣ Pricing Comparison
Two pricing tables:
- **Free Models**: Top 20 models that cost $0
  - Great for testing and development
  - Includes providers like Baidu, Nvidia, Venice
- **Cheapest Paid Models**: Top 20 lowest-cost models
  - Shows prompt, completion, and total price
  - All prices per 1M tokens
  - Sorted by total price (prompt + completion)

### Filtering & Search

#### Search Box
- Searches provider names AND model IDs
- Example: "llama" finds all providers hosting Llama models
- Example: "DeepInfra" finds the DeepInfra provider
- Real-time filtering as you type

#### Location Filter
Dropdown with all available countries:
- US, CN, SG, FR, IL, NL, ID, SE
- Shows only providers from selected country
- Works with other filters

#### Min Models Filter
- Show only providers with at least N models
- Example: "10" shows only providers with 10+ models
- Good for finding major providers

#### Min Uptime Filter
- Show only providers with uptime ≥ N%
- Example: "99" shows only 99%+ uptime providers
- Good for finding most reliable providers

#### Filters Summary Bar
- Appears when any filter is active
- Shows what filters are applied
- Shows result count (e.g., "Showing 15 of 67 providers")
- "Clear Filters" button to reset all

### Provider Details Modal

Click any provider name to see:

**Overview Section**:
- Location & headquarters
- Total model count
- Average uptime (24 hours)
- Average latency (p50)
- Datacenters (when available)
- Tags (quantization variants, etc.)

**Pricing Section**:
- Prompt price range (min to max)
- Completion price range (min to max)
- Per 1M tokens

**Links Section** (when available):
- Privacy Policy
- Terms of Service
- Status Page

**Models List** (up to 50 shown):
- Model ID
- Pricing (prompt / completion)
- Context length
- Uptime percentage
- Latency (p50)

### Sorting

Click any column header to sort:
- **First click**: Sort descending (↓)
- **Second click**: Sort ascending (↑)
- **Visual indicator**: Arrow shows current sort direction
- **Active column**: Highlighted in blue

Default sort: By model count (descending)

---

## 🎯 Common Use Cases

### Find the Cheapest Provider for a Model
1. Go to "All Providers" tab
2. Search for the model (e.g., "llama-3.1-70b")
3. Results show all providers hosting it
4. Sort by "Price Range" column
5. Click provider to see exact pricing

### Find Fastest Providers
1. Go to "Performance Leaders" tab
2. Check "Lowest Latency" table
3. Top providers: Cerebras (199ms), Liquid (268ms), Cohere (295ms)

### Find Most Reliable Providers
1. Go to "Performance Leaders" tab
2. Check "Best Uptime" table
3. Many providers at 100% uptime

### Find Providers in a Specific Country
**Method 1**: Use filter
1. Go to "All Providers" tab
2. Select country from Location dropdown
3. See all providers in that country

**Method 2**: Use geography view
1. Go to "By Geography" tab
2. Scroll to desired country section
3. See all providers grouped by country

### Find Free Models
1. Go to "Pricing Comparison" tab
2. Check "Free Models" table
3. 20+ free options from various providers

### Find Providers with Many Models
1. Go to "All Providers" tab
2. Enter "20" in "Min Models" filter
3. See only providers with 20+ models
4. Or sort by "Models" column

---

## 🎨 Design Features

### Dark Theme
- Easy on the eyes
- Professional appearance
- High contrast for readability

### Color Coding
- **US**: Blue badge
- **China**: Red badge
- **Singapore**: Green badge
- **France**: Purple badge
- **Israel**: Pink badge
- **Netherlands**: Orange badge
- **Unknown**: Gray badge

### Visual Metrics
- **Progress Bars**: Show uptime visually
- **Color Gradient**: Purple to pink gradient
- **Hover Effects**: Tables highlight on hover
- **Smooth Animations**: Transitions and effects

### Responsive Design
- Works on desktop, tablet, and mobile
- Adapts layout to screen size
- Touch-friendly buttons

---

## 💡 Tips & Tricks

### Combine Filters
Stack multiple filters for precise results:
- Search: "deepseek"
- Location: "CN"
- Min Uptime: 95
- Result: DeepSeek models in China with 95%+ uptime

### Quick Provider Info
- Hover over provider names to see pointer cursor
- Click for instant modal with full details
- Press Escape or click outside to close modal

### Keyboard Shortcuts
- **Escape**: Close modal
- **Ctrl+F**: Browser search (works within page)

### Price Comparison
Prices are per 1M tokens:
- $0.0000004 = $0.40 per 1 billion tokens
- $0.000001 = $1.00 per 1 billion tokens
- Compare total price (prompt + completion)

### Understanding Metrics
- **Uptime**: Last 24 hours only (not long-term average)
- **Latency**: p50 means median (50th percentile)
- **Price Range**: Min to max across all their models

---

## 🔧 Customization

### Change Port
Edit `serve.py` line 9:
```python
PORT = 8000  # Change to any available port
```

### Modify Styling
Edit `index.html` in the `<style>` section:
- Colors: Search for color hex codes (e.g., `#667eea`)
- Fonts: Change `font-family` properties
- Spacing: Adjust `padding` and `margin` values

### Add Custom Filters
Edit the JavaScript section:
1. Add new filter input in HTML
2. Add filter logic in `applyFilters()` function
3. Update `updateFiltersSummary()` for display

---

## 📊 Data Source

The web UI loads data from: **`infrastructure_provider_map.json`**

This file is generated by: `python3 map_infrastructure_providers.py`

### Refresh Data
1. Run: `python3 map_infrastructure_providers.py` (takes ~2 minutes)
2. Refresh browser page (Ctrl+R or Cmd+R)
3. New data appears instantly

### Data Format
The JSON contains:
- 67 providers
- 368 models  
- Pricing for each model/provider combination
- Performance metrics (uptime, latency, throughput)
- Geographic data (headquarters, datacenters)

---

## 🐛 Troubleshooting

### Page Won't Load
**Problem**: Blank page or "Cannot read property" error
**Solution**: Make sure `infrastructure_provider_map.json` exists in same directory
**Check**: Open browser console (F12) to see error messages

### Data Not Showing
**Problem**: Page loads but shows "Loading..." forever
**Solution**: 
1. Check `infrastructure_provider_map.json` exists
2. Verify JSON is valid: `python3 -m json.tool infrastructure_provider_map.json > /dev/null`
3. Make sure web server has read permissions

### Port Already in Use
**Problem**: "Address already in use" error
**Solution**: 
1. Use different port: Edit `serve.py`
2. Or kill process using port: `lsof -ti:8000 | xargs kill`

### Filters Not Working
**Problem**: Filters don't seem to apply
**Solution**:
1. Clear all filters first (button at top)
2. Apply one filter at a time
3. Check browser console for JavaScript errors

### Modal Won't Close
**Problem**: Provider details modal stuck open
**Solution**:
1. Press Escape key
2. Click dark area outside modal
3. Refresh page if needed

### Slow Performance
**Problem**: Page is slow or laggy
**Solution**:
1. Close other browser tabs
2. Browser may struggle with 368 models × 67 providers
3. Use filters to reduce results shown
4. Clear browser cache

---

## 📱 Mobile Use

The interface is responsive and works on mobile:
- Tables scroll horizontally
- Touch-friendly tap targets
- Filters stack vertically
- Modal fills screen

**Best mobile experience**:
- Use landscape orientation for tables
- Use filters to reduce data shown
- Zoom in if text too small

---

## 🔗 Integration

### Embed in Another Page
```html
<iframe src="http://localhost:8000/index.html" 
        width="100%" 
        height="800px" 
        frameborder="0">
</iframe>
```

### Use as Data API
The JSON file can be loaded by other applications:
```javascript
fetch('infrastructure_provider_map.json')
  .then(r => r.json())
  .then(data => console.log(data));
```

### Export Table Data
1. Open browser console (F12)
2. Run: `copy(infraData)` to copy all data
3. Paste into spreadsheet or text editor

---

## 🎉 Advanced Features

### Custom Sort
Click column headers multiple times to:
1. Sort descending (largest first)
2. Sort ascending (smallest first)
3. Return to unsorted (click elsewhere)

### Multi-Column Filter
All filters work together:
- Search for model
- Filter by location
- Set minimum uptime
- Set minimum model count
- Results must match ALL filters

### Deep Linking
Share specific views by URL:
- `index.html` - Main view
- `index.html#providers` - Providers table
- `index.html#geography` - Geography view
- `index.html#performance` - Performance leaderboards
- `index.html#pricing` - Pricing comparison

**Note**: Deep linking to specific providers/models not yet implemented but can be added.

---

## 📝 Future Enhancements

Possible features to add:
- [ ] Export to CSV/Excel
- [ ] Save favorite providers
- [ ] Compare 2+ providers side-by-side
- [ ] Historical price tracking
- [ ] Real-time uptime monitoring
- [ ] Model availability alerts
- [ ] Provider status notifications
- [ ] Custom dashboards
- [ ] Advanced charts (graphs, heatmaps)
- [ ] Direct links to provider websites
- [ ] Model performance comparisons
- [ ] Cost calculator (estimate usage costs)

---

## 🆘 Support

For issues or questions:
1. Check browser console (F12) for errors
2. Verify `infrastructure_provider_map.json` is valid
3. Try refreshing the page
4. Try clearing browser cache
5. Check if data file is up to date

**Common Issues**:
- JSON file missing → Run `map_infrastructure_providers.py`
- Old data → Re-run mapper script to refresh
- Slow page → Use filters to reduce data shown
- Styling issues → Hard refresh (Ctrl+Shift+R)

---

## 📄 Files

- **index.html** - Main web interface (single file, no dependencies)
- **infrastructure_provider_map.json** - Data file
- **serve.py** - Simple HTTP server script
- **WEB_UI_GUIDE.md** - This guide

All you need is the HTML file and JSON file. The HTML is self-contained with embedded CSS and JavaScript.
