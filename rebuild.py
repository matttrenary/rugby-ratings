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
from pwr import rank_teams
from elo import init_teams, run_elo_loop

def load_results(df):
    df = clean_results(df)
    teams = init_teams(df)
    teams, df, today, last_week_calculated, old_ranks = run_elo_loop(df, teams)
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
