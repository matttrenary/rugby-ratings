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

workbook_name = "College Rugby Results"

def parse_arguments():
    """Parse arguments when executed from CLI"""
    parser = argparse.ArgumentParser(
        prog="calc-elo",
        description="CLI tool to calculate Elo ratings from game results",
    )
    parser.add_argument(
        "--code",
        choices=["15s", "7s", "both"],
        default="both",
        help="15s or 7s results",
    )
    parser.add_argument(
        "--refresh",
        choices=["all", "new"],
        default="new",
        help="all past games or only those without ratings",
    )
    args = parser.parse_args()
    return args

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
    print('today:', today)
    last_week =  (now - timedelta(days=7)).strftime("%m-%d")
    print('lastWk:', last_week)

    # Iterate to calculate ELOs
    last_week_calculated = False
    for index, row in df.iterrows():
        # Once at lastWk, grab the week-old rankings
        if row.Date > last_week and not last_week_calculated:
            week_old_teams, _ = rank_teams(teams, df, today, last_week_calculated)
            old_ranks = week_old_teams['Rank']
            print(old_ranks)
            last_week_calculated = True

        game = Game(row.Team1, row.Score1, row.Team2, row.Score2, row.Neutral, row.Additional)
        set_elo(game, teams)

        if not pd.isna(game.margin):
            calculate_elo(game, teams)
            update_results(df, index, game)
        else:
            update_results_nan(df, index, game)

    # Rank teams based on final ELO results
    teams, df = rank_teams(teams, df, today, last_week_calculated)
    teams['old_rank'] = old_ranks
    teams['Movement'] = teams['Rank'] - teams['old_rank']
    print(teams)
    return teams, df

def rank_teams(teams, df, today, last_week_calculated):
    # Modify df to limit rankings to this school year
    if today < '07-01':
        lastYear = int(now.strftime("%Y")) - 1
        lastCutoff = str(lastYear) + "-07-01"
        nextCutoff = now.strftime("%Y-07-01")
    else:
        lastCutoff = now.strftime("%Y-07-01")
        nextYear = int(now.strftime("%Y")) + 1
        nextCutoff = str(nextYear) + "-07-01"
    pairwise_games =  df.loc[(df['Date'] >= lastCutoff) & (df['Date'] < nextCutoff) & (df.Score1>=0) & (df.Score2>=0)]
    # Ensure recent games aren't included if last_week_calculated = False
    if not last_week_calculated:
        now = now.astimezone(pytz.timezone('US/Eastern'))
        last_week = (now.strftime("%m-%d") - timedelta(days=7)).strftime("%m-%d")
        pairwise_games =  pairwise_games.loc[(pairwise_games['Date'] <= last_week)]

    teams, opponentsMatrix = calculate_pairwise(teams[teams['Eligible']], teams, pairwise_games)

    teams = teams.sort_values(by=['Pairwise', 'Eligible', 'Elo'], ascending=False).copy()
    # Catch Pairwise tiebreakers
    teams = pairwise_tiebreakers(teams, opponentsMatrix)
    teams = teams.sort_values(by=['Pairwise', 'Eligible', 'TiebreakPairwise', 'Elo'], ascending=False).copy()

    teams['Elo'] = teams['Elo'].round(0).astype(int)
    teams['Rank'] = range(1, len(teams) + 1)
    df = format_results(df)
    return teams, df

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

def set_elo(game, teams):
    game.elo1 = teams.loc[game.team1, 'Elo']
    game.elo2 = teams.loc[game.team2, 'Elo']

def calculate_elo(game, teams):
    # Elo coefficients
    k = 40
    x = 2 if game.margin == 0 else 1
    margin_coef = np.log(game.margin + x)
    if game.neutral != 'Yes':
        game.home_coef = 75

    # Auto correlation coefficient
    game.autocor = autocor(game)

    rdiff = game.elo2 - (game.elo1 + game.home_coef)
    we = 1/(10**(rdiff/400)+1)

    game.adjust1 = k*margin_coef*game.autocor*(game.win1-we)
    game.adjust2 = -1*game.adjust1

    game.rn1 = game.elo1 + game.adjust1
    game.rn2 = game.elo2 + game.adjust2

    teams.loc[game.team1, 'Elo'] = game.rn1
    teams.loc[game.team2, 'Elo'] = game.rn2

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
            # Criteria 1: Head to Head
            wlt = opponents[opponent]
            if wlt[0] > wlt[1]:
                allTeams.loc[team, 'Pairwise'] += 1
                continue
            elif wlt[0] < wlt[1]:
                continue
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
                allTeams.loc[team, 'Pairwise'] += 1
                continue
            elif teamWinPct < oppoWinPct:
                continue
            # Criteria 3: ELO
            if teams.loc[team, 'Elo'] > teams.loc[opponent, 'Elo']:
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
                # Criteria 1: Head to Head
                wlt = opponentsMatrix[team][opponent]
                if wlt[0] > wlt[1]:
                    teams.loc[team, 'TiebreakPairwise'] += 1
                    continue
                elif wlt[0] < wlt[1]:
                    continue
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
                    teams.loc[team, 'TiebreakPairwise'] += 1
                    continue
                elif teamWinPct < oppoWinPct:
                    continue
                # Criteria 3: ELO
                if teams.loc[team, 'Elo'] > teams.loc[opponent, 'Elo']:
                    teams.loc[team, 'TiebreakPairwise'] += 1
        # Reset variables in order to continue iterating
        i = j + 1
        currPWR = teams['Pairwise'].iloc[i]
    return teams


def autocor(game):
    if game.win1 == 1:
        autocor = 2.2/(((game.elo1+game.home_coef)-game.elo2)*.001+2.2)
    elif game.win2 == 1:
        autocor = 2.2/((game.elo2-(game.elo1+game.home_coef))*.001+2.2)
    else:
        autocor = 1
    return autocor

def update_results(df, index, game):
    df.loc[index, 'elo1'] = game.elo1
    df.loc[index, 'elo2'] = game.elo2
    df.loc[index, 'rn1'] = game.rn1
    df.loc[index, 'rn2'] = game.rn2
    df.loc[index, 'adjust1'] = game.adjust1
    df.loc[index, 'adjust2'] = game.adjust2

def update_results_nan(df, index, game):
    df.loc[index, 'elo1'] = game.elo1
    df.loc[index, 'elo2'] = game.elo2
    df.loc[index, 'rn1'] = np.nan
    df.loc[index, 'rn2'] = np.nan
    df.loc[index, 'adjust1'] = np.nan
    df.loc[index, 'adjust2'] = np.nan

def format_results(df):
    # Prep for turning numeric columns to strs
    df['adjust1'] = df['adjust1'].astype('string')
    df['adjust2'] = df['adjust2'].astype('string')
    df['Score1'] = df['Score1'].astype('string')
    df['Score2'] = df['Score2'].astype('string')

    # Don't like this long-term
    for index, row in df.iterrows():
        try:
            df.loc[index, 'elo1'] = int(round(row.elo1))
            df.loc[index, 'elo2'] = int(round(row.elo2))
        except:
            None
        
        try:
            df.loc[index, 'rn1'] = int(round(row.rn1))
            df.loc[index, 'rn2'] = int(round(row.rn2))
        except:
            None

        try:
            if round(float(row.adjust1)) < 1:
                df.loc[index, 'adjust1'] = str(int(round(float(row.adjust1))))
            else:
                df.loc[index, 'adjust1'] = '+' + str(int(round(float(row.adjust1))))
            
            if round(float(row.adjust2)) < 1:
                df.loc[index, 'adjust2'] = str(int(round(float(row.adjust2))))
            else:
                df.loc[index, 'adjust2'] = '+' + str(int(round(float(row.adjust2))))
        except:
            None

    df['elo1'] = df['elo1'].round(0).astype(int)
    df['elo2'] = df['elo2'].round(0).astype(int)

    df.adjust1 = df.adjust1.fillna('')
    df.adjust2 = df.adjust2.fillna('')
    df.Score1 = df.Score1.fillna('')
    df.Score2 = df.Score2.fillna('')
    
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

def generate_from_df(df, template_file, id, **kwargs):
    data = []
    for index, row in df.iterrows():
        data = data + [row.to_dict()]

    if id[-2:] == '7s':
        linkExt = '#7s'
    else:
        linkExt = ''

    return(generate_page(data, template_file, id=id, linkExt=linkExt, **kwargs))

def generate_page(content, template_file, **kwargs):
    """Generate site in local directory"""

    template_loader = jinja2.FileSystemLoader(searchpath="./templates/")
    template_env = jinja2.Environment(loader=template_loader)
    template = template_env.get_template(template_file)

    now = datetime.now()
    now = now.astimezone(pytz.timezone('US/Eastern'))
    if sys.platform.startswith('win'):
        # Code for Windows OS goes here
        now = now.strftime("%#I:%M %p on %h %#d, %Y %Z")
    else:
        # Code for MacOS (Darwin), as well as other other systems, goes here
        now = now.strftime("%-I:%M %p on %h %-d, %Y %Z")

    return(template.render(data=content, timestamp=now, **kwargs))

def generate_teams(team15s, team7s, results15s, results7s):
    teams = pd.concat([team15s, team7s]).drop_duplicates()

    for index, row in teams.iterrows():
        
        games15s = results15s[(results15s.Team1==row.Team) | (results15s.Team2==row.Team)].copy()
        body15s = generate_from_df(games15s,
                                   "_results_table.html",
                                   id='results15s',
                                   title=f'{row.Team} 15s Results',
                                   active='show active')

        games7s = results7s[(results7s.Team1==row.Team) | (results7s.Team2==row.Team)].copy()
        body7s = generate_from_df(games7s,
                                  "_results_table.html",
                                  id='results7s',
                                  title=f'{row.Team} 7s Results')

        content = body15s + body7s
        content = generate_page(content, 'team_template.html', content_title=row.Team)

        page_name = 'teams/' + row.TeamLink + '.html'
        save_page(page_name, content)

def rebuild_front(df_15s, df_7s):
    # Generate table
    body_15s = generate_from_df(df_15s,
                            '_results_table.html',
                            id='recent_results_15s',
                            active='show active')
    body_7s = generate_from_df(df_7s,
                            '_results_table.html',
                            id='recent_results_7s',
                            active='show active')

    now = datetime.now()
    now = now.astimezone(pytz.timezone('US/Eastern'))
    if sys.platform.startswith('win'):
        # Code for Windows OS goes here
        now = now.strftime("%#I:%M %p on %h %#d, %Y %Z")
    else:
        # Code for MacOS (Darwin), as well as other other systems, goes here
        now = now.strftime("%-I:%M %p on %h %-d, %Y %Z")
    now = f'<p id="results_timestamp" style="text-align: center;">All information as of {now}</p>'

    # Replace html on front page
    with open('results.html', 'r+') as front_page:
        new_html = local_utils.replace_element(front_page.read(),
                                               'div',
                                               'recent_results_15s',
                                               body_15s)
        new_html = local_utils.replace_element(new_html,
                                               'div',
                                               'recent_results_7s',
                                               body_7s)
        new_html = local_utils.replace_element(new_html,
                                               'p',
                                               'results_timestamp',
                                               now)
        save_page('results.html', new_html)

def save_page(page_name, content):
    with open(page_name, "w+") as f:
        f.write(content)

class Game:
    def __init__(self, team1, score1, team2, score2, neutral, additional):
        self.team1 = team1
        self.score1 = score1
        self.team2 = team2
        self.score2 = score2
        self.neutral = neutral
        self.additional = additional
        self.home_coef = 0
        self.calc_margin()
        self.calc_winloss()

    def calc_margin(self):
        try:
            self.score1 >= 0
            self.score2 >= 0
        except:
            self.margin = np.nan
        else:
            self.margin = abs(self.score1 - self.score2)

    def calc_winloss(self):
        try:
            if self.score1 > self.score2:
                self.win1 = 1
                self.win2 = 0
            elif self.score1 < self.score2:
                self.win1 = 0
                self.win2 = 1
            else:
                self.win1 = .5
                self.win2 = .5
        except:
            self.win1 = np.nan
            self.win2 = np.nan

def main():
    # 15s
    games15s = download_results('15s')
    rankings15s, results15s = load_results(games15s)
    rankings15s = rankings15s.reset_index().copy()

    body_rankings15s = generate_from_df(rankings15s,
                                        '_rankings_table.html',
                                        id='rankings15s',
                                        active='show active')

    # 7s
    games7s = download_results('7s')
    rankings7s, results7s = load_results(games7s)
    rankings7s = rankings7s.reset_index().copy()

    body_rankings7s = generate_from_df(rankings7s,
                                        '_rankings_table.html',
                                        id='rankings7s')

    # Rankings
    body_rankings = body_rankings15s + body_rankings7s
    content_rankings = generate_page(body_rankings,
                                    'rankings_template.html',
                                    content_title='Division 1 College Rugby Rankings')
    save_page('index.html', content_rankings)

    # Team pages
    generate_teams(rankings15s, rankings7s, results15s, results7s)

    # Update frontpage with recent results
    game_subset_15s = local_utils.load_range(results15s, 2, 2)
    game_subset_7s = local_utils.load_range(results7s, 2, 2)
    rebuild_front(game_subset_15s, game_subset_7s)

if __name__ == "__main__":
    main()
