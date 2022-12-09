import argparse
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

    template_loader = jinja2.FileSystemLoader(searchpath="./")
    template_env = jinja2.Environment(loader=template_loader)
    template = template_env.get_template(template_file)

    return(template.render(data=content, **kwargs))

def generate_teams():
    team15s = pd.read_csv('Ratings15s.csv', header = 0)
    team7s = pd.read_csv('Ratings7s.csv', header = 0)
    teams = pd.concat([team15s, team7s]).drop_duplicates()

    df7s = pd.read_csv('Results7s.csv', header = 0)
    df15s = pd.read_csv('Results15s.csv', header = 0)

    for index, row in teams.iterrows():
        games15s = df15s[(df15s.Team1==row.Team) | (df15s.Team2==row.Team)].copy()
        body15s = generate_from_df(games15s, "_results_table.html", title='15s Results')

        games7s = df7s[(df7s.Team1==row.Team) | (df7s.Team2==row.Team)].copy()
        body7s = generate_from_df(games7s, "_results_table.html", title='7s Results')

        content = body15s + body7s
        content = generate_page(content, 'base_template.html')

        page_name = 'teams/' + row.TeamLink + '.html'
        save_page(page_name, content)

def save_page(page_name, content):
    with open(page_name, "w+") as f:
        f.write(content)

def main(args):
    print(f"### Building pages: {args.code} ###")

    code = args.code
    if code == '15s' or code == 'both':
        body = generate_from_csv('Ratings15s.csv', '_ratings_table.html')
        content = generate_page(body, 'base_template.html')
        save_page('Ratings15s.html', content)

        body = generate_from_csv('Results15s.csv', '_results_table.html')
        content = generate_page(body, 'base_template.html')
        save_page('Results15s.html', content)

    if code == '7s' or code == 'both':
        body = generate_from_csv('Ratings7s.csv', '_ratings_table.html')
        content = generate_page(body, 'base_template.html')
        save_page('Ratings7s.html', content)

        body = generate_from_csv('Results7s.csv', '_results_table.html')
        content = generate_page(body, 'base_template.html')
        save_page('Results7s.html', content)

    generate_teams()

if __name__ == "__main__":
    arguments = parse_arguments()
    main(arguments)
