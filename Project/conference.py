#!/usr/bin/env python

"""
conference.py -- Conference server-side Python App Engine API;
    uses Google Cloud Endpoints
"""

__author__ = 'veltheris@gmail.com (Dylan Mountain)'

  #############
#### Imports ###############################################################
  #############

### Basic Imports ###
from datetime import datetime

### AppEngine Imports ###
import endpoints
import logging

from protorpc import messages
from protorpc import message_types
from protorpc import remote

from google.appengine.ext import ndb
from google.appengine.api import taskqueue
from google.appengine.api import memcache

### Custom Models Imports ###
# -Profile
from models import Profile
from models import ProfileMiniForm
from models import ProfileForm
from models import TeeShirtSize
# -Conference
from models import Conference
from models import ConferenceForm
from models import ConferenceForms
from models import ConferenceQueryForm
from models import ConferenceQueryForms

# -Registration
from models import BooleanMessage
from models import ConflictException

# -Session
from models import Session
from models import SessionForm
from models import SessionForms
from models import QuerySessionByKey
from models import QuerySessionByType
from models import QuerySessionBySpeaker
from models import QuerySessionByDuration
from models import QuerySessionByStartTime
from models import SessionWebsafe
from models import StringMessage

### Settings and Utilities ###
from utils import getUserId

from settings import WEB_CLIENT_ID


  ######################
#### Global Variables #####################################################
  ######################

EMAIL_SCOPE = endpoints.EMAIL_SCOPE
API_EXPLORER_CLIENT_ID = endpoints.API_EXPLORER_CLIENT_ID

DEFAULTS = {
    "city": "Default City",
    "maxAttendees": 0,
    "seatsAvailable": 0,
    "topics": [ "Default", "Topic" ],
}

OPERATORS = {
            'EQ':   '=',
            'GT':   '>',
            'GTEQ': '>=',
            'LT':   '<',
            'LTEQ': '<=',
            'NE':   '!='
            }

FIELDS =    {
            'CITY': 'city',
            'TOPIC': 'topics',
            'MONTH': 'month',
            'MAX_ATTENDEES': 'maxAttendees',
            }

CONF_GET_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeConferenceKey=messages.StringField(1),
)

MEMCACHE_FEATURED_KEY = "FeaturedKEY"

  ########################
#### Endpoint Functions ###########################################################
  ########################

@endpoints.api( name='conference',
                version='v1',
                allowed_client_ids=[WEB_CLIENT_ID, API_EXPLORER_CLIENT_ID],
                scopes=[EMAIL_SCOPE])
class ConferenceApi(remote.Service):
    """Conference API v0.1"""

#--------------------------------### Profiles ###--------------------------------------------------#

    def _copyProfileToForm(self, prof):
        """Copy relevant fields from Profile to ProfileForm."""
        # copy relevant fields from Profile to ProfileForm
        pf = ProfileForm()
        for field in pf.all_fields():
            if hasattr(prof, field.name):
                # convert t-shirt string to Enum; just copy others
                if field.name == 'teeShirtSize':
                    setattr(pf, field.name, getattr(TeeShirtSize, getattr(prof, field.name)))
                else:
                    setattr(pf, field.name, getattr(prof, field.name))
        pf.check_initialized()
        return pf


    def _getProfileFromUser(self):
        """Return user Profile from datastore, creating new one if non-existent."""
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')

        # get Profile from datastore
        user_id = getUserId(user)
        p_key = ndb.Key(Profile, user_id)
        profile = p_key.get()
        # create new Profile if not there
        if not profile:
            profile = Profile(
                key = p_key,
                displayName = user.nickname(),
                mainEmail= user.email(),
                teeShirtSize = str(TeeShirtSize.NOT_SPECIFIED),
            )
            profile.put()

        return profile      # return Profile


    def _doProfile(self, save_request=None):
        """Get user Profile and return to user, possibly updating it first."""
        # get user Profile
        prof = self._getProfileFromUser()

        # if saveProfile(), process user-modifyable fields
        if save_request:
            for field in ('displayName', 'teeShirtSize'):
                if hasattr(save_request, field):
                    val = getattr(save_request, field)
                    if val:
                        setattr(prof, field, str(val))
            prof.put()

        # return ProfileForm
        return self._copyProfileToForm(prof)


    @endpoints.method(message_types.VoidMessage, ProfileForm,
            path='profile', http_method='GET', name='getProfile')
    def getProfile(self, request):
        """Return user profile."""
        return self._doProfile()


    @endpoints.method(ProfileMiniForm, ProfileForm,
            path='profile', http_method='POST', name='saveProfile')
    def saveProfile(self, request):
        """Update & return user profile."""
        return self._doProfile(request)


#--------------------------------### Conferences ###--------------------------------------------------#

    def _copyConferenceToForm(self, conf, displayName):
        """Copy relevant fields from Conference to ConferenceForm."""
        cf = ConferenceForm()
        for field in cf.all_fields():
            if hasattr(conf, field.name):
                # convert Date to date string; just copy others
                if field.name.endswith('Date'):
                    setattr(cf, field.name, str(getattr(conf, field.name)))
                else:
                    setattr(cf, field.name, getattr(conf, field.name))
            elif field.name == "websafeKey":
                setattr(cf, field.name, conf.key.urlsafe())
        if displayName:
            setattr(cf, 'organizerDisplayName', displayName)
        cf.check_initialized()
        return cf


    def _createConferenceObject(self, request):
        """Create or update Conference object, returning ConferenceForm/request."""
        # preload necessary data items
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)

        if not request.name:
            raise endpoints.BadRequestException("Conference 'name' field required")

        # copy ConferenceForm/ProtoRPC Message into dict
        data = {field.name: getattr(request, field.name) for field in request.all_fields()}
        del data['websafeKey']
        del data['organizerDisplayName']

        # add default values for those missing (both data model & outbound Message)
        for df in DEFAULTS:
            if data[df] in (None, []):
                data[df] = DEFAULTS[df]
                setattr(request, df, DEFAULTS[df])

        # convert dates from strings to Date objects; set month based on start_date
        if data['startDate']:
            data['startDate'] = datetime.strptime(data['startDate'][:10], "%Y-%m-%d").date()
            data['month'] = data['startDate'].month
        else:
            data['month'] = 0
        if data['endDate']:
            data['endDate'] = datetime.strptime(data['endDate'][:10], "%Y-%m-%d").date()

        # set seatsAvailable to be same as maxAttendees on creation
        # both for data model & outbound Message
        if data["maxAttendees"] > 0:
            data["seatsAvailable"] = data["maxAttendees"]
            setattr(request, "seatsAvailable", data["maxAttendees"])

        # make Profile Key from user ID
        p_key = ndb.Key(Profile, user_id)
        # allocate new Conference ID with Profile key as parent
        c_id = Conference.allocate_ids(size=1, parent=p_key)[0]
        # make Conference key from ID
        c_key = ndb.Key(Conference, c_id, parent=p_key)
        data['key'] = c_key
        data['organizerUserId'] = request.organizerUserId = user_id

        # create Conference & return (modified) ConferenceForm
        Conference(**data).put()

        return request


    @endpoints.method(ConferenceForm, ConferenceForm, path='conference',
            http_method='POST', name='createConference')
    def createConference(self, request):
        """Create new conference."""
        return self._createConferenceObject(request)


    @endpoints.method(ConferenceQueryForms, ConferenceForms,
                path='queryConferences',
                http_method='POST',
                name='queryConferences')
    def queryConferences(self, request):
        """Query for conferences."""
        #conferences = Conference.query()
        conferences = self._getQuery(request)
         # return individual ConferenceForm object per Conference
        return ConferenceForms(
            items=[self._copyConferenceToForm(conf, "") \
            for conf in conferences]
        )

    @endpoints.method(message_types.VoidMessage, ConferenceForms,
            path='getConferencesCreated',
            http_method='POST', name='getConferencesCreated')
    def getConferencesCreated(self, request):
        """Return conferences created by user."""
        # make sure user is authed
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
    
        # make profile key
        p_key = ndb.Key(Profile, getUserId(user))
        # create ancestor query for this user
        conferences = Conference.query(ancestor=p_key)
        # get the user profile and display name
        prof = p_key.get()
        displayName = getattr(prof, 'displayName')
        # return set of ConferenceForm objects per Conference
        return ConferenceForms(
            items=[self._copyConferenceToForm(conf, displayName) for conf in conferences]
        )


#--------------------------------### Queries ###--------------------------------------------------#

    def _getQuery(self, request):
        """Return formatted query from the submitted filters."""
        q = Conference.query()
        inequality_filter, filters = self._formatFilters(request.filters)

        # If exists, sort on inequality filter first
        if not inequality_filter:
            q = q.order(Conference.name)
        else:
            q = q.order(ndb.GenericProperty(inequality_filter))
            q = q.order(Conference.name)

        for filtr in filters:
            if filtr["field"] in ["month", "maxAttendees"]:
                filtr["value"] = int(filtr["value"])
            formatted_query = ndb.query.FilterNode(filtr["field"], filtr["operator"], filtr["value"])
            q = q.filter(formatted_query)
        return q


    def _formatFilters(self, filters):
        """Parse, check validity and format user supplied filters."""
        formatted_filters = []
        inequality_field = None

        for f in filters:
            filtr = {field.name: getattr(f, field.name) for field in f.all_fields()}

            try:
                filtr["field"] = FIELDS[filtr["field"]]
                filtr["operator"] = OPERATORS[filtr["operator"]]
            except KeyError:
                raise endpoints.BadRequestException("Filter contains invalid field or operator.")

            # Every operation except "=" is an inequality
            if filtr["operator"] != "=":
                # check if inequality operation has been used in previous filters
                # disallow the filter if inequality was performed on a different field before
                # track the field on which the inequality operation is performed
                if inequality_field and inequality_field != filtr["field"]:
                    raise endpoints.BadRequestException("Inequality filter is allowed on only one field.")
                else:
                    inequality_field = filtr["field"]

            formatted_filters.append(filtr)
        return (inequality_field, formatted_filters)

#--------------------------------### Registration ###--------------------------------------------------#

    @ndb.transactional(xg=True)
    def _conferenceRegistration(self, request, reg=True):
        """Register or unregister user for selected conference."""
        retval = None
        prof = self._getProfileFromUser() # get user Profile

        # check if conf exists given websafeConfKey
        # get conference; check that it exists
        wsck = request.websafeConferenceKey
        conf = ndb.Key(urlsafe=wsck).get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % wsck)

        # register
        if reg:
            # check if user already registered otherwise add
            if wsck in prof.conferenceKeysToAttend:
                raise ConflictException(
                    "You have already registered for this conference")

            # check if seats avail
            if conf.seatsAvailable <= 0:
                raise ConflictException(
                    "There are no seats available.")

            # register user, take away one seat
            prof.conferenceKeysToAttend.append(wsck)
            conf.seatsAvailable -= 1
            retval = True

        # unregister
        else:
            # check if user already registered
            if wsck in prof.conferenceKeysToAttend:

                # unregister user, add back one seat
                prof.conferenceKeysToAttend.remove(wsck)
                conf.seatsAvailable += 1
                retval = True
            else:
                retval = False

        # write things back to the datastore & return
        prof.put()
        conf.put()
        return BooleanMessage(data=retval)


    @endpoints.method(CONF_GET_REQUEST, BooleanMessage,
            path='conference/{websafeConferenceKey}',
            http_method='POST', name='registerForConference')
    def registerForConference(self, request):
        """Register user for selected conference."""
        return self._conferenceRegistration(request)


    @endpoints.method(message_types.VoidMessage, ConferenceForms,
            path='conferences/attending',
            http_method='GET', name='getConferencesToAttend')
    def getConferencesToAttend(self, request):
        """Get list of conferences that user has registered for."""
        # TODO:
        # step 1: get user profile
        profile = self._getProfileFromUser() # get user Profile
        # step 2: get conferenceKeysToAttend from profile.
        safekeys = profile.conferenceKeysToAttend
        # to make a ndb key from websafe key you can use:
        #keys = ()
        #for safekey in safekeys:
        #    keys.append(ndb.Key(urlsafe=safekey))
        keys = (ndb.Key(urlsafe=safekey) for safekey in safekeys)
        # step 3: fetch conferences from datastore. 
        # Use get_multi(array_of_keys) to fetch all keys at once.
        # Do not fetch them one by one!
        conferences = ndb.get_multi(keys)
        # return set of ConferenceForm objects per Conference
        return ConferenceForms(items=[self._copyConferenceToForm(conf, "")\
         for conf in conferences]
        )
    
  ##############################
#### Additional Functionality ########################################
  ##############################
    
    #Backend process for turning query results into result objects
    def _formatSession(self, session):
        """Copy relevant fields from Session to SessionForm."""
        result = SessionForm()
        for field in result.all_fields():
            if hasattr(session, field.name):
                # convert Date to date string; just copy others
                if field.name == 'startTime' or field.name == 'date':
                    setattr(result, field.name, str(getattr(session, field.name)))
                else:
                    setattr(result, field.name, getattr(session, field.name))
                    #setattr(result, field.name, field.name)
            if field.name == "websafeConferenceKey":
                setattr(result, field.name, session.key.parent().urlsafe())
            if field.name == "websafeKey":
                setattr(result, field.name, session.key.urlsafe())
        #if displayName:
        #setattr(cf, 'organizerDisplayName', displayName)
        if not result.websafeKey:
            raise endpoints.BadRequestException("Oh noes")
        result.check_initialized()
        return result

    
    #Backend process to create a session
    def _createSession(self, request):
        """Add a Session, returning Session/request."""
        # preload necessary data items
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)
        
        if not request.name:
            raise endpoints.BadRequestException("Conference 'name' field required")
        
        data = {field.name: getattr(request, field.name) for field in request.all_fields()}
        
        conference_id = ndb.Key(urlsafe=data['websafeConferenceKey'])
        #check if the user id is the same as the conference's parent.
        if user_id != conference_id.parent().string_id():
            raise endpoints.UnauthorizedException('Must be owner of conference')
        
        del data['websafeConferenceKey']
        data['conferenceId'] = conference_id.string_id()
        # convert dates from strings to Date objects; set month based on start_date
        if data['date']:
            data['date'] = datetime.strptime(data['startDate'][:10], "%Y-%m-%d").date()
        if data['startTime']:
            data['startTime'] = datetime.strptime(data['startTime'][:5], "%H:%M").time()
        # make Profile Key from user ID
        #c_key = ndb.Key(Conference, conference_id)
        c_key = conference_id
        # allocate new Conference ID with Profile key as parent
        s_id = Session.allocate_ids(size=1, parent=c_key)[0]
        # make Conference key from ID
        s_key = ndb.Key(Session, s_id, parent=c_key)
        data['key'] = s_key
        #data['parentConference'] = request.parentConference = conference_id
        
        # create Conference & return (modified) ConferenceForm
        Session(**data).put()
        if data['speaker']:
            taskqueue.add(params={'websafeKey': c_key.urlsafe(),
                                  'speaker': data['speaker']},
                                  url='/tasks/checkSpeaker')
        return request

    #Backend process for adding or removing from wishlist.
    def _wishlistChange(self, request, add=True):
        """Register or unregister user for selected conference."""
        result = None
        profile = self._getProfileFromUser() # get user Profile

        # check if conf exists given websafeConfKey
        # get conference; check that it exists
        session_key = request.websafeKey
        session = ndb.Key(urlsafe=session_key).get()
        if not session:
            raise endpoints.NotFoundException(
                'There is no session with key: %s' % session_key)
        # register
        if add:
            # See if the session is already on wishlist
            if session_key in profile.sessionWishlist:
                raise ConflictException(
                    "This session is on your wishlist already")
            # add the session to the wishlist
            profile.sessionWishlist.append(session_key)
            result = "Session added to Wishlist"

        # remove from wishlist
        else:
            # See if the session is already on wishlist
            if session_key in profile.sessionWishlist:
                # remove the session from wishlist
                profile.sessionWishlist.remove(session_key)
                result = "Session removed from Wishlist"
            else:
                raise ConflictException("This session is not on your wishlist")

        # write things back to the datastore & return
        profile.put()
        return BooleanMessage(data=result)
        

#-------------------------------### Methods - Basic ###------------------------------#

   #Method that Creates a session.
    @endpoints.method(SessionForm, SessionForm, path='session/new',
            http_method='POST', name='createSession')
    def createSession(self, request):
        """Create new session."""
        return self._createSession(request)

    #Method that queries sessions by conference key.
    @endpoints.method(QuerySessionByKey, SessionForms,
            path='sessions/conference/all',
            http_method='GET', name='getConferenceSessions')
    def getConferenceSessions(self, request):
        """websafeConferenceKey -- Given a conference, return all sessions"""
        safe_key = getattr(request, "websafeConferenceKey")
        conference_key = ndb.Key(urlsafe=safe_key)
        sessions = Session.query(ancestor=conference_key)
        sessions = sessions.order(Session.name)
         # return individual Session Forms
        return SessionForms(
            items=[self._formatSession(session) for session in sessions]
        )
    
#-------------------------------### Methods - Query ###------------------------------#
    
    #Method to query sessions by type and key
    @endpoints.method(QuerySessionByType, SessionForms,
            path='sessions/conference/type',
            http_method='GET', name='getConferenceSessionsByType')
    def getConferenceSessionsByType(self, request):
        """websafeConferenceKey, typeOfSession -- Given a conference, return all sessions of a specified type (eg lecture, keynote, workshop)"""
        safe_key = getattr(request, "websafeConferenceKey")
        speaker = getattr(request, "typeOfSession")
        conference_key = ndb.Key(urlsafe=safe_key)
        sessions = Session.query(ancestor=conference_key)
        sessions = sessions.filter(Session.typeOfSession==typeOfSession)
        sessions = sessions.order(Session.name)
         # return individual Session Forms
        return SessionForms(
            items=[self._formatSession(session) for session in sessions]
        )

    #Method to query sessions by speaker    
    @endpoints.method(QuerySessionBySpeaker, SessionForms,
            path='sessions/speaker',
            http_method='GET', name='getSessionsBySpeaker')
    def getSessionsBySpeaker(self, request):
        """speaker -- Given a speaker, return all sessions given by this particular speaker, across all conferences"""
        speaker = getattr(request, "speaker")
        sessions = Session.query()
        sessions = sessions.filter(Session.speaker==speaker)
        sessions = sessions.order(Session.name)
         # return individual Session Forms
        return SessionForms(
            items=[self._formatSession(session) for session in sessions]
        )
 
    #Method to query sessions by duration
    @endpoints.method(QuerySessionByDuration, SessionForms,
            path='sessions/duration',
            http_method='GET', name='getSessionsByDuration')
    def getSessionsByDuration(self, request):
        """Grab sessions by their duration."""
        safe_key = getattr(request, "websafeConferenceKey")
        duration = getattr(request, "duration")
        direction = getattr(request, "direction")
        conference_key = ndb.Key(urlsafe=safe_key)
        sessions = Session.query(ancestor=conference_key)
        field = 'duration'
        if direction:
            operator = '>'
        else:
            operator = '<'
        value = duration
        queryFilter = ndb.query.FilterNode(field,operator,value)
        sessions = sessions.filter(queryFilter)
        sessions = sessions.order(Session.duration)
        sessions = sessions.order(Session.name)
         # return individual Session Forms
        return SessionForms(
            items=[self._formatSession(session) for session in sessions]
        )

    #method to query sessions by StartTime
    @endpoints.method(QuerySessionByStartTime, SessionForms,
            path='sessions/startTime',
            http_method='GET', name='getSessionsByStartTime')
    def getSessionsByStartTime(self, request):
        """Get sessions by the Start Time."""
        safe_key = getattr(request, "websafeConferenceKey")
        startTime = getattr(request, "startTime")
        startTime = datetime.strptime(startTime[:5], "%H:%M").time()
        direction = getattr(request, "direction")
        conference_key = ndb.Key(urlsafe=safe_key)
        sessions = Session.query(ancestor=conference_key)
        sessions = Session.query(ancestor=conference_key)
        field = 'startTime'
        if direction:
            operator = '>'
        else:
            operator = '<'
        value = startTime
        queryFilter = ndb.query.FilterNode(field,operator,value)
        sessions = sessions.filter(queryFilter)
        sessions = sessions.order(Session.startTime)
        sessions = sessions.order(Session.name)
         # return individual Session Forms
        return SessionForms(
            items=[self._formatSession(session) for session in sessions]
        )

#-------------------------------### Methods - Wishlist ###------------------------------#

    #Method to add to wishlist
    @endpoints.method(SessionWebsafe, BooleanMessage,
            path='session/wishlist/add/',
            http_method='GET', name='addSessionToWishlist')
    def addSessionToWishlist(self, request):
        """SessionKey -- adds the session to the user's list of sessions they are interested in attending."""
        return self._wishlistChange(request, add=True)

    #Method to remove from wishlist
    @endpoints.method(SessionWebsafe, BooleanMessage,
            path='session/wishlist/remove/',
            http_method='GET', name='removeSessionFromWishlist')
    def removeSessionFromWishlist(self, request):
        """SessionKey -- adds the session to the user's list of sessions they are interested in attending."""
        return self._wishlistChange(request, add=False)
      
    
    @endpoints.method(message_types.VoidMessage, SessionForms,
            path='sessions/wishlist',
            http_method='GET', name='getSessionsInWishlist')
    def getSessionsInWishlist(self, request):
        """Get list of conferences that user has registered for."""
        profile = self._getProfileFromUser() # get user Profile
        safekeys = profile.sessionWishlist
        keys = (ndb.Key(urlsafe=safekey) for safekey in safekeys)
        sessions = ndb.get_multi(keys)
        # return set of ConferenceForm objects per Conference
        return SessionForms(items=[self._formatSession(session) for session in sessions]
        )

#-------------------------------### Methods - Task Completion ###------------------------------#

    #Function to query speakers. Used by the Task Queue
    @staticmethod
    def _speakerCheck(safe_key,speaker):
        logging.info(speaker)
        conference_key = ndb.Key(urlsafe=safe_key)
        sessions = Session.query(ancestor=conference_key)
        #sessions = Session.query()
        sessions = sessions.filter(Session.speaker == speaker)
        sessions = sessions.order(Session.name)
        count = sessions.count()
        logging.info(count)
        if count >= 2:
            announcement = "The current Featured Speaker is %s! He will be speaking at %s sessions." % (speaker, count)
            memcache.set(MEMCACHE_FEATURED_KEY, announcement)

    #Method to manually get the Featured Speaker
    @endpoints.method(message_types.VoidMessage, StringMessage,
            path='sessions/speaker/featured',
            http_method='GET', name='getFeaturedSpeaker')
    def getFeaturedSpeaker(self, request):
        """Get the featured speaker."""
        announcement = memcache.get(MEMCACHE_FEATURED_KEY)
        if not announcement:
            announcement = "There are no featured speakers right now."
        return StringMessage(data=announcement)

      
  ###################
#### Register API #############################################################
  ###################
api = endpoints.api_server([ConferenceApi]) 
