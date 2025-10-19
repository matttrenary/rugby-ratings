# rugby-ratings
_calculate and publish rugby team ratings based on game results_

## The Process
- rebuild.py runs automatically via GitHub Actions.
- It pulls scores from a Google Spreadsheet, calculates team ratings and rankings, and then produces html pages via Jinja.
- The built-in GitHub Pages Action then processes the html and markdown to complete a site refresh.
- Certain pages (about, thankyou, etc.) are not part of the rebuild and are updated manually as needed.

## Local Development
Follow the below steps to get up and running locally:
1. Add text within .gitignore'd GDriveCredential.json to `GSPREAD_CREDENTIALS` environment variable
2. Create a new conda (`conda env create -f requirements.yml`) or pip venv (`python -m venv venv ; pip install -r requirements.txt`) environment
3. Activate the conda (`conda activate rugbyhawk`) or pip venv (`source venv/bin/activate`) environment
4. Set the GSPREAD\_CREDENTIALS environment variable using either Linux/MacOS bash (`export GSPREAD_CREDENTIALS=$(<GDriveCredential.json)`) or Windows PowerShell (`$GSPREAD_CREDENTIALS = Get-Content -Raw -Path "GDriveCredential.json"`)
5. Run rebuild.py (`python rebuild.py`) to apply the changes you made to the code
6. Host rugbyhawk locally (`python -m http.server`) to see how the changes you made look

## Contributors
- Matt Trenary
- George Janke
- Raymond Li
- Luke Zana
