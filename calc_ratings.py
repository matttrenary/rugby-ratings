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
    df = pd.read_csv(fname)

    # Only games with scores for both teams
    df = df[~(df.Score1.isnull()) & ~(df.Score2.isnull())].copy()

    ### Prepare teams ELO list
    teams = pd.concat([df.Team1, df.Team2]).rename('Team').to_frame()
    teams = teams.drop_duplicates()
    teams['Elo'] = 1500
    teams['TeamLink'] = team_link(teams.Team)
    teams = teams.set_index('Team')

    for index, row in df.iterrows():
        game = Game(row.Team1, row.Score1, row.Team2, row.Score2, row.Neutral, row.Additional)
        calculate_elo(game, teams)
        update_results(df, index, game)

    teams = format_ratings(teams)
    df = format_results(df)

    return teams, df

def calculate_elo(game, teams):
    # Elo coefficients
    k = 40
    margin_coef = np.log(game.margin + 1)
    if game.neutral != 'Yes':
        game.home_coef = 75

    print(f"{game.team1} vs {game.team2}")
    game.elo1 = teams.loc[game.team1, 'Elo']
    game.elo2 = teams.loc[game.team2, 'Elo']
    print(f"{game.elo1} vs {game.elo2}")
    rdiff1 = game.elo2 - (game.elo1 + game.home_coef)
    rdiff2 = (game.elo1 + game.home_coef) - game.elo2
    print(f"Ratings diff of {rdiff1}")
    we1 = 1/(10**(rdiff1/400)+1)
    we2 = 1/(10**(rdiff2/400)+1)
    print(f"win1 {game.win1}")
    print(f"win2 {game.win2}")
    print(f"we1 {we1}")
    print(f"we2 {we2}")
    game.rn1 = game.elo1 + k*margin_coef*(game.win1-we1)
    game.rn2 = game.elo2 + k*margin_coef*(game.win2-we2)

    print(f"Assigning {game.team1} to {game.rn1}")
    print(f"Assigning {game.team2} to {game.rn2}")
    teams.loc[game.team1, 'Elo'] = game.rn1
    teams.loc[game.team2, 'Elo'] = game.rn2

def update_results(df, index, game):
        df.loc[index, 'elo1'] = game.elo1
        df.loc[index, 'elo2'] = game.elo2
        df.loc[index, 'rn1'] = game.rn1
        df.loc[index, 'rn2'] = game.rn2

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
    df['adjust1'] = df.rn1-df.elo1
    df['adjust1'] = df['adjust1'].apply(lambda x: str(x) if x<1 else '+' + str(x))
    df['adjust2'] = df.rn2-df.elo2
    df['adjust2'] = df['adjust2'].apply(lambda x: str(x) if x<1 else '+' + str(x))
    df['Team1Link'] = team_link(df.Team1)
    df['Team2Link'] = team_link(df.Team2)

    return df

def team_link(series):
    series = series.str.lower().str.replace(' ','').str.replace("'",'')
    series = series.str.replace('&','').str.replace('(','').str.replace(')','')
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
        calcs[1].to_csv('Results15s.csv')
    if code == '7s' or code == 'both':
        calcs = load_results('7s')
        calcs[0].to_csv('Ratings7s.csv')
        calcs[1].to_csv('Results7s.csv')

if __name__ == "__main__":
    arguments = parse_arguments()
    main(arguments)
