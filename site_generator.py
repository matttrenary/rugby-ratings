import sys
import jinja2
import pandas as pd
from datetime import datetime
import pytz
import local_utils


class SiteGenerator:
    def __init__(self):
        template_loader = jinja2.FileSystemLoader(searchpath="./templates/")
        self.env = jinja2.Environment(loader=template_loader)

    def _format_timestamp(self):
        now = datetime.now().astimezone(pytz.timezone('US/Eastern'))
        if sys.platform.startswith('win'):
            return now.strftime("%#I:%M %p on %h %#d, %Y %Z")
        return now.strftime("%-I:%M %p on %h %-d, %Y %Z")

    def generate_page(self, content, template_file, **kwargs):
        """Generate site in local directory"""
        template = self.env.get_template(template_file)
        return template.render(data=content, timestamp=self._format_timestamp(), **kwargs)

    def generate_from_df(self, df, template_file, id, **kwargs):
        data = df.to_dict('records')

        if id[-2:] == '7s':
            linkExt = '#7s'
        else:
            linkExt = ''

        return self.generate_page(data, template_file, id=id, linkExt=linkExt, **kwargs)

    def generate_teams(self, team15s, team7s, results15s, results7s):
        teams = pd.concat([team15s, team7s]).drop_duplicates()

        for index, row in teams.iterrows():

            games15s = results15s[(results15s.Team1==row.Team) | (results15s.Team2==row.Team)].copy()
            body15s = self.generate_from_df(games15s,
                                            "_results_table.html",
                                            id='results15s',
                                            title=f'{row.Team} 15s Results',
                                            active='show active')

            games7s = results7s[(results7s.Team1==row.Team) | (results7s.Team2==row.Team)].copy()
            body7s = self.generate_from_df(games7s,
                                           "_results_table.html",
                                           id='results7s',
                                           title=f'{row.Team} 7s Results')

            content = body15s + body7s
            content = self.generate_page(content, 'team_template.html', content_title=row.Team)

            page_name = 'teams/' + row.TeamLink + '.html'
            self.save_page(page_name, content)

    def rebuild_front(self, df_15s, df_7s):
        # Generate table
        body_15s = self.generate_from_df(df_15s,
                                         '_results_table.html',
                                         id='recent_results_15s',
                                         active='show active')
        body_7s = self.generate_from_df(df_7s,
                                        '_results_table.html',
                                        id='recent_results_7s',
                                        active='show active')

        now = f'<p id="results_timestamp" style="text-align: center;">All information as of {self._format_timestamp()}</p>'

        # Replace html on front page
        with open('results.html', 'r+', encoding='utf-8') as front_page:
            new_html = local_utils.replace_element(front_page.read(),
                                                   'div',
                                                   'recent_results_15s',
                                                   body_15s)
            new_html = local_utils.replace_element(new_html,
                                                   'div',
                                                   'recent_results_7s',
                                                   body_7s)
            new_html = local_utils.replace_element(new_html,
                                                   'p',
                                                   'results_timestamp',
                                                   now)
            self.save_page('results.html', new_html)

    def save_page(self, page_name, content):
        with open(page_name, "w+", encoding='utf-8') as f:
            f.write(content)
