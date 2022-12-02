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

def generate_site(code):
    """Generate site in local directory"""
    print("Process data and build site")

    template_loader = jinja2.FileSystemLoader(searchpath="./")
    template_env = jinja2.Environment(loader=template_loader)
    template = template_env.get_template("template.html")

    fname = 'Ratings' + code + '.csv'
    with open(fname) as csv_file:
        csv_reader = csv.DictReader(csv_file)
        data = [row for row in csv_reader]

    output = template.render(data=data)

    page = code + '.html'
    with open(page, "w") as f:
        f.write(output)


def deploy_site(page):
    """Deploy site S3 bucket"""
    print("Upload data to S3")
    session = boto3.Session(profile_name=AWS_PROFILE)
    s3 = session.resource("s3")
    page = page + '.html'
    s3.Bucket(BUCKET).upload_file(
        Filename=page, Key=page, ExtraArgs={"ContentType": "text/html"}
    )

def main(args):
    print(f"### Calculating results: {args.code} ###")

    code = args.code
    if code == '15s' or code == 'both':
        generate_site('15s')
        deploy_site('15s')
    if code == '7s' or code == 'both':
        generate_site('7s')
        deploy_site('7s')
    pass

if __name__ == "__main__":
    arguments = parse_arguments()
    main(arguments)
