# -*- coding: utf-8 -*-
"""
Created on Thu Nov 17 14:24:45 2022

@author: trenary
"""
import argparse
import os
import ast
import gspread
import pandas as pd
import numpy as np
import time
from datetime import datetime
import jinja2
from dateutil.tz import tzlocal
import pytz

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
    df['Date'] = df['Date'].replace(r'^([1-9]/)', r'0\1', regex=True)
    df['Date'] = df['Date'].replace(r'/([1-9]/)', r'/0\1', regex=True)
    df['Date'] = pd.to_datetime(df['Date'], format="%m/%d/%y")

    # Only games with scores for both teams
    df = df[~(df.Score1.isnull()) & ~(df.Score2.isnull())].copy()
    df = df[(df.Score1!='') & (df.Score2!='')].copy()

    # Ensure scores are ints for accurate comparison
    df = df.astype({'Score1': 'int', 'Score2': 'int'})

    ### Prepare teams ELO list
    teams = pd.concat([df.Team1, df.Team2]).rename('Team').to_frame()
    teams = teams.drop_duplicates()
    teams['Elo'] = 1500.00
    teams['TeamLink'] = team_link(teams.Team)
    teams = teams.set_index('Team')

    teams = qualify_teams(teams, df)
    # Set ineligible teams to a lower starting ELO
    teams[~teams['Eligible']] = teams[~teams['Eligible']].assign(Elo=1300)

    for index, row in df.iterrows():
        game = Game(row.Team1, row.Score1, row.Team2, row.Score2, row.Neutral, row.Additional)
        calculate_elo(game, teams)
        update_results(df, index, game)

    teams['Pairwise'] = 0
    teams['WLT'] = "0-0-0"
    # Modify df to limit rankings to this school year
    now = datetime.now()
    today = now.strftime("%m-%d")
    if today < '07-01':
        lastYear = int(now.strftime("%Y")) - 1
        lastCutoff = str(lastYear) + "-07-01"
        nextCutoff = now.strftime("%Y-07-01")
    else:
        lastCutoff = now.strftime("%Y-07-01")
        nextYear = int(now.strftime("%Y")) + 1
        nextCutoff = str(nextYear) + "-07-01"

    teams, opponentsMatrix = calculate_pairwise(teams[teams['Eligible']], teams,
        df.loc[(df['Date'] >= lastCutoff) & (df['Date'] < nextCutoff)])

    teams = format_ratings(teams, 'Elo')
    teams = teams.sort_values(by=['Pairwise', 'Eligible', 'Elo'], ascending=False).copy()

    # Catch Pairwise tiebreakers
    teams = pairwise_tiebreakers(teams, opponentsMatrix)
    teams = teams.sort_values(by=['Pairwise', 'Eligible', 'TiebreakPairwise', 'Elo'], ascending=False).copy()

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

def calculate_elo(game, teams):
    # Elo coefficients
    k = 40
    x = 2 if game.margin == 0 else 1
    margin_coef = np.log(game.margin + x)
    if game.neutral != 'Yes':
        game.home_coef = 75

    game.elo1 = teams.loc[game.team1, 'Elo']
    game.elo2 = teams.loc[game.team2, 'Elo']

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

def format_ratings(df, rating='Elo', sort=True):
    df[rating] = df[rating].round(0).astype(int)
    if sort:
        df = df.sort_values(by=rating, ascending=False).copy()
    return df

def format_results(df):
    df.Score1 = df.Score1.astype(int)
    df.Score2 = df.Score2.astype(int)
    df = format_ratings(df, 'elo1', False)
    df = format_ratings(df, 'elo2', False)
    df = format_ratings(df, 'rn1', False)
    df = format_ratings(df, 'rn2', False)
    df = format_ratings(df, 'adjust1', False)
    df = format_ratings(df, 'adjust2', False)
    df['adjust1'] = df['adjust1'].apply(lambda x: str(x) if int(x)<1 else '+' + str(x))
    df['adjust2'] = df['adjust2'].apply(lambda x: str(x) if int(x)<1 else '+' + str(x))
    df['Team1Link'] = team_link(df.Team1)
    df['Team2Link'] = team_link(df.Team2)

    # Make it so that recent results show up before earlier ones
    df = df.sort_values(by=['Date','Seq'], ascending=[False,False])
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

def generate_from_df(df, template_file, **kwargs):
    data = []
    for index, row in df.iterrows():
        data = data + [row.to_dict()]

    return(generate_page(data, template_file, **kwargs))

def generate_page(content, template_file, **kwargs):
    """Generate site in local directory"""

    template_loader = jinja2.FileSystemLoader(searchpath="./templates/")
    template_env = jinja2.Environment(loader=template_loader)
    template = template_env.get_template(template_file)

    now = datetime.now()
    now = now.astimezone(pytz.timezone('US/Eastern'))
    now = now.strftime("%-I:%M %p on %h %-d, %Y %Z")

    return(template.render(data=content, timestamp=now, **kwargs))

def generate_teams(team15s, team7s, results15s, results7s):
    teams = pd.concat([team15s, team7s]).drop_duplicates()

    for index, row in teams.iterrows():
        
        games15s = results15s[(results15s.Team1==row.Team) | (results15s.Team2==row.Team)].copy()
        body15s = generate_from_df(games15s,
                                   "_results_table.html",
                                   title=f'{row.Team} 15s Results',
                                   id='results15s',
                                   active='show active')

        games7s = results7s[(results7s.Team1==row.Team) | (results7s.Team2==row.Team)].copy()
        body7s = generate_from_df(games7s,
                                  "_results_table.html",
                                  title=f'{row.Team} 7s Results',
                                  id='results7s')

        content = body15s + body7s
        content = generate_page(content, 'team_template.html', content_title=row.Team)

        page_name = 'teams/' + row.TeamLink + '.html'
        save_page(page_name, content)

def save_page(page_name, content):
    with open(page_name, "w+") as f:
        f.write(content)

class Game:
    def __init__(self, team1, score1, team2, score2, neutral, additional):
        self.team1 = team1
        self.score1 = int(score1)
        self.team2 = team2
        self.score2 = int(score2)
        self.neutral = neutral
        self.additional = additional
        self.home_coef = 0
        self.calc_margin()
        self.calc_winloss()

    def calc_margin(self):
        self.margin = abs(self.score1 - self.score2)

    def calc_winloss(self):
        if self.score1 > self.score2:
            self.win1 = 1
            self.win2 = 0
        elif self.score1 < self.score2:
            self.win1 = 0
            self.win2 = 1
        else:
            self.win1 = .5
            self.win2 = .5

def main(args):
    print(f"### Calculating results: {args.code} ###")

    code = args.code
    if code == '15s' or code == 'both':
        games15s = download_results('15s')
        rankings15s, results15s = load_results(games15s)
        rankings15s = rankings15s.reset_index().copy()

        body_rankings15s = generate_from_df(rankings15s,
                                            '_rankings_table.html',
                                            id='rankings15s',
                                            active='show active')

        body_results15s = generate_from_df(results15s,
                                            '_results_table.html',
                                            id='results15s',
                                            active='show active')
    if code == '7s' or code == 'both':
        games7s = download_results('7s')
        rankings7s, results7s = load_results(games7s)
        rankings7s = rankings7s.reset_index().copy()

        body_rankings7s = generate_from_df(rankings7s,
                                            '_rankings_table.html',
                                            id='rankings7s',
                                            active='show active')

        body_results7s = generate_from_df(results7s,
                                            '_results_table.html',
                                            id='results7s',
                                            active='show active')

    body_results = body_results15s + body_results7s
    content_results = generate_page(body_results,
                                    'results_template.html',
                                    content_title='Division 1 College Rugby Results')
    save_page('results.html', content_results)

    body_rankings = body_rankings15s + body_rankings7s
    content_rankings = generate_page(body_rankings,
                                    'rankings_template.html',
                                    content_title='Division 1 College Rugby Rankings')
    save_page('rankings.html', content_rankings)

    generate_teams(rankings15s, rankings7s, results15s, results7s)

if __name__ == "__main__":
    arguments = parse_arguments()
    main(arguments)