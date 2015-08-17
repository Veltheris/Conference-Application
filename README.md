#Conference Manager Application
This is a python-powered AppEngine Application for a backend api to create and manages conferences. Users can create and register for conferences, as well as add sessions within conferences. Users can also query for existing conferences and sessions.

###Table of Contents
- Requirements
- Installation/Setup
  - Routes Reference
- Session Implementation
- Additional Quries
- Query Problem
- Changelog
- Commenets

##Requirements
This application exists as a web version, available using [https://v-udacity-course-projects.appspot.com/_ah/api/explorer] in a web browser.
The application can also be ran locally. Doing so require`s Google`s AppEngine client. See [https://developers.google.com/appengine] for downloads.


##Installation/Setup
Place this folder somewhere easily accessible. This application can be used without change, either on appspot at  [https://v-udacity-course-projects.appspot.com/_ah/api/explorer] or locally from [http://localhost:8080/_ah/api/explorer]. To Run locally, open up the AppEngine client, and select `File | Add Existing Application`. Select this folder in the browse folder dialog. You must use port 8080 to run using v-udacity-course-projects. To use with other addresses, `application` in `app.yaml` and `WEB_CLIENT_ID` in `settings.py` must be changed to your application name and key.

Once at the website, select `conference API`. This allows testing and use of the api functions. Below is a list of all api functions, and their parameters. (Auth) means the function requires authentication by OAuth to recive results. This can be toggled in the right corner.

###Routes Reference
- **getProfile()**  
(Auth, GET) Returns the current User profile

- **saveProfile(ProfileForm)**  
(Auth, POST) Creates or Updates a profile.
  - Name: Display Name
  - teeShirtSize: A EnumField. Defaults to NOT_SPECIFIED
    - NOT_SPECIFIED: Default Value.
    - XS_M: Extra-Small Mens
    - XS_W: Extra-Small Womens
    - S_M: Small Mens
    - S_W: Small Womens
    - M_M: Medium Mens
    - M_W: Medium Womens
    - L_M: Large Mens
    - L_W: Large Womens
    - XL_M: Extra-Large Mens
    - XL_W: Extra-Large Womens
    - XXL_M: XX-Large Mens
    - XXL_W: XX-Large Womens
    - XXXL_M: XXX-Large Mens
    - XXXL_W: XXX-Large Womens


- **createConference(ConferenceForm)**  
(Auth, POST) Creates a new conference.
  - name: Name of conference
  - description: Description of conference
  - topics: Topics of the Conference. Can enter multiple times.
  - city: City where the conference is held.
  - startDate: Starting date in form YYYY-MM-DD
  - month: Month of the year, in number form.
  - maxAttendees: Number of available spots.
  - endDate: Ending date in form YYYY-MM-DD

- **queryConferences()**  
(GET) Returns a list of conferences. Can be given filters.

- **getConferencesCreated()**  
(Auth, GET) Returns all conferences a user created.

- **registerForConference(websafeConferenceKey)**  
(Auth, POST) Register for a conference using it's key.
  - websafeConferenceKey: Conference's websafe key. Use queryConferences() to find.

- **getConferencesToAttend()**  
(Auth, GET) Returns all conferences a user is registered for.

- **getConferenceSessions(websafeConferenceKey)**  
(GET) Given a conference's websafe key, return all sessions.
  - websafeConferenceKey: Conference's websafe key. Use queryConferences() to find.

- **getConferenceSessionsByType(websafeConferenceKey, typeOfSession)**
(GET) Given a conference, return all sessions of a specified type (eg lecture, keynote, workshop)
  - websafeConferenceKey: Conference's websafe key. Use queryConferences() to find.
  - typeOfSession: They type of session you are looking for.

- **getSessionsBySpeaker(speaker)**
(GET) Given a speaker, return all sessions given by this particular speaker, across all conferences
  - speaker: Speaker's name

- **getSessionsByDuration(websafeConferenceKey, duration, direction)**
(GET) Given a conference, duration and direction, returns all sessions that fit the requirements.
  - websafeConferenceKey: Conference's websafe key. Use queryConferences() to find.
  - duration: in minutes
  - direction: Boolean Operator. True for more than duration.

- **getSessionsByStartTime(websafeConferenceKey, startTime, direction)**
(GET) Given a conference, starting time and direction, returns all sessions that fit the requirements.
  - websafeConferenceKey: Conference's websafe key. Use queryConferences() to find.
  - startTime: Starting time in 24 hour format HH:MM
  - direction: Boolean Operator. True for after startTime.

- **createSession(SessionForm, websafeConferenceKey)**
(Auth, POST) Creates a new session in the given conference. Must be the owner of the conference.
  - websafeConferenceKey: Conference's websafe key. Use queryConferences() to find.
  - name: Name of the new session.
  - typeOfSession: Type of the session (eg lecture, keynote, workshop). Can be entered multiple times.
  - highlights: Highlights of the session. Can be entered multiple times.
  - speaker: Speaker for the session. Can be entered multiple times.
  - duration: Session's duration, in minutes.
  - date: Date of the session.
  - startTime: Starting time of the session, in 24-hour format HH:MM

- **addSessionToWishlist(SessionKey)**
(Auth, POST) Adds the session to the user's list of sessions they are interested in attending.
  - sessionKey: Key for the session to add.

- **removeSessionFromWishlist(SessionKey)**
(Auth, POST) Removes the session to the user's list of sessions they are interested in attending.
  - sessionKey: Key for the session to remove.

- **getSessionsInWishlist()**
(Auth, POST) Returns all sessions in the user's wishlist

- **getFeaturedSpeaker()**
(GET) Returns the featured speaker, if there is one.

##Session Implementation
Sessions are implemented as a full `ndb.Model` Class, using conference as an ancestor. Duration, StartTime, and Date are implemented as Integer, Time, and Date respectively. StartTime is a time object because it refers to a discrete time, while Duration is an integer because it is a length of time. The remaining properties are Strings. Highlights, Topics, and Speaker are repeated, as a session could conceivable have multiple speakers or topics. I didn't use Enum values, as I wasn't sure what the possiple results are for highlights and topics.

I chose to implement speaker as a simple property of Session, rather than a full entity on it's own. Speaker as an entity would be useful if there were man properties of a speaker to note on their own.

##Additional Queries
For additional queries, I decided to base them off the currently unused duration and startTime values. I had the queries take in a property as well as a boolean value. This Boolean value would determine if the resulting filter operation used greater than or less than.

These queries have been implemented as getSessionsByStartTime and getSessionsByDuration.

##Query Problem
Querying for all sessions that are not workshop sessions and are before 7:00PM sounds like it should be an easy query. However, NDB has a number of restrictions. While Query objects can be filtered with Not Equal to (`!=`), they are implemented as being the same as Less than or Greater than (`> or <`). While this sounds similar to Not Equal to, it means that sessions that have the topics of Workshop *and* Lecture would count as "Not Equal to" just Workshop.

The implementation of Not Equal to also causes a larger issue for the Query. One of the big restrictions of NDB is that you cannot filter with inequalities on two different properties. Since Not Equal to is implemented using them, you can't have both it and sessions Less Than 7:00PM at the same time.

One way around these issues at the cost of efficiency, is to only run one of the filters and than manually check the results in the `For` loop. This would enable you to at least give the desired Sessions.

##Changelog

###Version 1.0
- First Submitted Version.

###Version 1.1
- Second Version
- Fixed an issue with getSessionsByStartTime()
- Added default values to session to clear some issues with SessionForms
- Fixed path names that would result in a 404 when viewed through API Explorer
- Wishlist adding and removing now returns a string as well as a Boolean value.

##Commenets
This was a fun project, though AppEngine is a bit annoying to work with.