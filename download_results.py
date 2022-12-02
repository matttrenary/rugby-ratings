# -*- coding: utf-8 -*-
"""
Created on Wed Nov 23 21:32:56 2022

@author: trenary
"""
import argparse
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials

workbook_name = "College Rugby Results"

def parse_arguments():
    """Parse arguments when executed from CLI"""
    parser = argparse.ArgumentParser(
        prog="download-results",
        description="CLI tool to download GSheet rugby results",
    )
    parser.add_argument(
        "--code",
        choices=["15s", "7s", "both"],
        default="both",
        help="15s or 7s results",
    )
    args = parser.parse_args()
    return args

def download_results(code):
    """Download results using the Google Sheets API"""
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    credentials = ServiceAccountCredentials.from_json_keyfile_name(
        "GDriveCredential.json", scope
    )
    client = gspread.authorize(credentials)
    workbook = client.open(workbook_name)

    worksheet = workbook.worksheet(code)
    sheet_values = worksheet.get_all_values()

    print(f"Downloading: {worksheet.title}")
    fname = worksheet.title + ".csv"
    df = pd.DataFrame(sheet_values)
    # Handle initial columns being numeric index
    df.columns = df.iloc[0]
    df = df.drop(0)
    df.to_csv(fname, index=False)

def main(args):
    print(f"### Downloading results: {args.code} ###")

    code = args.code
    if code == '15s' or code == 'both':
        download_results('15s')
    if code == '7s' or code == 'both':
        download_results('7s')
    pass

if __name__ == "__main__":
    arguments = parse_arguments()
    main(arguments)
