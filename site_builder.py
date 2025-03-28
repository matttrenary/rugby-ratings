import argparse
import sys
from datetime import datetime
import time
from dateutil.tz import tzlocal
import pytz
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
    # If-Then statement handles OS-level differences in C's strftime() func
    if sys.platform.startswith('win'):
        # Code for Windows OS goes here
        now = now.astimezone(pytz.timezone('US/Eastern'))
        now = now.strftime("%#I:%M %p on %h %#d, %Y %Z")
    else:
        # Code for MacOS (Darwin), as well as other other systems, goes here
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
        content = generate_page(content, 'team_template.html', content_title=row.Team)

        page_name = 'teams/' + row.TeamLink + '.html'
        save_page(page_name, content)

def save_page(page_name, content):
    with open(page_name, "w+") as f:
        f.write(content)

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
