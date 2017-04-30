#!/usr/bin/python

import logging
import os

import github_webhook
from auto_merger import GitAutoMerger

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

DEFAULT_CONTEXT = 'continuous-integration/travis-ci/pr'


def response(status_code, status):
    return {'statusCode': status_code, 'body': status}


def required_context():
    return os.environ.get('REQUIRED_CONTEXT', DEFAULT_CONTEXT)


def git_review_handler(event, _context):
    logging.debug(event)
    webhook = github_webhook.Webhook(event['body'], event['headers'], os.environ.get('GITHUB_SECRET', ''))
    if not webhook.is_valid_request():
        return response(404, 'not found')
    j = webhook.event

    am = GitAutoMerger(os.environ.get('GITHUB_TOKEN', ''))
    if 'ping' == webhook.event_name:
        return response(200, 'grass tastes bad')
    elif 'status' == webhook.event_name:
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
        am.branch = branch_name
    elif 'pull_request_review' == webhook.event_name:
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
