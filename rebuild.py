# -*- coding: utf-8 -*-
"""
Created on Thu Nov 17 14:24:45 2022

@author: trenary
"""
import os
import ast
import sys
import gspread
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta
import jinja2
from dateutil.tz import tzlocal
import pytz
import local_utils
from game import Game
from site_generator import SiteGenerator

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

def load_results(df):
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
    # Prepare teams ELO list
    teams = pd.concat([df.Team1, df.Team2]).rename('Team').to_frame()
    teams = teams.drop_duplicates()
    teams['Elo'] = 1500.00
    teams['TeamLink'] = team_link(teams.Team)
    teams = teams.set_index('Team')
    # Prepare columns for pairwise calculation
    teams['Pairwise'] = 0
    teams['WLT'] = "0-0-0"

    teams = qualify_teams(teams, df)
    # Set ineligible teams to a lower starting ELO
    teams[~teams['Eligible']] = teams[~teams['Eligible']].assign(Elo=1300)

    # Determine date cutoffs
    now = datetime.now()
    now = now.astimezone(pytz.timezone('US/Eastern'))
    today = now.strftime("%m-%d")
    last_week =  (now - timedelta(days=7)).strftime("%Y-%m-%d")

    # Iterate to calculate ELOs
    last_week_calculated = False
    for index, row in df.iterrows():
        # Once at lastWk, grab the week-old rankings
        if row.Date.strftime("%Y-%m-%d") > last_week and not last_week_calculated:
            week_old_teams = rank_teams(teams, df, today, last_week_calculated)
            old_ranks = week_old_teams['Rank']
            last_week_calculated = True

        game = Game(row.Team1, row.Score1, row.Team2, row.Score2, row.Neutral, row.Additional)
        game.set_elo(teams)

        if not pd.isna(game.margin):
            game.calculate_elo(teams)
            game.update_results(df, index)
        else:
            game.update_results_nan(df, index)

    # Rank teams based on final ELO results
    teams = rank_teams(teams, df, today, last_week_calculated)
    if last_week_calculated:
        teams['Movement'] = old_ranks - teams['Rank']
    else:
        teams['Movement'] = 0
    df = format_results(df)
    return teams, df

def filter_games(df, start, end, upper=None):
    mask = (df['Date'] >= start) & (df['Date'] < end) & (df.Score1 >= 0) & (df.Score2 >= 0)
    if upper is not None:
        mask &= df['Date'] <= upper
    return df.loc[mask]

def rank_teams(teams, df, today, last_week_calculated):
    # Work on a copy so mutations don't bleed back to the caller between calls
    teams = teams.copy()
    teams['Pairwise'] = 0
    # Modify df to limit rankings to this school year
    now = datetime.now()
    now = now.astimezone(pytz.timezone('US/Eastern'))
    if today < '07-01':
        # backYear and backCutoff assist with disqualifying idle teams
        backYear = int(now.strftime("%Y")) - 2
        lastYear = int(now.strftime("%Y")) - 1
        backCutoff = str(backYear) + "-07-01"
        lastCutoff = str(lastYear) + "-07-01"
        nextCutoff = now.strftime("%Y-07-01")
    else:
        # backYear and backCutoff assist with disqualifying idle teams
        backYear = int(now.strftime("%Y")) - 1
        backCutoff = str(backYear) + "-07-01"
        lastCutoff = now.strftime("%Y-07-01")
        nextYear = int(now.strftime("%Y")) + 1
        nextCutoff = str(nextYear) + "-07-01"

    # Ensure recent games aren't included if last_week_calculated = False
    upper = (now - timedelta(days=7)).strftime("%Y-%m-%d") if not last_week_calculated else None
    pairwise_games = filter_games(df, lastCutoff, nextCutoff, upper)
    active_games = filter_games(df, backCutoff, nextCutoff, upper)

    # Disqualify idle teams
    for team in list(teams.index):
        if team not in list(active_games['Team1']) and team not in list(active_games['Team2']):
            teams.loc[team, 'Eligible'] = False

    teams, opponentsMatrix = calculate_pairwise(teams[teams['Eligible']], teams, pairwise_games)

    teams = teams.sort_values(by=['Pairwise', 'Eligible', 'Elo'], ascending=False).copy()
    # Catch Pairwise tiebreakers
    teams = pairwise_tiebreakers(teams, opponentsMatrix)
    teams = teams.sort_values(by=['Pairwise', 'Eligible', 'TiebreakPairwise', 'Elo'], ascending=False).copy()

    teams['Elo'] = teams['Elo'].round(0).astype(int)
    teams['Rank'] = range(1, len(teams) + 1)
    return teams

def qualify_teams(teams, df):
    # Tally each team's number of games
    numGames = dict.fromkeys(list(teams.index.values), 0)
    for index in df.index:
        numGames[df['Team1'][index]] = numGames[df['Team1'][index]] + 1
        numGames[df['Team2'][index]] = numGames[df['Team2'][index]] + 1
    # Remove teams with less than 5 games
    numGames2 = numGames.copy()
    for key, value in numGames.items():
        if (value < 5):
            numGames2.pop(key)
    possible = numGames2
    # Find teams without enough Connectivity
    eligible = []
    newEligible = []
    newEligible.append(max(possible, key=possible.get))
    possible.pop(newEligible[0])
    # Start with the top two teams in terms of games played
    newEligible.append(max(possible, key=possible.get))
    possible.pop(newEligible[1])
    while (len(newEligible) > 0):
        eligible = eligible + newEligible
        newEligible = []
        possible = dict.fromkeys(possible, 0)
        for index in df.index:
            if (df['Team1'][index] in eligible) and (df['Team2'][index] in possible):
                possible[df['Team2'][index]] = possible[df['Team2'][index]] + 1
            elif (df['Team2'][index] in eligible) and (df['Team1'][index] in possible):
                possible[df['Team1'][index]] = possible[df['Team1'][index]] + 1
        possible2 = possible.copy()
        for key, value in possible.items():
            # connectivity coefficient C=3
            if (value >= 3):
                newEligible.append(key)
                possible2.pop(key)
        possible = possible2
    # Add eligibility to teams dataframe
    teams['Eligible'] = False
    for team in eligible:
        teams.loc[team, 'Eligible'] = True
    return teams


def pairwise_wins(team, opponent, opponentsMatrix, teams):
    """Return True if team wins the 3-criteria pairwise comparison against opponent."""
    completeTeams = list(teams.index.values)

    # Criteria 1: Head to Head
    wlt = opponentsMatrix[team][opponent]
    if wlt[0] > wlt[1]:
        return True
    elif wlt[0] < wlt[1]:
        return False

    # Criteria 2: Common Opponents
    teamWinPct = 0
    oppoWinPct = 0
    for common in completeTeams:
        teamWLT = opponentsMatrix[team][common]
        oppoWLT = opponentsMatrix[opponent][common]
        if (teamWLT == [0,0,0]) or (oppoWLT == [0,0,0]):
            continue
        teamGs = teamWLT[0] + teamWLT[1] + teamWLT[2]
        teamWinPct = teamWinPct + (teamWLT[0] + 0.5 * teamWLT[2]) / teamGs
        oppoGs = oppoWLT[0] + oppoWLT[1] + oppoWLT[2]
        oppoWinPct = oppoWinPct + (oppoWLT[0] + 0.5 * oppoWLT[2]) / oppoGs
    if teamWinPct > oppoWinPct:
        return True
    elif teamWinPct < oppoWinPct:
        return False

    # Criteria 3: ELO
    return teams.loc[team, 'Elo'] > teams.loc[opponent, 'Elo']


def calculate_pairwise(teams, allTeams, df):
    # Create matrix containing: teams > opponents > WLT vs that opponent
    eligibleTeams = list(teams.index.values)
    completeTeams = list(allTeams.index.values)
    opponentsMatrix = {team: ({oppo: [0, 0, 0] for oppo in completeTeams}) for team in completeTeams}
    # Create environment to track total WLT
    for team in completeTeams:
        opponentsMatrix[team]['TOTAL'] = [0, 0, 0]
    for index in df.index:
        score1 = df['Score1'][index]
        score2 = df['Score2'][index]
        team1 = df['Team1'][index]
        team2 = df['Team2'][index]
        if (score1 > score2):
            opponentsMatrix[team1][team2][0] += 1
            opponentsMatrix[team1]['TOTAL'][0] += 1
            opponentsMatrix[team2][team1][1] += 1
            opponentsMatrix[team2]['TOTAL'][1] += 1
        elif (score2 > score1):
            opponentsMatrix[team2][team1][0] += 1
            opponentsMatrix[team2]['TOTAL'][0] += 1
            opponentsMatrix[team1][team2][1] += 1
            opponentsMatrix[team1]['TOTAL'][1] += 1
        else:
            opponentsMatrix[team1][team2][2] += 1
            opponentsMatrix[team1]['TOTAL'][2] += 1
            opponentsMatrix[team2][team1][2] += 1
            opponentsMatrix[team2]['TOTAL'][2] += 1
    # Iterate through each team; conduct pairwise on that team
    for team, opponents in opponentsMatrix.items():
        # First, set that team's WLT
        totalWLT = opponentsMatrix[team]['TOTAL']
        allTeams.loc[team, 'WLT'] = f"{totalWLT[0]}-{totalWLT[1]}-{totalWLT[2]}"
        if team not in eligibleTeams:
            continue
        for opponent in eligibleTeams:
            if opponent == team:
                continue
            if pairwise_wins(team, opponent, opponentsMatrix, allTeams):
                allTeams.loc[team, 'Pairwise'] += 1
    # Output complete teams.Pairwise column
    return allTeams, opponentsMatrix

def pairwise_tiebreakers(teams, opponentsMatrix):
    completeTeams = list(teams.index.values)
    teams['TiebreakPairwise'] = 0
    i = 0
    currPWR = teams['Pairwise'].iloc[i]
    while currPWR != 0:
        j = i
        teamsTied = [completeTeams[i]]
        while teams['Pairwise'].iloc[j + 1] == currPWR:
            j += 1
            teamsTied.append(completeTeams[j])
        numTied = j - i + 1
        if (numTied < 2):
            i = j + 1
            currPWR = teams['Pairwise'].iloc[i]
            continue
        # Run new pairwise on tied teams
        for team in teamsTied:
            for opponent in teamsTied:
                if opponent == team:
                    continue
                if pairwise_wins(team, opponent, opponentsMatrix, teams):
                    teams.loc[team, 'TiebreakPairwise'] += 1
        # Reset variables in order to continue iterating
        i = j + 1
        currPWR = teams['Pairwise'].iloc[i]
    return teams



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

def main():
    site = SiteGenerator()

    # 15s
    games15s = download_results('15s')
    rankings15s, results15s = load_results(games15s)
    rankings15s = rankings15s.reset_index().copy()

    body_rankings15s = site.generate_from_df(rankings15s,
                                             '_rankings_table.html',
                                             id='rankings15s',
                                             active='show active')

    # 7s
    games7s = download_results('7s')
    rankings7s, results7s = load_results(games7s)
    rankings7s = rankings7s.reset_index().copy()

    body_rankings7s = site.generate_from_df(rankings7s,
                                            '_rankings_table.html',
                                            id='rankings7s')

    # Rankings
    body_rankings = body_rankings15s + body_rankings7s
    content_rankings = site.generate_page(body_rankings,
                                          'rankings_template.html',
                                          content_title='Division 1 College Rugby Rankings')
    site.save_page('index.html', content_rankings)

    # Team pages
    site.generate_teams(rankings15s, rankings7s, results15s, results7s)

    # Update frontpage with recent results
    game_subset_15s = local_utils.load_range(results15s, 2, 2)
    game_subset_7s = local_utils.load_range(results7s, 2, 2)
    site.rebuild_front(game_subset_15s, game_subset_7s)

if __name__ == "__main__":
    main()
