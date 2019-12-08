#!/usr/bin/python

import logging
import os
import boto3
import base64

import github_webhook
from auto_merger import GitAutoMerger

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

ENCRYPTED_KEYS = ('GITHUB_SECRET', 'GITHUB_TOKEN')


def get_environment_var(var, decryption_required=False):
    v = os.environ.get(var, '')
    if decryption_required and var in ENCRYPTED_KEYS and '1' == os.environ.get('ENCRYPTION_ENABLED', '0').strip():
        return boto3.client('kms').decrypt(CiphertextBlob=base64.b64decode(v))['Plaintext']
    return v


def response(status_code, status):
    return {'statusCode': status_code, 'body': status}


def git_review_handler(event, _context):
    logging.debug(event)
    webhook = github_webhook.Webhook(event['body']['payload'], event['headers'], get_environment_var('GITHUB_SECRET', True))
    if not webhook.is_valid_request():
        return response(404, 'not found')
    j = webhook.event

    am = GitAutoMerger(get_environment_var('GITHUB_TOKEN', True))
    if 'ping' == webhook.event_name:
        return response(200, 'grass tastes bad')

    elif 'check_suite' == webhook.event_name:
        am.repo = j['repository']['full_name']
        am.sha = j['check_suite']['head_sha']
        am.branch = j['check_suite']['head_branch']

    elif 'status' == webhook.event_name:
        am.repo = j['name']
        am.sha = j['sha']

        if not (len(j['branches']) == 1):
            logging.info("Got branches %s", j['branches'])
            return response(200, 'More than one branch')

        branches = j['branches']
        am.branch = branches[0]['name']

    elif 'pull_request_review' == webhook.event_name:
        pr = j['pull_request']
        am.repo = pr['head']['repo']['full_name']
        am.sha = pr['head']['sha']
        am.pr_id = pr['number']
        am.branch = pr['head']['ref']

    else:
        return response(403, 'unsupported event ' + event)

    logging.info("Starting for %s (%s), branch %s", am.repo, am.sha, am.branch)

    try:
        am.auto_merge()
        return response(200, 'merged yey')
    except ValueError as e:
        return response(200, e.message)

