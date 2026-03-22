import numpy as np
import pandas as pd
from game import Game
from data import team_link

ELO_K = 40
HOME_ADVANTAGE = 75
INITIAL_ELO = 1500.00
INELIGIBLE_ELO = 1300


def _autocor(game, home_coef):
    if game.win1 == 1:
        return 2.2 / (((game.elo1 + home_coef) - game.elo2) * .001 + 2.2)
    elif game.win2 == 1:
        return 2.2 / ((game.elo2 - (game.elo1 + home_coef)) * .001 + 2.2)
    else:
        return 1


def calculate_elo(game, teams):
    x = 2 if game.margin == 0 else 1
    margin_coef = np.log(game.margin + x)
    home_coef = HOME_ADVANTAGE if game.neutral != 'Yes' else 0
    autocor = _autocor(game, home_coef)

    rdiff = game.elo2 - (game.elo1 + home_coef)
    we = 1 / (10 ** (rdiff / 400) + 1)

    game.adjust1 = ELO_K * margin_coef * autocor * (game.win1 - we)
    game.adjust2 = -1 * game.adjust1
    game.rn1 = game.elo1 + game.adjust1
    game.rn2 = game.elo2 + game.adjust2

    teams.loc[game.team1, 'Elo'] = game.rn1
    teams.loc[game.team2, 'Elo'] = game.rn2


def init_teams(df):
    teams = pd.concat([df.Team1, df.Team2]).rename('Team').to_frame()
    teams = teams.drop_duplicates()
    teams['Elo'] = INITIAL_ELO
    teams['TeamLink'] = team_link(teams.Team)
    teams = teams.set_index('Team')
    # Prepare columns for pairwise calculation
    teams['Pairwise'] = 0
    teams['WLT'] = "0-0-0"

    return teams


def run_elo_loop(df, teams):
    for index, row in df.iterrows():
        game = Game(row.Team1, row.Score1, row.Team2, row.Score2, row.Neutral, row.Additional)
        game.set_elo(teams)

        if not pd.isna(game.margin):
            calculate_elo(game, teams)
            game.update_results(df, index)
        else:
            game.update_results_nan(df, index)

    return teams, df
