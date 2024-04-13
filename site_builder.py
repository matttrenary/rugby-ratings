import argparse
from datetime import datetime
import time
import csv
import pandas as pd
import jinja2

def parse_arguments():
    """Parse arguments when executed from CLI"""
    parser = argparse.ArgumentParser(
        prog="build-site",
        description="CLI tool to build site pages and publish",
    )
    parser.add_argument(
        "--code",
        choices=["15s", "7s", "both"],
        default="both",
        help="15s or 7s results",
    )
    args = parser.parse_args()
    return args

def generate_from_csv(data_file, template_file, **kwargs):
    with open(data_file) as csv_file:
        csv_reader = csv.DictReader(csv_file)
        data = [row for row in csv_reader]

    return(generate_page(data, template_file, **kwargs))

def generate_from_df(df, template_file, **kwargs):
    data = []
    for index, row in df.iterrows():
        data = data + [row.to_dict()]

    return(generate_page(data, template_file, **kwargs))

def generate_page(content, template_file, **kwargs):
    """Generate site in local directory"""

    template_loader = jinja2.FileSystemLoader(searchpath="./templates/")
    template_env = jinja2.Environment(loader=template_loader)
    template = template_env.get_template(template_file)

    now = datetime.now()
    if (time.localtime().tm_isdst == 0):
        # Append non-daylight savings timezone to timestamp
        now = now.strftime("%-I:%M %p on %h %-d, %Y ") + time.tzname[0]
    else:
        # Append daylight savings timezone to timestamp
        now = now.strftime("%-I:%M %p on %h %-d, %Y ") + time.tzname[time.daylight]

    return(template.render(data=content, timestamp=now, **kwargs))

def generate_teams():
    team15s = pd.read_csv('Ratings15s.csv', header = 0)
    team7s = pd.read_csv('Ratings7s.csv', header = 0)
    teams = pd.concat([team15s, team7s]).drop_duplicates()

    df7s = pd.read_csv('Results7s.csv', header = 0).fillna('')
    df15s = pd.read_csv('Results15s.csv', header = 0).fillna('')

    # Determine current season (for referencing conf/div/gov table)
    now = datetime.now()
    today = now.strftime("%m-%d")
    if today < '07-01':
        laterYear = int(now.strftime("%Y"))
        earlyYear = laterYear - 1
    else:
        earlyYear = int(now.strftime("%Y"))
        laterYear = earlyYear + 1
    seasonString = str(earlyYear) + "-" + str(laterYear)
        
    fname = "Org.csv"
    org = pd.read_csv(fname, names=('Season', 'Team', 'Conf', 'Div', 'Gov'))
    org['GovDiv'] = org['Gov'] + " " + org['Div']
    org = org.loc[org['Season'] == seasonString]
    teams = pd.merge(teams, org, how='left', on='Team')
    teams['ConfLink'] = team_link(teams['Conf'])
    teams['GovDivLink'] = team_link(teams['GovDiv'])

    for index, row in teams.iterrows():
        games15s = df15s[(df15s.Team1==row.Team) | (df15s.Team2==row.Team)].copy()
        games15s['adjust1'] = games15s['adjust1'].apply(lambda x: str(x) if int(x)<1 else '+' + str(x))
        games15s['adjust2'] = games15s['adjust2'].apply(lambda x: str(x) if int(x)<1 else '+' + str(x))
        body15s = generate_from_df(games15s,
                                   "_results_table.html",
                                   title=f'{row.Team} 15s Results',
                                   id='results15s',
                                   active='show active')

        games7s = df7s[(df7s.Team1==row.Team) | (df7s.Team2==row.Team)].copy()
        games7s['adjust1'] = games7s['adjust1'].apply(lambda x: str(x) if int(x)<1 else '+' + str(x))
        games7s['adjust2'] = games7s['adjust2'].apply(lambda x: str(x) if int(x)<1 else '+' + str(x))
        body7s = generate_from_df(games7s,
                                  "_results_table.html",
                                  title=f'{row.Team} 7s Results',
                                  id='results7s')

        content = body15s + body7s

        # Determine team's current conf/div/gov
        if (pd.isna(row.Gov)):
            subtitle = "Lower-Division Program"
        else:
            subtitle = "<a href=/divs/" + row.GovDivLink + ".html>" + row.GovDiv + "</a>" + " - " + \
                       "<a href=/confs/" + row.ConfLink + ".html>" + row.Conf + "</a>"
        content = generate_page(content, 'team_template.html',
                                content_title=row.Team,
                                content_subtitle=subtitle)

        page_name = 'teams/' + row.TeamLink + '.html'
        save_page(page_name, content)

    # Create broader conf/div pages
    confs = teams['Conf'].dropna().unique()
    confLinks = teams['ConfLink'].dropna().unique()
    divs = teams['GovDiv'].dropna().unique()
    divLinks = teams['GovDivLink'].dropna().unique()
    team15s = pd.merge(team15s, org, how='left', on='Team')
    team7s = pd.merge(team7s, org, how='left', on='Team')

    for i, conf in enumerate(confs):
        members15s = team15s[team15s.Conf == conf].copy()
        body15s = generate_from_df(members15s,
                                   "_rankings_table.html",
                                   title=f'{conf} 15s Rankings',
                                   id='rankings15s',
                                   active='show active') 
        members7s = team7s[team7s.Conf == conf].copy()
        body7s = generate_from_df(members7s,
                                  "_rankings_table.html",
                                  title=f'{conf} 7s Rankings',
                                  id='rankings7s')
        content = body15s + body7s

        content = generate_page(content, 'rankings_template.html',
                                content_title=conf)
        page_name = 'confs/' + confLinks[i] + '.html'
        save_page(page_name, content)
    for i, div in enumerate(divs):
        members15s = team15s[team15s.GovDiv == div].copy()
        body15s = generate_from_df(members15s,
                                   "_rankings_table.html",
                                   title=f'{div} 15s Rankings',
                                   id='rankings15s',
                                   active='show active') 
        members7s = team7s[team7s.GovDiv == div].copy()
        body7s = generate_from_df(members7s,
                                  "_rankings_table.html",
                                  title=f'{div} 7s Rankings',
                                  id='rankings7s')
        content = body15s + body7s

        content = generate_page(content, 'rankings_template.html',
                                content_title=div)
        page_name = 'divs/' + divLinks[i] + '.html'
        save_page(page_name, content)

def save_page(page_name, content):
    with open(page_name, "w+") as f:
        f.write(content)

def team_link(series):
    series = series.str.lower()
    series = series.str.replace(' ','', regex=False)
    series = series.str.replace("'",'', regex=False)
    series = series.str.replace('.','', regex=False)
    series = series.str.replace('&','', regex=False)
    series = series.str.replace('(','', regex=False)
    series = series.str.replace(')','', regex=False)
    return series

def main(args):
    print(f"### Building pages: {args.code} ###")

    code = args.code
    if code == '15s' or code == 'both':
        body_rankings15s = generate_from_csv('Ratings15s.csv',
                                            '_rankings_table.html',
                                            id='rankings15s',
                                            active='show active')

        body_results15s = generate_from_csv('Results15s.csv',
                                            '_results_table.html',
                                            id='results15s',
                                            active='show active')

    if code == '7s' or code == 'both':
        body_rankings7s = generate_from_csv('Ratings7s.csv',
                                           '_rankings_table.html',
                                           id='rankings7s')

        body_results7s = generate_from_csv('Results7s.csv',
                                           '_results_table.html',
                                           id='results7s')

    body_results = body_results15s + body_results7s
    content_results = generate_page(body_results,
                                    'results_template.html',
                                    content_title='Division 1 College Rugby Results')
    save_page('results.html', content_results)

    body_rankings = body_rankings15s + body_rankings7s
    content_rankings = generate_page(body_rankings,
                                    'rankings_template.html',
                                    content_title='Division 1 College Rugby Rankings')
    save_page('rankings.html', content_rankings)

    generate_teams()

if __name__ == "__main__":
    arguments = parse_arguments()
    main(arguments)
