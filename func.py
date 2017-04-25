#!/usr/bin/python

import logging
import json
import requests
import os

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)


def response(status_code, status):
    return {'statusCode': status_code, 'body': status}


def is_allowed_repository(repo):
    return repo.lower() in [r.strip() for r in os.environ.get('ALLOWED_REPOS', '').lower().split(',')]


class GitAutoMerger(object):
    def __init__(self, token, repo, sha, branch):
        self.token = token
        self.repo = repo
        self.sha = sha
        self.branch = branch
        self.pr = None
        self.pr_id = None

    def auto_merge(self):
        # TODO: if not is_allowed_repository set, everything
        self._assertion(is_allowed_repository(self.repo), 'is_allowed_repository')
        self.validate_build_status()
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
        self._assertion('[am]' in self.pr['title'].lower(), 'pull request title allows auto merge')
        self._assertion('open' == self.pr['state'], 'pull request is open')
        self._assertion(self.pr['locked'] is False, 'pull request is not locked')

    def validate_reviews(self):
        g = self.get("https://api.github.com/repos/%s/pulls/%s/reviews" % (self.repo, self.pr_id),
                     headers={'Accept': 'application/vnd.github.black-cat-preview+json'})
        logging.debug(g)
        self._assertion(len(g) >= 1, 'pull request has been reviewed')
        self._assertion(all(map(lambda x: x['state'] == 'APPROVED', g)), 'pull request has been approved')

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
    j = json.loads(event['body'])

    repo = j['name']
    sha = j['sha']
    if not (j['state'] == 'success'):
        logging.info("Got state %s", j['state'])
        return response(200, 'Bad state ' + j['state'])
    if not (j['context'] == 'continuous-integration/travis-ci/pr'):
        logging.info("Got context %s", j['context'])
        return response(200, 'Bad context ' + j['context'])
    if not (len(j['branches']) == 1):
        logging.info("Got branches %s", j['branches'])
        return response(200, 'More than one branch')

    branches = j['branches']
    branch_name = branches[0]['name']
    logging.info("Starting for %s (%s), branch %s", repo, sha, branch_name)
    am = GitAutoMerger(os.environ.get('GITHUB_TOKEN', ''), repo, sha, branch_name)
    try:
        am.auto_merge()
        return response(200, 'merged yey')
    except ValueError, e:
        return response(200, e.message)
