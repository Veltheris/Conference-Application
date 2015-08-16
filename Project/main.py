#!/usr/bin/env python
"""
main.py -- Controller for Taskqueue
"""

__author__ = 'veltheris@gmail.com (Dylan Mountain)'

import webapp2
from google.appengine.api import app_identity
from conference import ConferenceApi

class CheckSpeaker(webapp2.RequestHandler):
    def post(self):
        """Check if speaker has multiple sessions, adding them as featured speaker if so."""
        #websafeKey = getattr(self.request, "websafeKey")
        websafeKey = self.request.get('websafeKey')
        #speaker = getattr(self.request, "speaker")
        speaker = self.request.get('speaker')
        ConferenceApi._speakerCheck(websafeKey,speaker)        

app = webapp2.WSGIApplication([
    ('/tasks/checkSpeaker', CheckSpeaker),
], debug=True)
