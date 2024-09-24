# predict_game.py
# Script takes elo ratings as input and outputs home team win probability

from argparse import ArgumentParser as Parser

def parse_args():
    parser = Parser(description='Provide HomeElo, AwayElo, and NeutBool \
                    (default 0)') 
    parser.add_argument('HomeElo', type=int, help='Elo rating for home team')
    parser.add_argument('AwayElo', type=int, help='Elo rating for away team')
    parser.add_argument('NeutBool', nargs='?', default=0,
                        type=lambda x: int(x) if x else 0, choices=[1,0],
                        help='Boolean for neutral site (default is False, \
                        use 1 for True or omit to leave at default)') 
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    homeElo = args.HomeElo
    awayElo = args.AwayElo
    neutral = args.NeutBool
    
    if not neutral:
        home_coef = 75
    else:
        home_coef = 0
    rdiff = awayElo - (homeElo + home_coef)
    we = 1/(10**(rdiff/400)+1)

    print(we)
