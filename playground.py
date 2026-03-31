"""
Playground CLI for experimenting with the RugbyHawk pipeline.

Commands (each runs from that stage through to HTML generation):
  load   Download fresh data from Google Sheets, then run full pipeline
  rank   Run full pipeline from local CSVs (15s.csv / 7s.csv)
  site   Re-render HTML from saved state only (no recomputation)
  eval   Evaluate Elo predictive accuracy (Brier score, accuracy, calibration)

Examples:
  python playground.py rank
  python playground.py rank --date 2025-11-15
  python playground.py rank --k 35 --home 50
  python playground.py rank --games-min 4 --conn-min 2
  python playground.py load
  python playground.py site
  python playground.py eval
  python playground.py eval --k 30 --home 60
  python playground.py eval --skip-burnin
  python playground.py eval --eval-after 2025-09-01
  python playground.py eval --k 30 --eval-after 2025-09-01
"""
import sys
import argparse
import numpy as np
import pandas as pd
import pytz
import local_utils
from datetime import datetime, timedelta
from site_generator import SiteGenerator
from data import download_results, clean_results, format_results
from pwr import qualify_teams, rank_teams
from elo import init_teams, run_elo_loop, calculate_elo, INELIGIBLE_ELO
from game import Game
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
# Elo evaluation
# ---------------------------------------------------------------------------

def _eval_elo(df, teams):
    """Replay the Elo loop, recording pre-game win probability vs actual outcome.

    Returns a DataFrame with one row per completed game and columns:
      date       - game date
      p          - predicted win probability for team1 (pre-game)
      outcome    - actual result for team1 (1 / 0 / 0.5)
      home       - True if team1 was the home side
      elo_diff   - team1 Elo minus team2 Elo (pre-game, ignoring home coef)
      adjustment - magnitude of Elo adjustment (|adjust1|); tracks rating volatility

    Games with no score (NaN margin) are excluded.
    """
    records = []
    for index, row in df.iterrows():
        game = Game(row.Team1, row.Score1, row.Team2, row.Score2, row.Neutral, row.Additional)
        game.set_elo(teams)

        if pd.isna(game.margin):
            game.update_results_nan(df, index)
            continue

        home_coef = elo_module.HOME_ADVANTAGE if game.neutral != 'Yes' else 0
        rdiff = game.elo2 - (game.elo1 + home_coef)
        p = 1 / (10 ** (rdiff / 400) + 1)

        calculate_elo(game, teams)
        game.update_results(df, index)

        records.append({
            'date':       row.Date,
            'p':          p,
            'outcome':    game.win1,
            'home':       game.neutral != 'Yes',
            'elo_diff':   game.elo1 - game.elo2,
            'adjustment': abs(game.adjust1),
        })

    return pd.DataFrame(records)


def _detect_burnin(ev, window=20, threshold=0.10):
    """Return the positional index of the first game after burn-in ends.

    Tracks the rolling mean of Elo adjustment magnitude. Early games have
    large adjustments as ratings correct from 1500; once the rolling mean
    settles within `threshold` (e.g. 10%) of its long-run tail level, the
    cold-start effect is considered over.

    Returns 0 if there is not enough data to detect anything meaningful.
    """
    if len(ev) < window * 2:
        return 0

    rolling = ev['adjustment'].rolling(window, min_periods=window).mean()
    long_run = rolling.dropna().iloc[-window:].mean()

    for i, val in enumerate(rolling):
        if pd.notna(val) and val <= long_run * (1 + threshold):
            return i

    return len(ev)


def _print_eval(code, ev, n_excluded=0):
    """Print Brier score, accuracy, log loss, and a calibration table."""
    n_total = len(ev)
    if n_total == 0:
        print(f'[{code}] No games to evaluate after exclusions.')
        return

    brier     = ((ev['p'] - ev['outcome']) ** 2).mean()
    p_clipped = ev['p'].clip(1e-7, 1 - 1e-7)
    log_loss  = -(ev['outcome'] * np.log(p_clipped) +
                  (1 - ev['outcome']) * np.log(1 - p_clipped)).mean()

    decided = ev[ev['outcome'] != 0.5]
    acc = (decided['p'].round() == decided['outcome']).mean() if len(decided) else float('nan')

    excluded_note = f'  ({n_excluded} excluded)' if n_excluded else ''
    print(f'\n[{code}] Evaluated {n_total} completed games ({len(decided)} decided){excluded_note}')
    print(f'  Brier score  : {brier:.4f}  (random baseline: 0.2500)')
    print(f'  Accuracy     : {acc:.1%}')
    print(f'  Log loss     : {log_loss:.4f}')

    # Calibration: bucket predictions into 10-pp bins from 50% up.
    # Predictions below 50% are flipped so every row reads as
    # "favourite win probability" for a symmetric, interpretable view.
    fav_p       = ev['p'].where(ev['p'] >= 0.5, 1 - ev['p'])
    fav_outcome = ev['outcome'].where(ev['p'] >= 0.5, 1 - ev['outcome'])

    bins   = [0.50, 0.60, 0.70, 0.80, 0.90, 1.01]
    labels = ['50-60%', '60-70%', '70-80%', '80-90%', '90-100%']
    bucket = pd.cut(fav_p, bins=bins, labels=labels, right=False)

    cal     = pd.DataFrame({'bucket': bucket, 'p': fav_p, 'outcome': fav_outcome})
    grouped = cal.groupby('bucket', observed=True).agg(
        predicted=('p', 'mean'),
        actual=('outcome', 'mean'),
        n=('p', 'count'),
    )

    print(f'\n  Calibration (favourite win probability):')
    print(f'  {"Bin":<10}  {"Predicted":>10}  {"Actual":>8}  {"N":>5}')
    print(f'  {"-"*10}  {"-"*10}  {"-"*8}  {"-"*5}')
    for label, row in grouped.iterrows():
        if row['n'] > 0:
            print(f'  {label:<10}  {row["predicted"]:>9.1%}  {row["actual"]:>7.1%}  {int(row["n"]):>5}')
    print()


def cmd_eval(args):
    """Evaluate Elo predictive accuracy.

    All games are always fed through the Elo loop so that ratings warm up
    correctly from the 1500 starting point.  Exclusion flags only affect
    which games count toward the reported metrics:

      --eval-after DATE   Only score games on/after DATE.  Use this to hold
                          out a season you did not tune K/home on, giving a
                          clean train/test split.  Tune on an earlier window,
                          then run --eval-after on a later one you never tuned.

      --skip-burnin       Auto-detect the cold-start period (games where Elo
                          adjustments are still large) and exclude it.  The
                          detection window/threshold can be tuned with
                          --burnin-window and --burnin-threshold.
    """
    _override_constants(args)
    for code in CODES:
        print(f'[{code}] Loading {code}.csv...')
        df = pd.read_csv(f'{code}.csv')
        df = clean_results(df)

        if args.date:
            df = df[df['Date'].dt.strftime("%Y-%m-%d") <= args.date].copy()
            print(f'[{code}] Cutoff: {args.date} ({len(df)} games)')

        teams = _prepare_teams(df, init_teams(df))
        ev    = _eval_elo(df, teams)      # always runs full history

        # --- apply exclusions (metrics only; ratings were already computed) ---
        n_before = len(ev)

        if args.skip_burnin:
            burnin_idx = _detect_burnin(ev, args.burnin_window, args.burnin_threshold)
            if burnin_idx > 0:
                print(f'[{code}] Burn-in detected: skipping first {burnin_idx} games '
                      f'(game {burnin_idx + 1} onward evaluated)')
            ev = ev.iloc[burnin_idx:].reset_index(drop=True)

        if args.eval_after:
            cutoff = pd.Timestamp(args.eval_after)
            ev = ev[pd.to_datetime(ev['date']) >= cutoff].reset_index(drop=True)

        n_excluded = n_before - len(ev)
        _print_eval(code, ev, n_excluded=n_excluded)

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

    p_eval = sub.add_parser('eval', help='Evaluate Elo predictive accuracy from local CSVs')
    p_eval.add_argument('--date', metavar='YYYY-MM-DD',
                        help='Only include games on or before this date (hard cutoff on input)')
    p_eval.add_argument('--k', type=int, metavar='N',
                        help=f'ELO K-factor (default: {elo_module.ELO_K})')
    p_eval.add_argument('--home', type=int, metavar='N',
                        help=f'Home advantage in rating points (default: {elo_module.HOME_ADVANTAGE})')
    p_eval.add_argument('--eval-after', metavar='YYYY-MM-DD', dest='eval_after',
                        help='Only score games on/after this date (ratings still warm up from game 1). '
                             'Use as a test-set boundary: tune --k/--home on an earlier window, '
                             'then evaluate here on a period you never tuned on.')
    p_eval.add_argument('--skip-burnin', action='store_true', dest='skip_burnin',
                        help='Auto-detect cold-start period and exclude those games from metrics')
    p_eval.add_argument('--burnin-window', type=int, default=20, dest='burnin_window', metavar='N',
                        help='Rolling window size for burn-in detection (default: 20)')
    p_eval.add_argument('--burnin-threshold', type=float, default=0.10, dest='burnin_threshold',
                        metavar='F',
                        help='Fraction above long-run mean that counts as still burning in '
                             '(default: 0.10)')
    p_eval.add_argument('--games-min', type=int, dest='games_min', metavar='N',
                        help=argparse.SUPPRESS)
    p_eval.add_argument('--conn-min', type=int, dest='conn_min', metavar='N',
                        help=argparse.SUPPRESS)
    p_eval.set_defaults(func=cmd_eval)

    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
