# -*- coding: utf-8 -*-
"""
Created on Thu Nov 17 14:24:45 2022

@author: trenary
"""
import local_utils
from site_generator import SiteGenerator
from data import download_results, clean_results, format_results
from pwr import rank_teams
from elo import init_teams, run_elo_loop


def main():
    site = SiteGenerator()

    # 15s
    df_15s = download_results('15s')
    df_15s = clean_results(df_15s)
    teams_15s = init_teams(df_15s)
    teams_15s, df_15s, today_15s, lwc_15s, old_ranks_15s = run_elo_loop(df_15s, teams_15s)
    rankings15s = rank_teams(teams_15s, df_15s, today_15s, lwc_15s)
    rankings15s['Movement'] = old_ranks_15s - rankings15s['Rank'] if lwc_15s else 0
    results15s = format_results(df_15s)
    rankings15s = rankings15s.reset_index().copy()

    body_rankings15s = site.generate_from_df(rankings15s,
                                             '_rankings_table.html',
                                             id='rankings15s',
                                             active='show active')

    # 7s
    df_7s = download_results('7s')
    df_7s = clean_results(df_7s)
    teams_7s = init_teams(df_7s)
    teams_7s, df_7s, today_7s, lwc_7s, old_ranks_7s = run_elo_loop(df_7s, teams_7s)
    rankings7s = rank_teams(teams_7s, df_7s, today_7s, lwc_7s)
    rankings7s['Movement'] = old_ranks_7s - rankings7s['Rank'] if lwc_7s else 0
    results7s = format_results(df_7s)
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
