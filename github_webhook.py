import hmac
import hashlib
import logging
import json


class Webhook(object):
    def __init__(self, event, headers, secret=None):
        self.event_data = event
        self.headers = headers
        self.secret = secret
        self.event = json.loads(event)
        self.event_name = headers.get('X-GitHub-Event')

    def is_valid_request(self):
        if self.secret is None:
            return False

        signature = self.headers.get('X-Hub-Signature')
        if signature is None:
            logging.error('X-Hub-Signature missing')
            logging.info(list(self.headers.keys()))
            return False

        mac = hmac.new(str(self.secret), msg=self.event_data, digestmod=hashlib.sha1)
        return hmac.compare_digest(str("sha1=%s" % (mac.hexdigest(),)), str(signature))
