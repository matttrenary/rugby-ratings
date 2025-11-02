from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime, timedelta
import pytz
import sys

def replace_element(html, element_type, id, new_html):
    """Replaces a specific element within an html block with new html

    Args:
        html: The full html text with the replaceable text
        element_type: The element type that will be replaced
        id: The id of the element to be replaced
        new_html: The new html doing the replacing

    Returns:
        html with replaced text
    """
    
    soup = BeautifulSoup(html, 'html.parser')
    soup2 = BeautifulSoup(new_html, 'html.parser')

    soup.find(element_type, {'id': id}).replace_with(soup2)

    return str(soup)

def load_range(df, days_num_back, days_num_forward):
    """Filters dataframe, pulling only the games within specified days back

    Args:
        df: The dataframe of games
        days: The number of days back to include

    Returns:
        DataFrame with subset of games
    """

    # Arrange date objects
    days_ago = datetime.now(pytz.timezone('America/New_York')).date() - timedelta(days=days_num_back)
    days_ahead = datetime.now(pytz.timezone('America/New_York')).date() + timedelta(days=days_num_forward)
    df['Date'] = pd.to_datetime(df['Date'], format='mixed').dt.date
    
    # Filter df to our subset of games
    df = df[(df['Date'] >= days_ago) & (df['Date'] <= days_ahead)].copy()

    # Restyle Date column
    df.Date = pd.to_datetime(df.Date)
    if sys.platform.startswith('win'):
        # Code for Windows OS goes here
        df.Date = df.Date.dt.strftime('%b %e, %Y')
    else:
        # Code for MacOS (Darwin), as well as other other systems, goes here
        df.Date = df.Date.dt.strftime('%b %-d, %Y')

    return df
