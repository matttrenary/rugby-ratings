import os
import ast
import sys
import gspread
import pandas as pd
import numpy as np

workbook_name = "College Rugby Results"


def download_results(code):
    """Download results using the Google Sheets API"""

    credentials = ast.literal_eval(os.environ["GSPREAD_CREDENTIALS"])
    client = gspread.service_account_from_dict(credentials)
    workbook = client.open(workbook_name)

    worksheet = workbook.worksheet(code)
    sheet_values = worksheet.get_all_values()

    print(f"Downloading: {worksheet.title}")
    df = pd.DataFrame(sheet_values)
    # Handle initial columns being numeric index
    df.columns = df.iloc[0]
    df = df.drop(0)
    return df


def clean_results(df):
    # Format dates
    df['Date'] = df['Date'].replace(r'^([1-9]/)', r'0\1', regex=True)
    df['Date'] = df['Date'].replace(r'/([1-9]/)', r'/0\1', regex=True)
    df['Date'] = pd.to_datetime(df['Date'], format="%m/%d/%y")
    # Only games with two teams
    df = df[~(df.Team1.isnull()) & ~(df.Team2.isnull())].copy()
    df = df[(df.Team1!='') & (df.Team2!='')].copy()
    # Ensure scores are ints
    df.Score1 = df.Score1.replace('', np.nan).astype('Int64')
    df.Score2 = df.Score2.replace('', np.nan).astype('Int64')
    return df


def format_adjustment(val):
    try:
        n = int(round(float(val)))
        return str(n) if n < 1 else f'+{n}'
    except (ValueError, TypeError):
        return ''


def format_results(df):
    df['elo1'] = df['elo1'].round(0).astype(int)
    df['elo2'] = df['elo2'].round(0).astype(int)
    df['rn1'] = pd.to_numeric(df['rn1'], errors='coerce').round(0).astype('Int64')
    df['rn2'] = pd.to_numeric(df['rn2'], errors='coerce').round(0).astype('Int64')

    df['adjust1'] = df['adjust1'].apply(format_adjustment)
    df['adjust2'] = df['adjust2'].apply(format_adjustment)

    df['Score1'] = df['Score1'].astype('string').fillna('')
    df['Score2'] = df['Score2'].astype('string').fillna('')

    df['Team1Link'] = team_link(df.Team1)
    df['Team2Link'] = team_link(df.Team2)

    # Make it so that recent results show up before earlier ones
    df = df.sort_values(by=['Date','Seq'], ascending=[False,False])
    if sys.platform.startswith('win'):
        # Code for Windows OS goes here
        df.Date = df.Date.dt.strftime('%b %e, %Y')
    else:
        # Code for MacOS (Darwin), as well as other other systems, goes here
        df.Date = df.Date.dt.strftime('%b %-d, %Y')

    return df


def team_link(series):
    series = series.str.lower()
    series = series.str.replace(' ','', regex=False)
    series = series.str.replace("'",'', regex=False)
    series = series.str.replace('.','', regex=False)
    series = series.str.replace('&','', regex=False)
    series = series.str.replace('(','', regex=False)
    series = series.str.replace(')','', regex=False)
    return series
