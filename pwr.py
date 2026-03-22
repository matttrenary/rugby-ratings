import pandas as pd
from datetime import datetime, timedelta
import pytz


def filter_games(df, start, end, upper=None):
    mask = (df['Date'] >= start) & (df['Date'] < end) & (df.Score1 >= 0) & (df.Score2 >= 0)
    if upper is not None:
        mask &= df['Date'] <= upper
    return df.loc[mask]


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


def pairwise_wins(team, opponent, opponentsMatrix, teams):
    """Return True if team wins the 3-criteria pairwise comparison against opponent."""
    completeTeams = list(teams.index.values)

    # Criteria 1: Head to Head
    wlt = opponentsMatrix[team][opponent]
    if wlt[0] > wlt[1]:
        return True
    elif wlt[0] < wlt[1]:
        return False

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
        return True
    elif teamWinPct < oppoWinPct:
        return False

    # Criteria 3: ELO
    return teams.loc[team, 'Elo'] > teams.loc[opponent, 'Elo']


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
            if pairwise_wins(team, opponent, opponentsMatrix, allTeams):
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
                if pairwise_wins(team, opponent, opponentsMatrix, teams):
                    teams.loc[team, 'TiebreakPairwise'] += 1
        # Reset variables in order to continue iterating
        i = j + 1
        currPWR = teams['Pairwise'].iloc[i]
    return teams


def rank_teams(teams, df, today, last_week_calculated):
    # Modify df to limit rankings to this school year
    now = datetime.now()
    now = now.astimezone(pytz.timezone('US/Eastern'))
    if today < '07-01':
        # backYear and backCutoff assist with disqualifying idle teams
        backYear = int(now.strftime("%Y")) - 2
        lastYear = int(now.strftime("%Y")) - 1
        backCutoff = str(backYear) + "-07-01"
        lastCutoff = str(lastYear) + "-07-01"
        nextCutoff = now.strftime("%Y-07-01")
    else:
        # backYear and backCutoff assist with disqualifying idle teams
        backYear = int(now.strftime("%Y")) - 1
        backCutoff = str(backYear) + "-07-01"
        lastCutoff = now.strftime("%Y-07-01")
        nextYear = int(now.strftime("%Y")) + 1
        nextCutoff = str(nextYear) + "-07-01"

    # Ensure recent games aren't included if last_week_calculated = False
    upper = (now - timedelta(days=7)).strftime("%Y-%m-%d") if not last_week_calculated else None
    pairwise_games = filter_games(df, lastCutoff, nextCutoff, upper)
    active_games = filter_games(df, backCutoff, nextCutoff, upper)

    # Disqualify idle teams
    for team in list(teams.index):
        if team not in list(active_games['Team1']) and team not in list(active_games['Team2']):
            teams.loc[team, 'Eligible'] = False

    teams, opponentsMatrix = calculate_pairwise(teams[teams['Eligible']], teams, pairwise_games)

    teams = teams.sort_values(by=['Pairwise', 'Eligible', 'Elo'], ascending=False).copy()
    # Catch Pairwise tiebreakers
    teams = pairwise_tiebreakers(teams, opponentsMatrix)
    teams = teams.sort_values(by=['Pairwise', 'Eligible', 'TiebreakPairwise', 'Elo'], ascending=False).copy()

    teams['Elo'] = teams['Elo'].round(0).astype(int)
    teams['Rank'] = range(1, len(teams) + 1)
    return teams
