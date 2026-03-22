import pandas as pd
from datetime import datetime, timedelta
import pytz
from game import Game
from data import team_link
from pwr import qualify_teams, rank_teams


def init_teams(df):
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
    return teams


def run_elo_loop(df, teams):
    now = datetime.now().astimezone(pytz.timezone('US/Eastern'))
    today = now.strftime("%m-%d")
    last_week = (now - timedelta(days=7)).strftime("%Y-%m-%d")

    last_week_calculated = False
    old_ranks = None
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

    return teams, df, today, last_week_calculated, old_ranks
