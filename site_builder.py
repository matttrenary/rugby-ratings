import argparse
import csv

import boto3
import jinja2

AWS_PROFILE = "matt"
BUCKET = "rugby-ratings"

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

def generate_site(data_file, template_file):
    """Generate site in local directory"""
    print("Process data and build site")

    template_loader = jinja2.FileSystemLoader(searchpath="./")
    template_env = jinja2.Environment(loader=template_loader)
    template = template_env.get_template(template_file)

    with open(data_file) as csv_file:
        csv_reader = csv.DictReader(csv_file)
        data = [row for row in csv_reader]

    output = template.render(data=data)

    page = data_file.replace('.csv','.html')
    with open(page, "w") as f:
        f.write(output)

def deploy_site(page):
    """Deploy site S3 bucket"""
    print("Upload data to S3")
    session = boto3.Session(profile_name=AWS_PROFILE)
    s3 = session.resource("s3")
    s3.Bucket(BUCKET).upload_file(
        Filename=page, Key=page, ExtraArgs={"ContentType": "text/html"}
    )

def main(args):
    print(f"### Calculating results: {args.code} ###")

    code = args.code
    if code == '15s' or code == 'both':
        generate_site('Ratings15s.csv', 'ratings_template.html')
        generate_site('Results15s.csv', 'results_template.html')
        deploy_site('Ratings15s.html')
    if code == '7s' or code == 'both':
        generate_site('Ratings7s.csv', 'ratings_template.html')
        generate_site('Results7s.csv', 'results_template.html')
        deploy_site('Ratings7s.html')
    pass

if __name__ == "__main__":
    arguments = parse_arguments()
    main(arguments)