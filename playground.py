"""
Playground CLI for experimenting with the RugbyHawk pipeline.

Commands (each runs from that stage through to HTML generation):
  load   Download fresh data from Google Sheets, then run full pipeline
  rank   Run full pipeline from local CSVs (15s.csv / 7s.csv)
  site   Re-render HTML from saved state only (no recomputation)

Examples:
  python playground.py rank
  python playground.py rank --date 2025-11-15
  python playground.py rank --k 35 --home 50
  python playground.py rank --games-min 4 --conn-min 2
  python playground.py load
  python playground.py site
"""
import sys
import argparse
import pandas as pd
import pytz
import local_utils
from datetime import datetime, timedelta
from site_generator import SiteGenerator
from data import download_results, clean_results, format_results
from pwr import qualify_teams, rank_teams
from elo import init_teams, run_elo_loop, INELIGIBLE_ELO
import elo as elo_module
import pwr as pwr_module

CODES = ['15s', '7s']
_STATE_RANKINGS = {c: f'_pg_rankings_{c}.csv' for c in CODES}
_STATE_RESULTS  = {c: f'_pg_results_{c}.csv'  for c in CODES}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _override_constants(args):
    if args.k is not None:
        elo_module.ELO_K = args.k
        print(f'  ELO K-factor       : {args.k}')
    if args.home is not None:
        elo_module.HOME_ADVANTAGE = args.home
        print(f'  Home advantage     : {args.home}')
    if args.games_min is not None:
        pwr_module.GAMES_MIN = args.games_min
        print(f'  Games minimum      : {args.games_min}')
    if args.conn_min is not None:
        pwr_module.CONNECTIVITY_MIN = args.conn_min
        print(f'  Connectivity min   : {args.conn_min}')


def _parse_now(date_str):
    """Return a timezone-aware datetime for the given date string, or now."""
    if date_str:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return pytz.timezone('US/Eastern').localize(dt)
    return datetime.now().astimezone(pytz.timezone('US/Eastern'))


def _prepare_teams(df, teams):
    teams = qualify_teams(teams, df)
    teams.loc[~teams['Eligible'], 'Elo'] = INELIGIBLE_ELO
    return teams


def _get_old_ranks(teams, df, today, last_week, now):
    teams_snap = teams.copy()
    df_before = df[df['Date'].dt.strftime("%Y-%m-%d") <= last_week].copy()
    run_elo_loop(df_before, teams_snap)
    return rank_teams(teams_snap, df, today, False, now=now)['Rank']


# ---------------------------------------------------------------------------
# Pipeline stages
# ---------------------------------------------------------------------------

def _run_pipeline(code, fresh, date):
    """Run the full ELO + ranking pipeline for one code. Returns (rankings, results)."""
    now = _parse_now(date)
    today = now.strftime("%m-%d")
    last_week = (now - timedelta(days=7)).strftime("%Y-%m-%d")

    if fresh:
        print(f'[{code}] Downloading from Google Sheets...')
        df = download_results(code)
    else:
        print(f'[{code}] Loading {code}.csv...')
        df = pd.read_csv(f'{code}.csv')

    df = clean_results(df)

    if date:
        df = df[df['Date'].dt.strftime("%Y-%m-%d") <= date].copy()
        print(f'[{code}] Cutoff: {date} ({len(df)} games)')

    teams = _prepare_teams(df, init_teams(df))
    lwc = df['Date'].dt.strftime("%Y-%m-%d").gt(last_week).any()
    old_ranks = _get_old_ranks(teams, df, today, last_week, now) if lwc else None
    teams, df = run_elo_loop(df, teams)
    rankings = rank_teams(teams, df, today, lwc, now=now)
    rankings['Movement'] = old_ranks - rankings['Rank'] if lwc else 0
    results = format_results(df)
    rankings = rankings.reset_index()

    eligible_count = rankings['Eligible'].sum()
    print(f'[{code}] {eligible_count} eligible teams ranked.')
    return rankings, results


def _generate_site(site, rankings, results, date=None):
    """Render all HTML pages from rankings and results DataFrames."""
    now = _parse_now(date)

    body15s = site.generate_from_df(rankings['15s'], '_rankings_table.html',
                                     id='rankings15s', active='show active')
    body7s  = site.generate_from_df(rankings['7s'],  '_rankings_table.html',
                                     id='rankings7s')
    body    = body15s + body7s
    content = site.generate_page(body, 'rankings_template.html',
                                  content_title='Division 1 College Rugby Rankings')
    site.save_page('index.html', content)
    print('Generated: index.html')

    site.generate_teams(rankings['15s'], rankings['7s'], results['15s'], results['7s'])
    print('Generated: team pages')

    subset_15s = local_utils.load_range(results['15s'], 2, 2, now=now)
    subset_7s  = local_utils.load_range(results['7s'],  2, 2, now=now)
    site.rebuild_front(subset_15s, subset_7s)
    print('Generated: results.html')


def _save_state(rankings, results):
    for code in CODES:
        rankings[code].to_csv(_STATE_RANKINGS[code], index=False)
        results[code].to_csv(_STATE_RESULTS[code],   index=False)
    print('State saved.')


def _load_state():
    rankings = {}
    results  = {}
    for code in CODES:
        rk = _STATE_RANKINGS[code]
        rs = _STATE_RESULTS[code]
        try:
            rankings[code] = pd.read_csv(rk)
            results[code]  = pd.read_csv(rs)
        except FileNotFoundError as e:
            sys.exit(f'State file not found: {e.filename}\n'
                     f'Run `python playground.py rank` first to generate state files.')
    return rankings, results


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def cmd_load(args):
    _override_constants(args)
    site = SiteGenerator()
    rankings, results = {}, {}
    for code in CODES:
        rankings[code], results[code] = _run_pipeline(code, fresh=True, date=args.date)
    _save_state(rankings, results)
    _generate_site(site, rankings, results, date=args.date)
    print('Done.')


def cmd_rank(args):
    _override_constants(args)
    site = SiteGenerator()
    rankings, results = {}, {}
    for code in CODES:
        rankings[code], results[code] = _run_pipeline(code, fresh=False, date=args.date)
    _save_state(rankings, results)
    _generate_site(site, rankings, results, date=args.date)
    print('Done.')


def cmd_site(args):
    print('Loading saved state...')
    rankings, results = _load_state()
    site = SiteGenerator()
    _generate_site(site, rankings, results, date=args.date)
    print('Done.')


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def _add_pipeline_args(parser):
    """Add ELO/PWR override flags shared by load and rank commands."""
    parser.add_argument('--date', metavar='YYYY-MM-DD',
                        help='Only include games on or before this date')
    parser.add_argument('--k', type=int, metavar='N',
                        help=f'ELO K-factor (default: {elo_module.ELO_K})')
    parser.add_argument('--home', type=int, metavar='N',
                        help=f'Home advantage in rating points (default: {elo_module.HOME_ADVANTAGE})')
    parser.add_argument('--games-min', type=int, dest='games_min', metavar='N',
                        help=f'Min games for eligibility (default: {pwr_module.GAMES_MIN})')
    parser.add_argument('--conn-min', type=int, dest='conn_min', metavar='N',
                        help=f'Connectivity minimum (default: {pwr_module.CONNECTIVITY_MIN})')


def main():
    parser = argparse.ArgumentParser(
        prog='playground',
        description='RugbyHawk pipeline playground.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    sub = parser.add_subparsers(dest='command', required=True)

    p_load = sub.add_parser('load', help='Download fresh data, then run full pipeline')
    _add_pipeline_args(p_load)
    p_load.set_defaults(func=cmd_load)

    p_rank = sub.add_parser('rank', help='Run full pipeline from local CSVs')
    _add_pipeline_args(p_rank)
    p_rank.set_defaults(func=cmd_rank)

    p_site = sub.add_parser('site', help='Re-render HTML from saved state (no recomputation)')
    p_site.add_argument('--date', metavar='YYYY-MM-DD',
                        help='Reference date for "recent games" window (defaults to today)')
    p_site.set_defaults(func=cmd_site)

    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
