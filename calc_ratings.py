# -*- coding: utf-8 -*-
"""
Created on Thu Nov 17 14:24:45 2022

@author: trenary
"""
import argparse
import pandas as pd
import numpy as np

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

def load_results(code):
    fname = code + '.csv'
    df = pd.read_csv(fname, parse_dates=['Date'])

    # Only games with scores for both teams
    df = df[~(df.Score1.isnull()) & ~(df.Score2.isnull())].copy()

    ### Prepare teams ELO list
    teams = pd.concat([df.Team1, df.Team2]).rename('Team').to_frame()
    teams = teams.drop_duplicates()
    teams['Elo'] = 1500
    teams['TeamLink'] = team_link(teams.Team)
    teams = teams.set_index('Team')

    teams = qualify_teams(teams, df)

    for index, row in df.iterrows():
        game = Game(row.Team1, row.Score1, row.Team2, row.Score2, row.Neutral, row.Additional)
        calculate_elo(game, teams)
        update_results(df, index, game)

    teams = format_ratings(teams)
    df = format_results(df)

    return teams, df

def qualify_teams(teams, df):
    # Tally each team's number of games
    numGames = dict.fromkeys(list(teams.index.values), 0)
    for index, row in df.iterrows():
        numGames[row.Team1] = numGames[row.Team1] + 1
        numGames[row.Team2] = numGames[row.Team2] + 1
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
    while (len(newEligible) > 0):
        eligible = eligible + newEligible
        newEligible = []
        possible = dict.fromkeys(possible, 0)
        for index, row in df.iterrows():
            if (row.Team1 in eligible) and (row.Team2 in possible):
                possible[row.Team2] = possible[row.Team2] + 1
            elif (row.Team2 in eligible) and (row.Team1 in possible):
                possible[row.Team1] = possible[row.Team1] + 1
        possible2 = possible.copy()
        for key, value in possible.items():
            # connectivity coefficient C=3
            if (value >= 3):
                newEligible.append(key)
                possible2.pop(key)
        possible = possible2
    print("Eligible Teams: ", len(eligible))
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
    df['Rank'] = range(1, len(df) + 1)
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
    df.Date = df.Date.dt.strftime('%b %#d, %Y')

    return df

def team_link(series):
    series = series.str.lower()
    series = series.str.replace(' ','', regex=False)
    series = series.str.replace("'",'', regex=False)
    series = series.str.replace('&','', regex=False)
    series = series.str.replace('(','', regex=False)
    series = series.str.replace(')','', regex=False)
    return series

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
        calcs = load_results('15s')
        calcs[0].to_csv('Ratings15s.csv')
        # Somehow the Seq column was causing a Runtime Warning; worth investigating later
        calcs[1].loc[:, calcs[1].columns != 'Seq'].to_csv('Results15s.csv')
    if code == '7s' or code == 'both':
        calcs = load_results('7s')
        calcs[0].to_csv('Ratings7s.csv')
        calcs[1].to_csv('Results7s.csv')

if __name__ == "__main__":
    arguments = parse_arguments()
    main(arguments)
