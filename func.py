#!/usr/bin/python

import logging
import os
import boto3
import base64
import json
import random
import requests

import github_webhook
from auto_merger import GitAutoMerger

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

s3 = boto3.resource('s3')

DEFAULT_CONTEXT = 'continuous-integration/travis-ci/pr'
ENCRYPTED_KEYS = ('GITHUB_SECRET', 'GITHUB_TOKEN')


def get_environment_var(var):
    v = os.environ.get(var, '')
    if var in ENCRYPTED_KEYS and '1' == os.environ.get('ENCRYPTION_ENABLED', '0').strip():
        return boto3.client('kms').decrypt(CiphertextBlob=base64.b64decode(v))['Plaintext']
    return v


def response(status_code, status):
    return {'statusCode': status_code, 'body': status}


def required_context():
    return os.environ.get('REQUIRED_CONTEXT', DEFAULT_CONTEXT)


def git_review_handler(event, _context):
    logging.debug(event)
    webhook = github_webhook.Webhook(event['body'], event['headers'], get_environment_var('GITHUB_SECRET'))
    if not webhook.is_valid_request():
        return response(400, 'bad request')
    j = webhook.event

    am = GitAutoMerger(get_environment_var('GITHUB_TOKEN'))
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

def ask_for_review(event, _context):
    logging.debug(event)
    webhook = github_webhook.Webhook(event['body'], event['headers'], get_environment_var('GITHUB_SECRET'))
    if not webhook.is_valid_request():
        return response(400, 'bad request')
    j = webhook.event


    if 'pull_request' == webhook.event_name:
        if not (j['action'] == 'opened'):
            logging.info("Got action %s", j['action'])
            return response(200, 'Nothing to do when action ' + j['action'])
        # TODO To be able to override specific reviewers look here for a file with the repo name, else fallback to the default one
        file = s3.Object(get_environment_var('PULL_REQUEST_REVIEWERS_BUCKET'), "default.json").get()['Body'].read()
        reviewers = json.loads(file)
        victims = random.sample(reviewers, 1)
        for victim in victims:
            slack_url = victim["slack_webhook"]
            slack_data = { "text": "Please review my PR: " + j['pull_request']['title'] }
            requests.post(slack_url, data=json.dumps(slack_data), headers={ 'Content-Type': 'application/json' })
