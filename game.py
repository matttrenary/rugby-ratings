import pandas as pd
import numpy as np


class Game:
    def __init__(self, team1, score1, team2, score2, neutral, additional):
        self.team1 = team1
        self.score1 = score1
        self.team2 = team2
        self.score2 = score2
        self.neutral = neutral
        self.additional = additional
        self.calc_margin()
        self.calc_winloss()

    def calc_margin(self):
        if pd.isna(self.score1) or pd.isna(self.score2):
            self.margin = np.nan
        else:
            self.margin = abs(self.score1 - self.score2)

    def calc_winloss(self):
        try:
            if self.score1 > self.score2:
                self.win1 = 1
                self.win2 = 0
            elif self.score1 < self.score2:
                self.win1 = 0
                self.win2 = 1
            else:
                self.win1 = .5
                self.win2 = .5
        except:
            self.win1 = np.nan
            self.win2 = np.nan

    def set_elo(self, teams):
        self.elo1 = teams.loc[self.team1, 'Elo']
        self.elo2 = teams.loc[self.team2, 'Elo']

    def update_results(self, df, index):
        df.loc[index, 'elo1'] = self.elo1
        df.loc[index, 'elo2'] = self.elo2
        df.loc[index, 'rn1'] = self.rn1
        df.loc[index, 'rn2'] = self.rn2
        df.loc[index, 'adjust1'] = self.adjust1
        df.loc[index, 'adjust2'] = self.adjust2

    def update_results_nan(self, df, index):
        df.loc[index, 'elo1'] = self.elo1
        df.loc[index, 'elo2'] = self.elo2
        df.loc[index, 'rn1'] = np.nan
        df.loc[index, 'rn2'] = np.nan
        df.loc[index, 'adjust1'] = np.nan
        df.loc[index, 'adjust2'] = np.nan
