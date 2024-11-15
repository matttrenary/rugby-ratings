# rugby-ratings
Calculates and publishes team rugby ratings based on game results

# Process
- rebuild.py is scheduled via GitHub Actions
- It pulls scores from a Google Spreadsheet, calculates the ratings and rankings, and then produces html pages via Jinja
- The built-in GitHub Pages Action then processes the html and markdown to complete the site refresh
- Certain pages (about, thankyou, etc.) are not part of the rebuild and are updated manually as needed
