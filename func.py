#!/usr/bin/python

import logging
import json
import requests
import os
import itertools
import dateutil.parser

DEFAULT_TITLE_INDICATOR = '[am]'
DEFAULT_TITLE_PREVENTOR = '[dm]'
DEFAULT_CONTEXT = 'continuous-integration/travis-ci/pr'

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)


def response(status_code, status):
    return {'statusCode': status_code, 'body': status}


def is_allowed_repository(repo):
    allowed = os.environ.get('ALLOWED_REPOS', '').strip()
    if '*' == allowed:
        return True
    return repo.lower() in [r.strip() for r in allowed.lower().split(',')]


def is_allowed_pr_title(title):
    indicator_wl = os.environ.get('TITLE_INDICATOR', DEFAULT_TITLE_INDICATOR).strip()
    indicator_bl = os.environ.get('TITLE_PREVENTOR', DEFAULT_TITLE_PREVENTOR).strip()
    title = title.lower()
    return ('*' == indicator_wl or indicator_wl.lower() in title) and (indicator_bl == '' or indicator_bl not in title)


def required_context():
    return os.environ.get('REQUIRED_CONTEXT', DEFAULT_CONTEXT)


class GitAutoMerger(object):
    def __init__(self, token, repo=None, sha=None, branch=None):
        self.token = token
        self.repo = repo
        self.sha = sha
        self.branch = branch
        self.pr = None
        self.pr_id = None

    def auto_merge(self):
        self._assertion(None not in [self.repo, self.sha, self.branch] is not None, 'invalid args')
        self._assertion(is_allowed_repository(self.repo), 'is_allowed_repository')
        self.validate_build_status()
        if self.pr_id is None or self.pr is None:
            self.get_pull_request()
        self._assertion(self.pr is not None, 'find pull request')
        self.validate_pull_request()
        self.validate_reviews()
        self.merge()
        self.remove_branch()

    def get(self, url, params=None, headers=None):
        if params is None:
            params = {}
        g = requests.get(url, params=params, headers=self.headers(headers))
        return g.json()

    def put(self, url, params):
        return requests.put(url, json=params, headers=self.headers()).json()

    def delete(self, url):
        return requests.delete(url, headers=self.headers())

    def headers(self, h=None):
        if h is None:
            h = {}
        h['Authorization'] = 'token ' + self.token
        return h

    def validate_build_status(self):
        res = self.get("https://api.github.com/repos/" + self.repo + "/commits/" + self.sha + "/status")
        logging.debug(res)
        self._assertion(res['state'] == 'success', 'build status is success', res)

    def get_pull_request(self):
        res = self.get("https://api.github.com/repos/" + self.repo + "/pulls",
                       params={"head": ":".join([self.repo.split('/')[0], self.branch])})
        logging.debug(res)
        for r in res:
            if 'statuses_url' in r and self.sha in r['statuses_url']:
                self.pr = r
                self.pr_id = r['number']

    def validate_pull_request(self):
        self._assertion(is_allowed_pr_title(self.pr['title']), 'pull request title allows auto merge')
        self._assertion('open' == self.pr['state'], 'pull request is open')
        self._assertion(self.pr['locked'] is False, 'pull request is not locked')

    def validate_reviews(self):
        g = self.get("https://api.github.com/repos/%s/pulls/%s/reviews" % (self.repo, self.pr_id),
                     headers={'Accept': 'application/vnd.github.black-cat-preview+json'})
        logging.debug(g)
        # A user cannot review himself
        filtered = list(filter(lambda f: f['user']['login'] != self.pr['user']['login'], g))
        self._assertion(len(g) >= 1, 'pull request has been reviewed')
        filtered.sort(key=lambda f: dateutil.parser.parse(f['submitted_at']), reverse=True)
        for user_id, grps in itertools.groupby(filtered, lambda x: x['user']['login']):
            grps = list(grps)
            self._assertion(grps[0]['state'] == 'APPROVED', 'pull request has been approved by %s' % (user_id, ))

    def merge(self):
        res = self.put("https://api.github.com/repos/%s/pulls/%s/merge" % (self.repo, self.pr_id),
                       {'sha': self.sha, 'commit_message': 'Automatically merged by Mergebot'})
        logging.debug(res)
        self._assertion(res.get('merged', False), 'merge pull request')

    def remove_branch(self):
        res = self.delete("https://api.github.com/repos/%s/git/refs/heads/%s" % (self.repo, self.branch))
        logging.debug(res)

    def _assertion(self, l, log=None, more_data=None):
        if log is not None:
            logging.debug(log + ": %s", l)
            if more_data is not None:
                logging.debug(more_data)
        if not l:
            msg = 'assertion failed'
            if log is not None:
                msg += ' ' + log
            raise ValueError(msg)


def git_review_handler(event, _context):
    logging.debug(event)
    event_name = event['headers']['X-GitHub-Event']
    j = json.loads(event['body'])

    am = GitAutoMerger(os.environ.get('GITHUB_TOKEN', ''))
    if 'ping' == event_name:
        return response(200, 'grass tastes bad')
    elif 'status' == event_name:
        repo = j['name']
        sha = j['sha']
        if not (j['state'] == 'success'):
            logging.info("Got state %s", j['state'])
            return response(200, 'Bad state ' + j['state'])
        if not (j['context'] == required_context()):
            logging.info("Got context %s", j['context'])
            return response(200, 'Bad context ' + j['context'])
        if not (len(j['branches']) == 1):
            logging.info("Got branches %s", j['branches'])
            return response(200, 'More than one branch')
        branches = j['branches']
        branch_name = branches[0]['name']
        logging.info("Starting for %s (%s), branch %s", repo, sha, branch_name)

        am.repo = repo
        am.sha = sha
        am.branch_name = branch_name
    elif 'pull_request_review' == event_name:
        if not (j['action'] == 'submitted'):
            logging.info("Got action %s", j['action'])
            return response(200, 'Bad action ' + j['action'])
        if not (j['review']['state'] == 'approved'):
            logging.info("Got state %s", j['review']['state'])
            return response(200, 'Bad state ' + j['review']['state'])
        pr = j['pull_request']
        am.repo = pr['head']['repo']['full_name']
        am.sha = pr['head']['sha']
        am.pr_id = pr['number']
        am.pr = pr
        am.branch = pr['head']['ref']
    else:
        return response(403, 'unsupported event ' + event)

    try:
        am.auto_merge()
        return response(200, 'merged yey')
    except ValueError as e:
        return response(200, e.message)