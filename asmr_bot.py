# asmr_bot
A bot to assist in the moderation or /r/asmr on reddit

#using /u/asmr_bot 

import praw
import pickle
import time
import gdata.youtube
import urllib2
import json
import sqlite3
import re
import random
import shelve
import string # <- it's stupid that I need to do this.


print "Opening database.."
sql = sqlite3.connect('sql.db')
cur = sql.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS doneComments(ID TEXT)")
cur.execute("CREATE TABLE IF NOT EXISTS donesubmissions(ID TEXT)")
sql.commit()


MODLIST = ['theonefoster', 'nvadergir', 'zimm3rmann', 'youngnreckless', 'mahi-mahi', "asmr_bot", "sidecarfour", "harrietpotter"]

VIEWEDMODQUEUE = []

BANNEDCHANNELS = [
    'UC_Jm39jFO9cH8KB9GIW54kg' # "ASMR Casual" / "letsASMR" - for faking giveaways, vote manipulation, commenting on own submissions
    ]

METAEXPLAIN = """
Hey OP! This submission has been removed because it incorrectly uses a [meta] tag.

The [meta] tag is intended for posts which relate specifically to subjects concerning this subreddit, its rules, moderation, posts etc. Feel free to resubmit your post, but consider using [another more appropriate tag](https://www.reddit.com/r/asmr/wiki/index#wiki_tagging_system) to correctly label your post and make future searches easier.
"""

SBEXPLAIN = """
Hey OP! Unfortunately you appear to be [shadowbanned](https://www.reddit.com/r/AskReddit/comments/11ggji/can_someone_please_explain_to_me_what_shadow/) site-wide on reddit. The most likely reason for this is posting many links to a single (usually your own) channel or website, which goes against [reddiquette](https://www.reddit.com/wiki/reddiquette) and is considered spamming, although there are other possible reasons. You can try [contacting reddit admins](https://www.reddit.com/message/compose?to=%2Fr%2Freddit.com) to see if they will reverse it - otherwise everything you post (including comments) will remain invisible to non-moderators. 

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
Hey OP! This post has been removed because the title does not follow our guidelines (submission rule 7). This may because it looks clickbaity, or because it does not describe the triggers present in the content you've linked to.

Remeber that the title should contain a description of the content and its triggers only, and that your own commentary or experiences of the content should go in the comments section.

Please read our guidelines at /r/asmr/wiki, especially submission rule 7, then feel free to resubmit.
"""

BANNEDCHANNELCOMMENT = """
This submission has been removed because the youtube channel it links to is banned from this subreddit.
"""

def getYoutubeData(input,part,val): #input = search value, part=where to search, val=return value
     #use this to replace the many functions below.
     #part should be either snippet or statistics.
     #TODO: finish this and test it
     URL = ("https://www.googleapis.com/youtube/v3/videos?part=" & part & "&id=" + input + "&key=" + gBrowserKey)
     videoInfo = json.loads(urllib2.urlopen(URL).read())
     items = videoInfo[u'items']
     itemsDic = items[0]
     rtndic = itemsDic[val] #does this work? Might need the u

     #TODO JUST PUT THE JSON DICTIONARY INTO A GLOBAL VARIABLE OFC
     
     #when I start a comment it looks like a hastag #TODO #input #yolo

     return -1

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
    
        #if value == "ID":
        rtnvalue = snippet[u'channelTitle']
        #elif value == "NAME":
        #    rtnvalue = snippet[u'channelTitle']
        #elif value == "TITLE":
        #    rtnvalue = snippet[u'title']
        #else:
        #    return ""

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

        return subs
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

        return subs
    except:
        return -1

def redditUserActiveEnoughForFlair(username):
    user = r.get_redditor(username) #TODO: build this

def asmrbot():
    parseComments()
    checkChannel()    
    #getTopSubmissions()
    replyToMessages()
    getModQueue()

def login():
    print ("logging in..")
    r = praw.Reddit(appUserAgent)
    r.set_oauth_app_info(appID,appSecret, appURI)
    r.refresh_access_information(appRefreshToken)
    print ("logged in as " + str(r.user.name))
    return r

def getModQueue():
       modqueue = r.get_mod_queue(subreddit="asmr", fetch=True)

       for item in modqueue:
           if item.fullname not in VIEWEDMODQUEUE:
               print("New modqueue item!")
               VIEWEDMODQUEUE.append(item.fullname)
               
               try:
                   user = r.get_redditor(item.author.name, fetch=True)
               except: #if user is shadowbanned the above will throw HTTPError (404)
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
            sql.commit()
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
                    elif ('!bot-sb' in commentBody):
                        print ("Comment found! Replying to " + commentAuthor)
                        comment.remove(False)
                        submissionID = comment.parent_id
                        submission = r.get_submission(submission_id=submissionID[3:])
                        TLcomment = submission.add_comment(SBEXPLAIN).distinguish()
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

            except AttributeError: # if comment has no author (is deleted) (comment.author.name returns AttributeError), do nothing
                 print "Attribute Error! Comment was probably deleted."

def checkChannel():
    submissions = subreddit.get_new(limit=15)

    for submission in submissions:
        cur.execute("SELECT * FROM doneSubmissions WHERE ID=?", [submission.id])
        if not cur.fetchone(): 
            cur.execute("INSERT INTO doneSubmissions VALUES(?)", [submission.id])
            sql.commit()
            
            #for each new submission..

            if ("youtube" in submission.url or "youtu.be" in submission.url) and (not "playlist" in submission.url) and (not "attribution_link" in submission.url):
                try:
                    result = vidIDregex.split(submission.url)
                    vidID = result[5]
                    channelID = getYoutubeChannelIDFromVideoID(vidID)
                    if channelID in BANNEDCHANNELS:
                        print "Removing submission "# & submission.permalink & " (banned youtube channel).."
                        submission.add_comment(BANNEDCHANNELCOMMENT).distinguish()
                        submission.remove(False) #checks for banned youtube channels
                except Exception, e:
                    print "exception on removal of submission " & submission.short_link & " - " & str(e)

def getTopSubmissions():
#    submissions = subreddit.get_top_from_all(limit = 750)
#    
#    addedcount = 0  ###### REMOVE COMMENTS AND RUN TO UPDATE DB
#    totalcount = 0
#
#    for submission in submissions:
#        totalcount += 1
#        print ("Got submission " + submission.id + "(" + str(totalcount) + ")")
#        if (".youtube" in submission.url or "youtu.be" in submission.url) and (not "playlist" in submission.url) and (not "attribution_link" in submission.url):
#                
#            try:
#                result = vidIDregex.split(submission.url)
#                vidID = result[5]
#                channelName = getYoutubeChannelNameFromVideoID(vidID)
#                vidTitle = getYoutubeVideoTitleFromVideoID(vidID)
#                if (channelName != -1) and (vidTitle != -1):
#                    toplist[str(addedcount)] = {"URL" : submission.url, "Channel": channelName, "Title": vidTitle, "Reddit Link": submission.permalink }
#                    addedcount += 1
#                else:
#                    print "hmm"
#            except:
#                print "Exception!"

#    toplist.sync()
#    print "total videos: " + str(addedcount) #471

    rand = random.randint(1, 507)

    rtn = "How about [" + toplist[str(rand)]["Title"] + "](" + (toplist[str(rand)]["URL"]) + ") by " + toplist[str(rand)]["Channel"] + "? \n\n[(Reddit link)](" + toplist[str(rand)]["Reddit Link"] + ") \n\nIf you don't like this video, reply with ""!recommend"" and I'll find you another one."

    return filter(lambda x: x in string.printable, rtn) # removes stupid unicode characters

def replyToMessages():
    messages = r.get_unread()

    for message in messages:
        if not message.was_comment:
            user = message.author.name

            print "Message dectected from " + user

            if ("!recommend" in message.body.lower()): #recommendation
                print "Recommending popular video"
                messageToSend = getTopSubmissions()
                message.reply(messageToSend)
            elif(message.subject == "flair request" or message.subject == "re: flair request"): #set flair
            
                gotfromname = True
                des = getYoutubeChannelDescriptionFromName(message.body)
            
                if des == -1:
                    des = getYoutubeChannelDescriptionFromID(message.body)
                    gotfromname = False

                if des != -1:
                    description = des.lower()
                    if "hey /r/asmr mods!" in description:
                        if gotfromname:
                            subs = getSubscriberCountFromChannelName(message.body.lower())
                        else:
                            subs = getSubscriberCountFromChannelID(message.body)

                        if int(subs) >= 1000:
                            if gotfromname:
                                r.set_flair(subreddit="asmr", item=user, flair_text=message.body, flair_css_class="purpleflair")
                            else:
                                name = getChannelNameFromID(message.body)
                                r.set_flair(subreddit="asmr", item=user, flair_text=name, flair_css_class="purpleflair")

                            message.reply("Verification has been sucessful! Your flair should be applied within a few minutes. Please remember to remove the message from your channel description as soon as possible, otherwise somebody could steal your flair. Enjoy!")
                            print "Verified and set flair!"
                        else:
                            message.reply("Unfortunately you need to have 1000 youtube subscribers to be awarded with flair. You only have " + str(subs) + " at the momnent, but try again once you reach 1000!")
                            print "flair verification failed - not enough subs"
                    else:
                        message.reply("I couldn't see the verification message in your channel description. Please make sure you include the exact phrase '**Hey \\/r/asmr mods!**' in your youtube channel description so I can verify that you own that channel. You should remove the verification message once you're verified.")
                        print "flair verification failed - no verification message"
                else:
                    message.reply("""
    Sorry, I couldn't find that channel. You can use either the channel name (eg 'asmrtess') or the channel ID (the messy part in the youtube link - go to your page and get just the ID from the URL in the format youtube.com/channel/<ID>). Sending either the username OR the ID should work. 
                
    Please make sure the name is exactly correct. See [the wiki page](/r/asmr/wiki/flair_requests) for instructions. If you're still having problems, please [message the human mods](https://www.reddit.com/message/compose?to=%2Fr%2Fasmr)""")
                    print "flair verification failed - channel not found"
            elif(message.subject == "delete flair"): #delete flair
                if message.body == "delete flair":
                    r.delete_flair(subreddit="asmr", user=user)
                    message.reply("Your flair has been deleted. To apply for flair again, use [this link.](https://www.reddit.com/message/compose?to=asmr_bot&subject=flair%20request&message=enter your channel name here)")
                    print "flair deleted"
            elif("post reply" not in message.subject) and ("comment reply" not in message.subject) and ("username mention" not in message.subject) and ("you've been banned from" not in message.subject):
                print "command not recognised."
                message.reply("Sorry - I don't recognise that command.If you have any feedback, please message /u/theonefoster.")
        message.mark_as_read()

def userIsActive(username):#TODO
    return True


def userIsShadowbanned(username):
    try:
        user = r.get_redditor(user_name)
        return False
    except:
        return True

r = login()
subreddit = r.get_subreddit("asmr")

while True:
    try:
        asmrbot()
        time.sleep(10)
        r.handler.clear_cache() 
    except Exception,e:
        print str(e)
        try:
            r = login()
            
        except Exception,f:
            print str(f)
            print ("Sleeping..")
            time.sleep(120)
    
