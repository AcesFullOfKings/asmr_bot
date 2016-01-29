#using /u/asmr_bot 


############
# I've removed sensitive data from this file to publish it on 
# github. If you run it as-is, it won't work, but you can replace
# removed data with your own values.
############

import praw
import time
import datetime
#import gdata.youtube
import urllib2
import json
import sqlite3
import re
import random
import shelve
import string # <-- it's stupid that I need to do this

#PRAW details - removed sensitive data
appUserAgent = Removed
appID = Removed
appSecret = Removed
appURI = Removed
appRefreshToken = Removed # doesn't expire
changed = True
vidIDregex = re.compile('(youtu\.be\/|youtube\.com\/(watch\?(.*&)?v=|(embed|v)\/))([^\?&\"\'>]+)')
toplist = shelve.open("topPosts",'c')

#gdata details - removed sensitive data for publishing
gApiKey = Removed
gBrowserKey  = Removed

print "Opening database.."
sqlWar = sqlite3.connect('warnings.db') #for warnings (bad if corrupted)
curWar = sqlWar.cursor()
curWar.execute("CREATE TABLE IF NOT EXISTS warnings(NAME TEXT, WARNINGS INTEGER)")
sqlWar.commit()

sql = sqlite3.connect('sql.db') #for everything else (doesn't matter too much if corrupted)
cur = sql.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS doneComments(ID TEXT)") 
cur.execute("CREATE TABLE IF NOT EXISTS donesubmissions(ID TEXT)")
sql.commit()

MODLIST = ['theonefoster', 'nvadergir', 'zimm3rmann', 'youngnreckless', 'mahi-mahi', 'asmr_bot', 'sidecarfour', 'harrietpotter']

VIEWEDMODQUEUE = []

BANNEDCHANNELS = [ Removed ]

METAEXPLAIN = """
Hey OP! This submission has been removed because it incorrectly uses a [meta] tag.

The [meta] tag is intended for posts which relate specifically to subjects concerning this subreddit, its rules, moderation, posts etc. Feel free to resubmit your post, but consider using [another more appropriate tag](https://www.reddit.com/r/asmr/wiki/index#wiki_tagging_system) to correctly label your post and make future searches easier.
"""

SBEXPLAIN = """
Hey OP! Unfortunately you appear to be [shadowbanned](https://www.reddit.com/r/AskReddit/comments/11ggji/can_someone_please_explain_to_me_what_shadow/) site-wide on reddit, meaning your comments and submissions are invisible to everyone except moderators. The most likely reason for this is posting many links to a single (usually your own) channel or website, which goes against [reddiquette](https://www.reddit.com/wiki/reddiquette) and is considered spamming, although there are other possible reasons. You can try [contacting reddit admins](https://www.reddit.com/message/compose?to=%2Fr%2Freddit.com) to see if they will reverse it - otherwise everything you post (including comments) will remain invisible to non-moderators. 

You can verify your shadowban by logging out and trying to view your userpage - if it says "page not found", you know that you've been shadowbanned. 

This is a site-wide ban implemented by the admins and outside the control of the moderators of /r/asmr. If you haven't already, it is recommended that you read up on [reddit's guidelines on self-promotion](https://www.reddit.com/wiki/selfpromotion) and the [spam FAQ](https://www.reddit.com/wiki/faq#wiki_what_constitutes_spam.3F) (it'll only take a few minutes!) Thanks for your interest!
"""

SBEXPLAIN_MSG = """
Hey! You are receiving this message because you just commented in /r/asmr, but unfortunately you appear to be [shadowbanned](https://www.reddit.com/r/AskReddit/comments/11ggji/can_someone_please_explain_to_me_what_shadow/) site-wide on reddit. The most likely reason for this is posting many links to a single (usually your own) channel or website, which goes against [reddiquette](https://www.reddit.com/wiki/reddiquette) and is considered spamming, although there are other possible reasons. You can try [contacting reddit admins](https://www.reddit.com/message/compose?to=%2Fr%2Freddit.com) to see if they will reverse it - otherwise everything you post (including comments and submissions) will remain invisible to non-moderators. 

You can verify your shadowban by logging out and trying to view your userpage - if it says "page not found", you know that you've been shadowbanned. 

This is a site-wide ban implemented by the admins and outside the control of the moderators of /r/asmr. If you haven't already, it is recommended that you read up on [reddit's guidelines on self-promotion](https://www.reddit.com/wiki/selfpromotion) and the [spam FAQ](https://www.reddit.com/wiki/faq#wiki_what_constitutes_spam.3F) (it'll only take a few minutes!) Thanks for your interest!
"""

MUSEXPLAIN = """
Hey OP! This submission has been removed because music submissions aren't allowed. The tingles associated with music are almost always **frisson**, not asmr, so links to music aren't allowed to avoid confusion. Try submitting at /r/frisson or /r/asmrmusic instead.

If you haven't already, have a read of our subreddit's [wiki page](/r/asmr/wiki) which details all of the submission rules and guidelines.

Thanks for your interest!

"""

TITLEEXPLAIN = """
Hey OP! This post has been removed because the title does not follow our guidelines (submission rule 7). This may because it looks clickbaity, or it may be because it does not describe the triggers present in the content you've linked to.

Remeber that the title should contain a description of the content and its triggers only, and that your own commentary or experiences of the content should go in the comments section.

Please read our guidelines at /r/asmr/wiki, especially submission rule 7, then feel free to resubmit. If you're still unsure why this was removed, feel free to [contact the mods.](https://www.reddit.com/message/compose?to=%2Fr%2Fasmr&subject=Removed post)
"""

BANNEDCHANNELCOMMENT = """
This submission has been removed because the youtube channel it links to is banned from this subreddit.
"""

TWOTAGSCOMMENT = """
This submission has been removed because the title contains two "flair tags". Each submission needs to contain exactly one flair tag in the title - no more, no fewer. This is so that your submission can be categorised correctly and given a flair. Your submission can (and should really) have as many other arbitrary tags as you like.

You should use exactly one flair tag from the list below to categorise your post:

[intentional]

[unintentional]

[article]

[question]

[discussion]

[media]

[meta]

Remember to try to use at least two other tags of your choice to describe the content. Things like articles and discussions generally don't need an extra tag, but triggering content usually does. For more information on this rule, see [the tags explanation on our wiki](https://www.reddit.com/r/asmr/wiki/index#wiki_tagging_system), then feel free to resubmit with a title which follows our guidelines.
"""

UNLISTEDCOMMENT = """
This submission has been removed because the video it links to is unlisted. Please respect the content creator by not posting private videos.
"""

def getYoutubeVideoTitleFromVideoID(videoID): #value is the type of info to return
    try:
        URL = ("https://www.googleapis.com/youtube/v3/videos?part=snippet&id=" + videoID + "&key=" + gBrowserKey)
        videoInfo = json.loads(urllib2.urlopen(URL).read())
        items = videoInfo[u'items']
        itemsDic = items[0]
        snippet = itemsDic[u'snippet']
        return snippet[u'title']
    except:
        return -1

def getYoutubeChannelNameFromVideoID(videoID): #value is the type of info to return
    try:
        URL = ("https://www.googleapis.com/youtube/v3/videos?part=snippet&id=" + videoID + "&key=" + gBrowserKey)
        videoInfo = json.loads(urllib2.urlopen(URL).read())
        items = videoInfo[u'items']
        itemsDic = items[0]
        snippet = itemsDic[u'snippet']
        rtnvalue = snippet[u'channelTitle']
        return rtnvalue
    except:
        return -1

def getYoutubeChannelIDFromVideoID(videoID): #value is the type of info to return
    try:
        URL = ("https://www.googleapis.com/youtube/v3/videos?part=snippet&id=" + videoID + "&key=" + gBrowserKey)
        videoInfo = json.loads(urllib2.urlopen(URL).read())
        items = videoInfo[u'items']
        itemsDic = items[0]
        snippet = itemsDic[u'snippet']
        return snippet[u'channelId']
    except:
        return -1

def getYoutubeChannelDescriptionFromName(ChannelName): #value is the type of info to return
    try:
        URL = ("https://www.googleapis.com/youtube/v3/channels?part=snippet&forUsername=" + ChannelName + "&key=" + gBrowserKey)
        videoInfo = json.loads(urllib2.urlopen(URL).read())
        items = videoInfo[u'items']
        itemsDic = items[0]
        snippet = itemsDic[u'snippet']
        description = snippet[u'description']
        return description
    except:
        return -1

def getYoutubeChannelDescriptionFromID(ChannelID): #value is the type of info to return
    try:
        URL = ("https://www.googleapis.com/youtube/v3/channels?part=snippet&id=" + ChannelID + "&key=" + gBrowserKey)
        videoInfo = json.loads(urllib2.urlopen(URL).read())
        items = videoInfo[u'items']
        itemsDic = items[0]
        snippet = itemsDic[u'snippet']
        description = snippet[u'description']
        return description
    except:
        return -1

def getSubscriberCountFromChannelName(ChannelName): #value is the type of info to return
    try:
        URL = ("https://www.googleapis.com/youtube/v3/channels?part=statistics&forUsername=" + ChannelName + "&key=" + gBrowserKey)
        videoInfo = json.loads(urllib2.urlopen(URL).read())
        items = videoInfo[u'items']
        itemsDic = items[0]
        statistics = itemsDic[u'statistics']
        subs = statistics[u'subscriberCount']
        return int(subs)
    except:
        return -1

def getChannelNameFromID(ID): #value is the type of info to return
    try:
        URL = ("https://www.googleapis.com/youtube/v3/channels?part=snippet&id=" + ID + "&key=" + gBrowserKey)
        videoInfo = json.loads(urllib2.urlopen(URL).read())
        items = videoInfo[u'items']
        itemsDic = items[0]
        snippet = itemsDic[u'snippet']
        title = snippet[u'title']
        return title
    except:
        return -1

def getSubscriberCountFromChannelID(ID): #value is the type of info to return
    try:
        URL = ("https://www.googleapis.com/youtube/v3/channels?part=statistics&id=" + ID + "&key=" + gBrowserKey)
        videoInfo = json.loads(urllib2.urlopen(URL).read())
        items = videoInfo[u'items']
        itemsDic = items[0]
        statistics = itemsDic[u'statistics']
        subs = statistics[u'subscriberCount']
        return int(subs)
    except:
        return -1

def getChannelCreationDateFromID(ID): #value is the type of info to return
    try:
        URL = ("https://www.googleapis.com/youtube/v3/channels?part=snippet&forUsername=" + ID + "&key=" + gBrowserKey)
        videoInfo = json.loads(urllib2.urlopen(URL).read())
        items = videoInfo[u'items']
        itemsDic = items[0]
        snippet = itemsDic[u'snippet']
        publishedDate = snippet[u'publishedAt']
        return publishedDate
    except:
        return -1

def videoIsUnlisted(ID): #value is the type of info to return
    try:
        URL = ("https://www.googleapis.com/youtube/v3/videos?part=status&id=" + ID + "&key=" + gBrowserKey)
        videoInfo = json.loads(urllib2.urlopen(URL).read())
        items = videoInfo[u'items']
        itemsDic = items[0]
        status = itemsDic[u'status']
        publishedDate = status[u'privacyStatus']
        return publishedDate == "unlisted"
    except:
        return False

def redditUserActiveEnoughForFlair(username):
    user = r.get_redditor(username) #TODO: build this

def asmrbot():
    #remove comments to see time taken for each function
    #starttime = time.time()
    #print "Start: " + str(starttime)
    parseComments()
    #print "Comments took: " + str(time.time()-starttime)
    #starttime = time.time()
    checkSubmissions()
    #print "Submissions took: " + str(time.time()-starttime)
    #starttime = time.time()
    #getTopSubmissions()
    replyToMessages()
    #print "Messages took: " + str(time.time()-starttime)
    #starttime = time.time()
    getModQueue()
    #print "Modqueue took: " + str(time.time()-starttime)
    #starttime = time.time()

def login():
    print ("logging in..")
    r = praw.Reddit(appUserAgent)
    r.set_oauth_app_info(appID,appSecret, appURI)
    r.refresh_access_information(appRefreshToken)
    print ("logged in as " + str(r.user.name))
    return r

def getModQueue():
       modqueue = r.get_mod_queue(subreddit="asmr")

       for item in modqueue:
           if item.fullname not in VIEWEDMODQUEUE:
               print("New modqueue item!")
               VIEWEDMODQUEUE.append(item.fullname)
               
               try:
                   user = r.get_redditor(item.author.name, fetch=True)
                #if user is shadowbanned the above will throw HTTPError (404). Can also 
                #throw 503 sometimes if reddit is busy, resulting in false positive. There 
                #doesn't seem to be a way to distinguish between them though :\
               except:
                   print ("Replying to shadowbanned user " + item.author.name)
               
                   if item.fullname.startswith("t3"):  #submission
                       item.add_comment(SBEXPLAIN).distinguish()
                       item.remove(False)
                   elif item.fullname.startswith("t1"): #comment
                       r.send_message(recipient=item.author, subject="Shadowban notification", message=SBEXPLAIN_MSG)
                       item.remove(False)
                   item.clicked = True
    
def parseComments():
    comments = subreddit.get_comments(limit=15) #sends request

    for comment in comments:
        cur.execute("SELECT * FROM doneComments WHERE ID=?", [comment.id])
        if not cur.fetchone():
            cur.execute("INSERT INTO doneComments VALUES(?)", [comment.id])
            try:
                commentAuthor = comment.author.name
                commentBody = comment.body.lower()

                #print ('Scanning new comment by ' + commentAuthor + '...')
                if (commentAuthor in MODLIST and commentAuthor != "asmr_bot"):
                    if ('!bot-met' in commentBody):
                        print ("Comment found! Replying to " + commentAuthor)
                        comment.remove(False)
                        submissionID = comment.parent_id
                        submission = r.get_submission(submission_id=submissionID[3:])
                        submission.add_comment(METAEXPLAIN).distinguish()
                        submission.remove(False)
                    elif ('!bot-mus' in commentBody):
                        print ("Comment found! Replying to " + commentAuthor)
                        comment.remove(False)
                        submissionID = comment.parent_id
                        submission = r.get_submission(submission_id=submissionID[3:])
                        TLcomment = submission.add_comment(MUSEXPLAIN).distinguish()
                        submission.remove(False)
                    elif ('!bot-title' in commentBody):
                        print ("Comment found! Replying to " + commentAuthor)
                        comment.remove(False)
                        submissionID = comment.parent_id
                        submission = r.get_submission(submission_id=submissionID[3:])
                        TLcomment = submission.add_comment(TITLEEXPLAIN).distinguish()
                        submission.remove(False)
                    elif ("bot-warning" in commentBody):
                        parent = r.get_info(thing_id=comment.parent_id)
                        addWarning(parent)
                        comment.remove(False)

            except AttributeError: # if comment has no author (is deleted) (comment.author.name returns AttributeError), do nothing
                 print "Attribute Error! Comment was probably deleted."

def checkSubmissions():
    submissions = subreddit.get_new(limit=15)

    for submission in submissions:
        cur.execute("SELECT * FROM doneSubmissions WHERE ID=?", [submission.id])
        if not cur.fetchone(): 
            cur.execute("INSERT INTO doneSubmissions VALUES(?)", [submission.id])
            
            #for each new submission..

            if(titleHasTwoTags(submission.title)):
                submission.add_comment(TWOTAGSCOMMENT).distinguish()
                submission.remove(False)
                print "Removed submission " + submission.ID + " for having two flair tags."
            elif ("youtube" in submission.url or "youtu.be" in submission.url) and (not "playlist" in submission.url) and (not "attribution_link" in submission.url):
                try:
                    result = vidIDregex.split(submission.url)
                    vidID = result[5]
                    channelID = getYoutubeChannelIDFromVideoID(vidID)
                    if channelID in BANNEDCHANNELS:
                        print "Removing submission " + submission.short_link + " (banned youtube channel).."
                        submission.add_comment(BANNEDCHANNELCOMMENT).distinguish()
                        submission.remove(False) #checks for banned youtube channels
                    elif videoIsUnlisted(vidID):
                        print "Removing submission " + submission.short_link + " (unlisted video).."
                        submission.add_comment(UNLISTEDCOMMENT).distinguish()
                        submission.remove(False)
                except Exception, e:
                    print "exception on removal of submission " + submission.short_link + " - " + str(e)

def titleHasTwoTags(title):
    twoTagsRegex = re.compile('.*\[(intentional|unintentional|media|article|discussion|question|meta)\].*\[(intentional|unintentional|media|article|discussion|question|meta)\].*', re.I)
    return (re.search(twoTagsRegex, title) != None) # search the title for two tags; if two are found return true, else return false

def updateTopSubmissions(): #updates recommendation database. Doesn't usually need to be run unless the data gets corrupt or the top submissions drastically change.
    submissions = subreddit.get_top_from_all(limit = 750)
    
    addedcount = 0
    totalcount = 0

    for submission in submissions:
        totalcount += 1
        print ("Got submission " + submission.id + "(" + str(totalcount) + ")")
        if (".youtube" in submission.url or "youtu.be" in submission.url) and (not "playlist" in submission.url) and (not "attribution_link" in submission.url):
                
            try:
                result = vidIDregex.split(submission.url)
                vidID = result[5]
                channelName = getYoutubeChannelNameFromVideoID(vidID)
                vidTitle = getYoutubeVideoTitleFromVideoID(vidID)
                if (channelName != -1) and (vidTitle != -1):
                    toplist[str(addedcount)] = {"URL" : submission.url, "Channel": channelName, "Title": vidTitle, "Reddit Link": submission.permalink}
                    addedcount += 1
                else:
                    print "hmm"
            except:
                print "Exception!"

    toplist.sync()
    print "total videos: " + str(addedcount) #471

def recommendTopSubmission():
    #updateTopSubmissions()

    rand = random.randint(1, 507)

    rtn = "How about [" + toplist[str(rand)]["Title"] + "](" + (toplist[str(rand)]["URL"]) + ") by " + toplist[str(rand)]["Channel"] + "? \n\n[(Reddit link)](" + toplist[str(rand)]["Reddit Link"] + ") \n\nIf you don't like this video, reply with ""!recommend"" and I'll find you another one."

    return filter(lambda x: x in string.printable, rtn) # removes stupid unicode characters

def replyToMessages():
    messages = r.get_unread(limit=20)

    for message in messages:
        if not message.was_comment:
            user = message.author.name

            print "Message dectected from " + user

            if ("!recommend" in message.body.lower()): #recommendation
                print "Recommending popular video"
                messageToSend = recommendTopSubmission()
                message.reply(messageToSend)
            elif(message.subject == "flair request" or message.subject == "re: flair request"): #set flair
            
                gotfromname = True
                channelName = message.body
                des = getYoutubeChannelDescriptionFromName(message.body)
            
                if des == -1:
                    des = getYoutubeChannelDescriptionFromID(message.body)
                    gotfromname = False
                    channelName = getChannelNameFromID(message.body)

                if des != -1:
                    if "hey /r/asmr mods!" in des.lower():

                        if gotfromname:
                            subs = getSubscriberCountFromChannelName(channelName)
                        else:
                            subs = getSubscriberCountFromChannelID(message.body)

                        if subs >= 1000:
                            if daysSinceYoutubeChannelCreation(channelName) > 182:

                                if getNumberOfVideosFromChannelName(channelName) >= 12:

                                    r.set_flair(subreddit="asmr", item=user, flair_text=channelName, flair_css_class="purpleflair")
                                    message.reply("Verification has been sucessful! Your flair should be applied within a few minutes. Please remember to remove the message from your channel description as soon as possible, otherwise somebody could steal your flair. Enjoy!")

                                    print "Verified and set flair!"
                                else:
                                    message.reply("Unfortunately your channel needs to have at least 12 published videos to be eligible for subreddit flair. Thanks for applying, and feel free to check back once you've published 12 videos.")
                                    print "flair verification for " + channelName + " failed - not enough published videos."
                            else:
                                message.reply("Unfortunately your channel needs to be at least 6 months (182 days) old to be eligible for subreddit flair. Thanks for applying, and feel free to check back when your channel is old enough!")
                                print "flair verification for " + channelName + " failed - channel too new."
                        else:
                            message.reply("Unfortunately you need to have 1000 youtube subscribers to be awarded with flair. You only have " + str(subs) + " at the momnent, but try again once you reach 1000!")
                            print "flair verification for " + channelName + " failed - not enough subs."
                    else:
                        message.reply("I couldn't see the verification message in your channel description. Please make sure you include the exact phrase '**Hey \\/r/asmr mods!**' (without the quotes) in your youtube channel description so I can verify that you really own that channel. You should remove the verification message as soon as you've been verified.")
                        print "flair verification for " + channelName + " failed - no verification message."
                else:
                    message.reply("""
Sorry, I couldn't find that channel. You can use either the channel name (eg 'asmrtess') or the channel ID (the messy part in the youtube link - go to your page and get just the ID from the URL in the format youtube.com/channel/<ID>, eg "UCb3fNzphmiwDgHO2Yg319uw"). Sending EITHER the username OR the ID will work. 
                
Please make sure the name is exactly correct. See [the wiki page](/r/asmr/wiki/flair_requests) for instructions. If you're still having problems, please [message the human mods](https://www.reddit.com/message/compose?to=%2Fr%2Fasmr)""")
                    print "flair verification failed - channel not found. Message was: " + message.body
            elif(message.subject == "delete flair"): #delete flair
                if message.body == "delete flair":
                    r.delete_flair(subreddit="asmr", user=user)
                    message.reply("Your flair has been deleted. To apply for flair again, use [this link.](https://www.reddit.com/message/compose?to=asmr_bot&subject=flair%20request&message=enter your channel name here)")
                    print "flair deleted"
            elif("post reply" not in message.subject) and ("comment reply" not in message.subject) and ("username mention" not in message.subject) and ("you've been banned from" not in message.subject):
                print "command not recognised."
                message.reply("Sorry, I don't recognise that command. If you're trying to request a flair, read [the instructions here](https://www.reddit.com/r/asmr/wiki/flair_requests). For other commands you can send me, read the [asmr_bot wiki page](https://www.reddit.com/r/asmr/wiki/asmr_bot). If you have any questions or feedback, please message /u/theonefoster.")
        message.mark_as_read()

def userIsActive(username):#TODO
    return True


def userIsShadowbanned(username):
    try:
        user = r.get_redditor(user_name)
        return False
    except:
        return True

def daysSinceYoutubeChannelCreation(name):
    creationDate = getChannelCreationDateFromID(name)
    if (creationDate <> -1):
        try:
            year = creationDate[0:4]
            month = creationDate[5:7]
            day = creationDate[8:10]

            channelDate = datetime.date(year=int(year),month=int(month),day=int(day))
            return datetime.datetime.today().toordinal() - channelDate.toordinal()

        except Exception,e:
            return -1
    else:
        return -1

def getNumberOfVideosFromChannelName(name):
    try:
        URL = ("https://www.googleapis.com/youtube/v3/channels?part=statistics&forUsername=" + name + "&key=" + gBrowserKey)
        videoInfo = json.loads(urllib2.urlopen(URL).read())
        items = videoInfo[u'items']
        itemsDic = items[0]
        statistics = itemsDic[u'statistics']
        numVids = statistics[u'videoCount']

        return int(numVids)
    except:
        return -1

def addWarning(post): #post is a reddit thing (comment or submission)
    user = post.author.name
    cardinal = "?" #just for printing to console

    curWar.execute("SELECT * FROM warnings WHERE name=?", [user])
    result = curWar.fetchone()
    
    if not result:
        curWar.execute("INSERT INTO warnings VALUES(?,?)", [user, 1])
        post.remove(False)
        note = "Auto-ban: first warning - " + post.permalink
        msg = "You have received an automatic warning ban because of your post [here](" + post.permalink + "). This is your first warning, which is accompanied by a 7-day ban. Please take 2 minutes to read [our subreddit rules](/r/asmr/wiki) before participating in the community again."
        subreddit.add_ban(post.author, duration=7, note=note, ban_message=msg)
        cardinal = "First"
    elif result[1] >= 2: 
        curWar.execute("DELETE FROM warnings WHERE name=?", [user])
        curWar.execute("INSERT INTO warnings VALUES(?,?)",  [user, 3])
        post.remove(False)
        note = "Auto-ban: Permanent - " + post.permalink
        msg = "You been automatically banned because of your post [here](" + post.permalink + "). This is your third warning, meaning you are now permanently banned."
        subreddit.add_ban(post.author, note=note, ban_message=msg)
        cardinal = "Third"
    elif result[1] == 1:
        curWar.execute("DELETE FROM warnings WHERE name=?", [user])
        curWar.execute("INSERT INTO warnings VALUES(?,?)",  [user, 2])
        post.remove(False)
        note = "Auto-ban: Final warning - " + post.permalink
        msg = "You have received an automatic warning ban because of your post [here](" + post.permalink + "). **This is your final warning**. You will be banned for the next 30 days; if you receive another warning, you will be permanently banned. Please take 2 minutes to read [our subreddit rules](/r/asmr/wiki) before participating in the community again."
        subreddit.add_ban(post.author, duration=30, note=note, ban_message=msg)
        cardinal = "Second"
    sqlWar.commit()
    print cardinal + " warning added for " + user

#----------------------------------------------------
#----------------------------------------------------
#----------------------------------------------------

r = login()
subreddit = r.get_subreddit("asmr")

while True:
    try:
        asmrbot()
        sql.commit()
        r.handler.clear_cache()
        time.sleep(5)
    except Exception,e:
        print str(e)
        try:
            r = login()
            
        except Exception,f:
            print str(f)
            print ("Sleeping..")
            time.sleep(60) #usually rate limits or 503. 
    
