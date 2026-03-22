# -*- coding: utf-8 -*-
"""
Created on Thu Nov 17 14:24:45 2022

@author: trenary
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pytz
import local_utils
from game import Game
from site_generator import SiteGenerator
from data import download_results, clean_results, format_results, format_adjustment, team_link
from pwr import qualify_teams, rank_teams, filter_games, calculate_pairwise, pairwise_wins, pairwise_tiebreakers

def load_results(df):
    df = clean_results(df)
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
