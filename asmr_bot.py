# for /u/asmr_bot 

import praw
import time
import datetime
import sqlite3
import re
import random
import shelve
import string
import requests
import traceback

import schedule

import asmr_bot_data as d #d for data

# PRAW details
appUserAgent = d.appUserAgent
appID = d.appID
appSecret = d.appSecret
appURI = d.appURI
appRefreshToken = d.appRefreshToken
changed = True
vidIDregex = re.compile('(youtu\.be\/|youtube\.com\/(watch\?(.*&)?v=|(embed|v)\/))([^\?&\"\'>]+)')
toplist = shelve.open("topPosts",'c')

# gdata details
gApiKey = d.gApiKey
gBrowserKey  = d.gBrowserKey

# global variables
MODLIST = ['theonefoster', 'nvadergir', 'zimm3rmann', 'youngnreckless', 'mahi-mahi', 'asmr_bot', 'sidecarfour', 'harrietpotter']
VIEWEDMODQUEUE = []
BadTitlePhrases = d.BadTitlePhrases
BANNEDCHANNELS = d.BANNEDCHANNELS

# Messages
METAEXPLAIN = d.METAEXPLAIN
SBEXPLAIN = d.SBEXPLAIN
SBEXPLAIN_MSG = d.SBEXPLAIN_MSG
MUSEXPLAIN = d.MUSEXPLAIN
TITLEEXPLAIN = d.TITLEEXPLAIN
BANNEDCHANNELCOMMENT = d.BANNEDCHANNELCOMMENT
TWOTAGSCOMMENT = d.TWOTAGSCOMMENT
BANNEDCHANNELCOMMENT = d.BANNEDCHANNELCOMMENT
BADTITLECOMMENT = d.BADTITLECOMMENT
UNLISTEDCOMMENT = d.UNLISTEDCOMMENT

# Open sql databases
print("Opening databases..")
sqlWar = sqlite3.connect('warnings.db') # for warnings database (bad if corrupted)
curWar = sqlWar.cursor()
curWar.execute("CREATE TABLE IF NOT EXISTS warnings(NAME TEXT, WARNINGS INTEGER)")
sqlWar.commit()

sql = sqlite3.connect('sql.db') # for everything else (doesn't matter too much if corrupted)
cur = sql.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS doneComments(ID TEXT)") 
cur.execute("CREATE TABLE IF NOT EXISTS donesubmissions(ID TEXT)")
sql.commit()

def getYoutubeVideoData(location, part, input_type, input_val, return_val):

    # read like "from LOCATION, get the PART where INPUT_TYPE is INPUT_VAL and return RETURN_VAL
    # where location is channel/video, part is statistics/snippet/status, type is ID or fromUsername, val is the search value, return value is the data you want
     
    input_val = input_val.replace(" ", "") # remove spaces (http doesn't like spaces, and it works fine without them eg usernames don't have spaces but people think they do: "CGP Grey" is really "cgpgrey")

    try:
        URL = ("https://www.googleapis.com/youtube/v3/" + location + "?part=" + part + "&" + input_type + "=" + input_val + "&key=" + gBrowserKey)
        response = requests.get(URL).json()
        items = response[u'items']
        snippet = items[0][part]
        rtn = snippet[return_val]
        return rtn
    except Exception as e:
        #traceback.print_exc()
        return -1

def daysSinceYoutubeChannelCreation(channelName):
    creationDate = getYoutubeVideoData("channels", "snippet", "forUsername", channelName, "publishedAt")
    if (creationDate != -1):
        try:
            year = creationDate[0:4]
            month = creationDate[5:7]
            day = creationDate[8:10]

            channelDate = datetime.date(year=int(year),month=int(month),day=int(day))
            return datetime.datetime.today().toordinal() - channelDate.toordinal()
        except Exception as e:
            return -1
    else:
        return -1

def daysSinceYoutubeChannelCreationFromID(channelID):
    creationDate = getYoutubeVideoData("channels", "snippet", "id", channelID, "publishedAt")
    if (creationDate != -1):
        try:
            year = creationDate[0:4]
            month = creationDate[5:7]
            day = creationDate[8:10]

            channelDate = datetime.date(year=int(year),month=int(month),day=int(day))
            return datetime.datetime.today().toordinal() - channelDate.toordinal()
        except Exception as e:
            return -1
    else:
        return -1

def videoIsUnlisted(ID):
    return getYoutubeVideoData("videos", "status", "id", ID, "privacyStatus") == "unlisted"

def redditUserActiveEnoughForFlair(username):
    user = r.get_redditor(username)

def checkModQueue():
       modqueue = r.get_mod_queue(subreddit="asmr")

       for item in modqueue:
           if item.fullname not in VIEWEDMODQUEUE:
               print("New modqueue item!")
               VIEWEDMODQUEUE.append(item.fullname)

               useless_report = True
               p = ""

               for report in item.user_reports:
                   if item.fullname.startswith("t1") or not (report[0] is None or report[0] == "Spam" or "own content" in report[0] or "self promotion" in report[0] or "self-promotion" in report[0]): #report is None if no reason given
                       useless_report = False
                       p = report[0]
               #if useless_report:
                   #item.clicked = True
                   #item.approve()
                   #print("Item approved - ignored \"own content\"/spam/blank report. (Reason: '" + p + "')")
               if userIsShadowbanned(item.author.name): #was elif, see comment above
                   print("Replying to shadowbanned user " + item.author.name)
               
                   if item.fullname.startswith("t3"):  # submission
                       item.remove(False)
                       item.add_comment(SBEXPLAIN).distinguish()
                   elif item.fullname.startswith("t1"): # comment
                       item.remove(False)
                       r.send_message(recipient=item.author, subject="Shadowban notification", message=SBEXPLAIN_MSG)
                   item.clicked = True

def checkComments():
    comments = subreddit.get_comments(limit=15) # sends request

    for comment in comments:
        cur.execute("SELECT * FROM doneComments WHERE ID=?", [comment.id])
        if not cur.fetchone():
            cur.execute("INSERT INTO doneComments VALUES(?)", [comment.id])
            try:
                commentAuthor = comment.author.name.lower()
                commentBody = comment.body.lower()

                if (commentAuthor in MODLIST and commentAuthor != "asmr_bot"):
                    if ('!bot-met' in commentBody):
                        print("Comment found! Replying to " + commentAuthor + " (bad meta post)")
                        comment.remove(False)
                        submissionID = comment.parent_id
                        submission = r.get_submission(submission_id=submissionID[3:])
                        submission.remove(False)
                        submission.add_comment(METAEXPLAIN).distinguish()
                    elif ('!bot-mus' in commentBody):
                        print("Comment found! Replying to " + commentAuthor + " (music)")
                        comment.remove(False)
                        submissionID = comment.parent_id
                        submission = r.get_submission(submission_id=submissionID[3:])
                        submission.remove(False)
                        TLcomment = submission.add_comment(MUSEXPLAIN).distinguish()
                    elif ('!bot-title' in commentBody):
                        print("Comment found! Replying to " + commentAuthor + " (bad title)")
                        comment.remove(False)
                        submissionID = comment.parent_id
                        submission = r.get_submission(submission_id=submissionID[3:])
                        submission.remove(False)
                        TLcomment = submission.add_comment(TITLEEXPLAIN).distinguish()
                    elif ("!bot-warning" in commentBody):
                        print("Comment found! Replying to " + commentAuthor + " (add warning)")
                        comment.remove(False)
                        parent = r.get_info(thing_id=comment.parent_id)
                        addWarning(parent)
                    elif("!bot-purge" in commentBody):
                        print("Comment found! Replying to " + commentAuthor + " (kill thread)")
                        try:
                            parent = r.get_info(thing_id=comment.parent_id)
                            if parent.fullname.startswith("t1"):# TODO - this isn't necessary I think
                                parent = getCommentFromSubmission(parent)
                                purgeThread(parent)
                            else:
                                comment.remove(False)
                                r.send_message(commentAuthor, "Failed command", "The !bot-purge command can only be used in reply to a top-level comment. This is due to reddit API restrictions.") #todo: wat
                        except Exception as e:
                            print("Exception when purging comment tree. Parent was " + parent.id)
                            traceback.print_exc()
                            r.send_message(commentAuthor, "Failed command", "Your purge command failed for an unknown reason. Your comment was removed.")
                        finally:
                            comment.remove(False)

            except AttributeError: # if comment has no author (is deleted) (comment.author.name returns AttributeError), do nothing
                print("Attribute Error! Comment was probably deleted.")
                traceback.print_exc()

def checkSubmissions():
    submissions = subreddit.get_new(limit=15)

    for submission in submissions:
        cur.execute("SELECT * FROM doneSubmissions WHERE ID=?", [submission.id])
        if not cur.fetchone(): 
            cur.execute("INSERT INTO doneSubmissions VALUES(?)", [submission.id])
            
            # for each new submission..
            if(titleHasTwoTags(submission.title)):
                submission.remove(False)
                submission.add_comment(TWOTAGSCOMMENT).distinguish()
                print("Removed submission " + submission.id + " for having two flair tags.")
            elif isBadTitle(submission.title):
                submission.remove(False)
                submission.add_comment(BADTITLECOMMENT).distinguish()
                r.send_message("theonefoster", "Bad Title - Submission removed", submission.permalink + "\n\nTitle was: \"**" + submission.title + "**\"")
                print("Removed submission " + submission.id + " for having a bad title.")
            elif ("youtube" in submission.url or "youtu.be" in submission.url) and (not "playlist" in submission.url) and (not "attribution_link" in submission.url):
                try:
                    result = vidIDregex.split(submission.url)
                    vidID = result[5]
                    channelID = getYoutubeVideoData("videos", "snippet", "id", vidID, "channelId")
                    if channelID in BANNEDCHANNELS:
                        submission.remove(False) # checks for banned youtube channels
                        submission.add_comment(BANNEDCHANNELCOMMENT).distinguish()
                        print("Removing submission " + submission.short_link + " (banned youtube channel)..")
                    elif videoIsUnlisted(vidID):
                        submission.remove(False)
                        submission.add_comment(UNLISTEDCOMMENT).distinguish()
                        print("Removing submission " + submission.short_link + " (unlisted video)..")
                except Exception as e:
                    print("exception on removal of submission " + submission.short_link + " - " + str(e))
                    traceback.print_exc()

def titleHasTwoTags(title):
    twoTagsRegex = re.compile('.*\[(intentional|unintentional|media|article|discussion|question|meta)\].*\[(intentional|unintentional|media|article|discussion|question|meta)\].*', re.I)
    return (re.search(twoTagsRegex, title) != None) # search the title for two tags; if two are found return true, else return false

def updateTopSubmissions(): # updates recommendation database. Doesn't usually need to be run unless the data gets corrupt or the top submissions drastically change.
    submissions = subreddit.get_top_from_all(limit = 750)
    addedcount = 0
    totalcount = 0

    for submission in submissions:
        totalcount += 1
        print("Got submission " + submission.id + "(" + str(totalcount) + ")")
        if (".youtube" in submission.url or "youtu.be" in submission.url) and (not "playlist" in submission.url) and (not "attribution_link" in submission.url):
            try:
                result = vidIDregex.split(submission.url)
                vidID = result[5]
                channelName = getYoutubeVideoData("videos", "snippet", "id", vidID, "channelTitle")
                vidTitle = getYoutubeVideoData("videos", "snippet", "id", vidID, "title")
                if (channelName != -1) and (vidTitle != -1):
                    toplist[str(addedcount)] = {"URL" : submission.url, "Channel": channelName, "Title": vidTitle, "Reddit Link": submission.permalink}
                    addedcount += 1
                else:
                    print("Youtube Exception. Bad link?")
            except Exception as e:
                print("Other exception - " + str(e))
                traceback.print_exc()

    toplist.sync()
    print("total videos: " + str(addedcount)) # 471

def recommendTopSubmission():
    # updateTopSubmissions() # uncomment this line and run to update database. Or just call the function somewhere.
    rand = random.randint(1, 518)
    rtn = "How about [" + toplist[str(rand)]["Title"] + "](" + (toplist[str(rand)]["URL"]) + ") by " + toplist[str(rand)]["Channel"] + "? \n\n[(Reddit link)](" + toplist[str(rand)]["Reddit Link"] + ") \n\nIf you don't like this video, reply with ""!recommend"" and I'll find you another one."

    return ''.join(char for char in rtn if char in string.printable) # removes stupid unicode characters

def replyToMessages():
    messages = r.get_unread(limit=100)

    for message in messages:
        if not message.was_comment:
            user = message.author.name
            print("Message dectected from " + user)

            if ("!recommend" in message.body.lower()): # recommendation
                print("Recommending popular video")
                messageToSend = recommendTopSubmission()
                message.reply(messageToSend)
            elif(message.subject == "flair request" or message.subject == "re: flair request"): # set flair

                gotFromID = False
                channelName = message.body
                des = getYoutubeVideoData("channels", "snippet", "forUsername", channelName, "description") # des as in description #tested
            
                if des == -1:
                    des = getYoutubeVideoData("channels", "snippet", "id", message.body, "description")
                    channelName = getYoutubeVideoData("channels", "snippet", "id", message.body, "title")
                    gotFromID = True

                if des != -1:
                    if "hey /r/asmr mods!" in des.lower():
                        if gotFromID:
                            subs = int(getYoutubeVideoData("channels", "statistics", "id", message.body, "subscriberCount"))
                        else:
                            subs = int(getYoutubeVideoData("channels", "statistics", "forUsername", channelName, "subscriberCount"))

                        if subs >= 1000:
                            if gotFromID:
                                age = daysSinceYoutubeChannelCreationFromID(message.body)
                            else:
                                age = daysSinceYoutubeChannelCreation(channelName)

                            if age > 182:

                                if gotFromID:
                                    videoCount = int(getYoutubeVideoData("channels", "statistics", "id", message.body, "videoCount"))
                                else:
                                    videoCount = int(getYoutubeVideoData("channels", "statistics", "forUsername", channelName, "videoCount"))

                                if videoCount >= 12:
                                    r.set_flair(subreddit="asmr", item=user, flair_text=channelName, flair_css_class="purpleflair")
                                    message.reply("Verification has been sucessful! Your flair should be applied within a few minutes, but it can sometimes take up to an hour depending on how slow reddit is being today. Please remember to remove the message from your channel description as soon as possible, otherwise somebody could steal your flair. Enjoy!")
                                    print("Verified and set flair for " + user)
                                else:
                                    message.reply("Unfortunately your channel needs to have at least 12 published videos to be eligible for subreddit flair, but you've only published " + str(videoCount) + " so far. Thanks for applying though, and feel free to check back once you've published 12 videos.")
                                    print("flair verification for " + channelName + " failed - not enough published videos.")
                            else:
                                message.reply("Unfortunately your channel needs to be at least 6 months (182 days) old to be eligible for subreddit flair. Thanks for applying, and feel free to check back when your channel is old enough!")
                                print("flair verification for " + channelName + " failed - channel too new.")
                        else:
                            message.reply("Unfortunately you need to have 1000 youtube subscribers to be awarded with flair. You only have " + str(subs) + " at the moment, but try again once you reach 1000!")
                            print("flair verification for " + channelName + " failed - not enough subs.")
                    else:
                        message.reply("I couldn't see the verification message in your channel description. Please make sure you include the exact phrase '**Hey \\/r/asmr mods!**' (without the quotes) in your youtube channel description so I can verify that you really own that channel. You should remove the verification message as soon as you've been verified.")
                        print("flair verification for " + channelName + " failed - no verification message.")
                else:
                    message.reply("""
Sorry, I couldn't find that channel. You can use either the channel name (eg 'asmrtess') or the channel ID (the messy part in the youtube link - go to your page and get just the ID from the URL in the format youtube.com/channel/<ID>, eg "UCb3fNzphmiwDgHO2Yg319uw"). Sending EITHER the username OR the ID will work. 
                
Please make sure the name is exactly correct. See [the wiki page](/r/asmr/wiki/flair_requests) for instructions. If you're still having problems, please [message the human mods](https://www.reddit.com/message/compose?to=%2Fr%2Fasmr)""")
                    print("flair verification failed - channel not found. Message was: " + message.body)
            elif(message.subject == "delete flair"): # delete flair
                if message.body == "delete flair":
                    r.delete_flair(subreddit="asmr", user=user)
                    message.reply("Your flair has been deleted. To apply for flair again, use [this link.](https://www.reddit.com/message/compose?to=asmr_bot&subject=flair%20request&message=enter your channel name here)")
                    print("Flair deleted for " + user)
            elif("post reply" not in message.subject) and ("comment reply" not in message.subject) and ("username mention" not in message.subject) and ("you've been banned from" not in message.subject):
                print("Command not recognised. Message was " + message.body)
                message.reply("Sorry, I don't recognise that command. If you're trying to request a flair, read [the instructions here](https://www.reddit.com/r/asmr/wiki/flair_requests). For other commands you can send me, read the [asmr_bot wiki page](https://www.reddit.com/r/asmr/wiki/asmr_bot). If you have any questions or feedback, please message /u/theonefoster.")
        message.mark_as_read()

def userIsActive(username):# TODO
    return True

def userIsShadowbanned(username):
    try:
        user = r.get_redditor(user_name=username, fetch=True)
        return False
    except praw.errors.HTTPException:
        return True
    except Exception as e:
        print("Unknown exception when checking shadowban for user " + username + " - exception code: \"" + str(e) + "\"")
        traceback.print_exc()
        return False

def addWarning(post): # post is a reddit 'thing' (comment or submission)
    user = post.author.name
    ordinal = "?"
    # curWar.execute("DELETE FROM warnings WHERE name=?", [user])
    # sqlWar.commit()
    # print "deleted."
    # time.sleep(10000)

    curWar.execute("SELECT * FROM warnings WHERE name=?", [user])
    result = curWar.fetchone()
    
    if not result:
        post.remove(False)
        curWar.execute("INSERT INTO warnings VALUES(?,?)", [user, 1])
        note = "Auto-ban: first warning - " + post.permalink
        msg = "You have received an automatic warning ban because of your post [here](" + post.permalink + "). This is your first warning, which is accompanied by a 7-day ban. Please take 2 minutes to read [our subreddit rules](/r/asmr/wiki) before participating in the community again."
        subreddit.add_ban(post.author, duration=7, note=note, ban_message=msg)
        ordinal = "First"
    elif result[1] >= 2: 
        post.remove(False)
        curWar.execute("DELETE FROM warnings WHERE name=?", [user])
        curWar.execute("INSERT INTO warnings VALUES(?,?)",  [user, 3])
        note = "Auto-ban: Permanent - " + post.permalink
        msg = "You have been automatically banned because of your post [here](" + post.permalink + "). This is your third warning, meaning you are now permanently banned."
        subreddit.add_ban(post.author, note=note, ban_message=msg)
        ordinal = "Third"
    elif result[1] == 1:
        post.remove(False)
        curWar.execute("DELETE FROM warnings WHERE name=?", [user])
        curWar.execute("INSERT INTO warnings VALUES(?,?)",  [user, 2])
        note = "Auto-ban: Final warning - " + post.permalink
        msg = "You have received an automatic warning ban because of your post [here](" + post.permalink + "). **This is your final warning**. You will be banned for the next 30 days; if you receive another warning, you will be permanently banned. Please take 2 minutes to read [our subreddit rules](/r/asmr/wiki) before participating in the community again."
        subreddit.add_ban(post.author, duration=30, note=note, ban_message=msg)
        ordinal = "Second"
    sqlWar.commit()
    print(ordinal + " warning added for " + user)

def isBadTitle(title):
    title = title.lower()
    if ("[intentional]" in title or "[unintentional]" in title):
        for phrase in BadTitlePhrases:
            if phrase in title:
                return True
    return False

def purgeThread(comment): # yay recursion woop woop
    for c in comment.replies:
        purgeThread(c)
        c.remove(False)
    comment.remove(False)

def getCommentFromSubmission(comment): # it's completely fucking dumb that I have to do this
    s = comment.submission
    i = comment.id
    for c in s.comments:
        if c.id == i:
            return c
    return None

def login():
    print("logging in..")
    r = praw.Reddit(appUserAgent, disable_update_check=True)
    r.set_oauth_app_info(appID,appSecret, appURI)
    r.refresh_access_information(appRefreshToken)
    print("logged in as " + str(r.user.name))
    return r

def removeSticky():
    sticky = subreddit.get_sticky()
    if "Free-For-All Friday" in sticky.title:
        sticky.unsticky()
    else:
        try:
            sticky = subreddit.get_sticky(bottom=True)
            if "Free-For-All Friday" in sticky.title:
                sticky.unsticky()
        except praw.errors.HTTPException as e: # if there's no bottom sticky it'll throw a 404 Not Found
            pass

def asmrbot():
    # starttime = time.time()
    # print "Start: " + str(starttime)
    checkComments()
    # print "Comments took: " + str(time.time()-starttime)
    # starttime = time.time()
    checkSubmissions()
    # print "Submissions took: " + str(time.time()-starttime)
    # starttime = time.time()
    # getTopSubmissions()
    replyToMessages()
    # print "Messages took: " + str(time.time()-starttime)
    # starttime = time.time()
    checkModQueue()
    # print "Modqueue took: " + str(time.time()-starttime)
    # starttime = time.time()
    schedule.run_pending()

# ----------------------------------------------------
# ----------------------------------------------------

r = login()
subreddit = r.get_subreddit("asmr")
schedule.every().saturday.at("18:00").do(removeSticky)
while True:
    try:
        asmrbot()
        sql.commit()
        r.handler.clear_cache()
        time.sleep(5)
    except praw.errors.HTTPException:
        try:
            r = login()
        except Exception as f:
            print("Login failed: " + str(f))
            print ("Sleeping....")
            time.sleep(30)
    except Exception as e:
        print(str(e))
        #traceback.print_exc()
        try:
            r = login()
        except Exception as f:
            print(str(f))
            #if "HTTP" not in str(f):
                #traceback.print_exc()
            print("Sleeping..")
            time.sleep(30) # usually rate limits or 503. Sleeping reduces reddit load.
