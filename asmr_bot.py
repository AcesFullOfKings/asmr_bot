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
import queue

import schedule

import asmr_bot_data as d # d for data
import theonefoster_bot

class my_submission_type():
    sub_permalink = ""
    sub_ID = ""
    channel_ID = ""
    date_created = ""

# PRAW details, other imported data
app_user_agent = d.appUserAgent
app_id = d.appID
app_secret = d.appSecret
app_URI = d.appURI
app_refresh_token = d.appRefreshToken
BADTITLEPHRASES = d.BadTitlePhrases
BANNEDCHANNELS = d.BANNEDCHANNELS

# gdata details
gBrowserKey  = d.gBrowserKey

# global variables
MODLIST = {'theonefoster', 'nvadergir', 'zimm3rmann', 'youngnreckless', 'mahi-mahi', 'asmr_bot', 'sidecarfour', 'harrietpotter'}
VIEWEDMODQUEUE = set()
modqueue_is_full = True #if bot is restarted it will wait for empty modqueue before full queue notifications begin
unactioned_modqueue = queue.Queue(0)
first_run = True #does a lot more processing on first run to catch up with anything missed during downtime

# Messages
METAEXPLAIN = d.METAEXPLAIN
SBEXPLAIN = d.SBEXPLAIN
SBEXPLAIN_MSG = d.SBEXPLAIN_MSG
MUSEXPLAIN = d.MUSEXPLAIN
TITLE_EXPLAIN = d.TITLE_EXPLAIN
BANNEDCHANNELCOMMENT = d.BANNEDCHANNELCOMMENT
TWOTAGSCOMMENT = d.TWOTAGSCOMMENT
BANNEDCHANNELCOMMENT = d.BANNEDCHANNELCOMMENT
BADTITLECOMMENT = d.BADTITLECOMMENT
UNLISTEDCOMMENT = d.UNLISTEDCOMMENT
SPAMCOMMENT = d.SPAMCOMMENT
REPOSTCOMMENT = d.REPOSTCOMMENT
CHANNEL_PLAYLIST_EXPLAIN = d.CHANNEL_PLAYLIST_EXPLAIN
del(d)

vidIDregex = re.compile('(youtu\.be\/|youtube\.com\/(watch\?(.*&)?v=|(embed|v)\/))([^\?&\"\'>]+)')
attribution_regex = re.compile("\/attribution_link\?.*v%3D([^%&]*)(%26|&|$)")

# open shelves
toplist = shelve.open("topPosts","c")
user_submission_data = shelve.open("user_submission_data", "c") # all submissions from past day by author
recent_video_data = shelve.open("recent_video_data", "c") # videos submitted over past 3 months
seen_objects = shelve.open("seen_objects", "c") # to track which objects have been seen.

if "videos" not in recent_video_data: # initialise dict
    fake = my_submission_type()
    fake.date_created = time.time()
    recent_video_data["videos"] = {"id": fake} # empty dict can cause problems. enter test data and remove later.

if "submissions" not in user_submission_data: #initialise dict
    fake = my_submission_type()
    fake.date_created = time.time()
    user_submission_data["submissions"] = {"un": [fake]} # empty dict can cause problems. enter test data and remove later.

if "submissions" not in seen_objects:
    seen_objects["submissions"] = []

if "comments" not in seen_objects:
    seen_objects["comments"] = []

user_submission_data.sync()
recent_video_data.sync()

# Open sql databases
print("Opening databases..")
warnings_db = sqlite3.connect('warnings.db') # for warnings database (bad if corrupted so not using shelve as it's lost data in the past)
warnings_cursor = warnings_db.cursor()
warnings_cursor.execute("CREATE TABLE IF NOT EXISTS warnings(NAME TEXT, WARNINGS INTEGER)")
warnings_db.commit()

def get_youtube_video_data(location, part, input_type, input_val, return_val):

    # read like "from LOCATION, get the PART where INPUT_TYPE is INPUT_VAL and return RETURN_VAL"
    # where location is channels/videos, part is statistics/snippet/status, type is id or fromUsername, val is the search value, return value is the data you want
     
    input_val = input_val.replace(" ", "") # remove spaces (http doesn't like spaces, and it works fine without them: usernames don't have spaces but people think they do: "CGP Grey" is really "cgpgrey")

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

def days_since_youtube_channel_creation(**kwargs):
    if "id" in kwargs:
        creation_date = get_youtube_video_data("channels", "snippet", "id", kwargs["id"], "publishedAt")
    elif "name" in kwargs:
        creation_date = get_youtube_video_data("channels", "snippet", "forUsername", kwargs["name"], "publishedAt")
    else:
        print("Invalid kwargs passed for function days_since_youtube_channel_created!")
        r.send_message(recipient="theonefoster", subject="Error in bot function", message="Invalid kwargs passed in days_since_youtube_channel_creation. Please check it immediately! \n\n kwargs were " + str(kwargs))
        return -1

    if (creation_date != -1):
        try:
            year = creation_date[0:4]
            month = creation_date[5:7]
            day = creation_date[8:10]

            channel_date = datetime.date(year=int(year),month=int(month),day=int(day))
            return datetime.datetime.today().toordinal() - channel_date.toordinal()
        except Exception as e:
            return -1
    else:
        return -1

def video_is_unlisted(ID):
    return get_youtube_video_data("videos", "status", "id", ID, "privacyStatus") == "unlisted"

def check_mod_queue():
    global modqueue_is_full
    global unactioned_modqueue
    global seen_objects
    global user_submission_data
    global recent_video_data

    modqueue = list(r.get_mod_queue(subreddit=subreddit.display_name))

    for item in modqueue:
        if item.fullname not in VIEWEDMODQUEUE:
            print("New modqueue item!")
            VIEWEDMODQUEUE.add(item.fullname)

            hour = str((time.struct_time(time.strptime(time.ctime())).tm_hour + 4)%24)
            min = str(time.struct_time(time.strptime(time.ctime())).tm_min)
            scheduletime = hour+":"+min
            
            unactioned_modqueue.put(item)

            schedule.every().day.at(scheduletime).do(check_old_mod_queue_item)

            if user_is_shadowbanned(item.author.name):
                print("Replying to shadowbanned user " + item.author.name)
             
                if item.fullname.startswith("t3"):  # submission
                    item.remove(False)
                    item.add_comment(SBEXPLAIN).distinguish(sticky=True)
                elif item.fullname.startswith("t1"): # comment
                    item.remove(False)
                    r.send_message(recipient=item.author, subject="Shadowban notification", message=SBEXPLAIN_MSG)
                item.clicked = True
            elif len(modqueue) >= 4 and modqueue_is_full == False:
                print("Full modqueue detected! Messaging mods..")
                r.send_message("/r/" + subreddit.display_name, "Modqueue items require attention!", "The modqueue has multiple unactioned items in it - please review them asap! \n\n https://www.reddit.com/r/asmr/about/modqueue/")
                modqueue_is_full = True
            elif len(modqueue) <=2:
                modqueue_is_full = False

def check_old_mod_queue_item():
    submission = unactioned_modqueue.get()
    modqueue = list(r.get_mod_queue(subreddit=subreddit.display_name, fetch=True))
    for item in modqueue:
        if item.id == submission.id:
            print("Modqueue item unactioned for 4 hours - messaging mods")
            r.send_message("/r/" + subreddit.display_name, "Unactioned Modqueue Item", "Attention - a modqueue item hasn't been actioned for 4 hours. Please review it asap! \n\n https://www.reddit.com/r/asmr/about/modqueue/")
    return schedule.CancelJob

def check_comments():
    global first_run
    global seen_objects
    global user_submission_data
    global recent_video_data

    if first_run:
        limit = 100
    else:
        limit = 6

    comments = list(subreddit.get_comments(limit=limit)) # sends request

    for comment in comments:
        if comment.id not in seen_objects["comments"]:
            seen_comments = seen_objects["comments"]
            seen_objects["comments"].append(comment.id)
            seen_objects["comments"] = seen_comments
            seen_objects.sync()

            try:
                comment_author = comment.author.name.lower()
                comment_body = comment.body.lower()

                if any(comment_body == x for x in ["ayy", "ayyy", "ayyyy", "ayyyyy"]):
                    print("Responding to ayy by /u/" + comment_author)
                    comment.reply("lmao").distinguish()
                    continue

                if (comment_author in MODLIST):
                    if ('!bot-meta' in comment_body):
                        print("Comment found! Replying to " + comment_author + " (bad meta post)")
                        if comment_author == "theonefoster":
                            my_comment = tof.get_info(thing_id = comment.fullname)
                            my_comment.delete()
                        else:
                            comment.remove(False)
                        submissionID = comment.parent_id
                        submission = r.get_submission(submission_id=submissionID[3:])
                        submission.remove(False)
                        submission.add_comment(METAEXPLAIN).distinguish(sticky=True)
                    elif ('!bot-mus' in comment_body):
                        print("Comment found! Replying to " + comment_author + " (music)")
                        if comment_author == "theonefoster":
                            my_comment = tof.get_info(thing_id = comment.fullname)
                            my_comment.delete()
                        else:
                            comment.remove(False)
                        submissionID = comment.parent_id
                        submission = r.get_submission(submission_id=submissionID[3:])
                        submission.remove(False)
                        TLcomment = submission.add_comment(MUSEXPLAIN).distinguish(sticky=True)
                    elif ('!bot-title' in comment_body):
                        print("Comment found! Replying to " + comment_author + " (bad title)")
                        if comment_author == "theonefoster":
                            my_comment = tof.get_info(thing_id = comment.fullname)
                            my_comment.delete()
                        else:
                            comment.remove(False)
                        submissionID = comment.parent_id
                        submission = r.get_submission(submission_id=submissionID[3:])
                        submission.remove(False)
                        TLcomment = submission.add_comment(TITLE_EXPLAIN).distinguish(sticky=True)
                    elif ("!bot-warning" in comment_body):
                        print("Comment found! Replying to " + comment_author + " (add warning)")
                        if comment_author == "theonefoster":
                            my_comment = tof.get_info(thing_id = comment.fullname)
                            my_comment.delete()
                        else:
                            comment.remove(False)
                        parent = r.get_info(thing_id=comment.parent_id)
                        add_warning(parent)
                    elif("!bot-purge" in comment_body):
                        print("Comment found! Replying to " + comment_author + " (kill thread)")
                        try:
                            parent = r.get_info(thing_id=comment.parent_id)
                            if parent.fullname.startswith("t1"):# TODO - this isn't necessary I think
                                parent = get_comment_from_submission(parent)
                                purge_thread(parent)
                                if comment_author == "theonefoster":
                                    my_comment = tof.get_info(thing_id = comment.fullname)
                                    my_comment.delete()
                            else:
                                if comment_author == "theonefoster":
                                    my_comment = tof.get_info(thing_id = comment.fullname)
                                    my_comment.delete()
                                else:
                                    comment.remove(False)
                                r.send_message(comment_author, "Failed command", "The !bot-purge command can only be used in reply to a top-level comment. This is due to reddit API restrictions.") #todo: wat
                        except Exception as e:
                            print("Exception when purging comment tree - "+str(e)+"\nParent was " + parent.id)
                            #traceback.print_exc()
                            r.send_message(comment_author, "Failed command", "Your purge command failed for an unknown reason. Your comment was removed.")
                        finally:
                            comment.remove(False)

            except AttributeError: # if comment has no author (is deleted) (comment.author.name returns AttributeError), do nothing
                print("Attribute Error! Comment was probably deleted.")
                #traceback.print_exc()
    
def check_submissions():
    global first_run
    global recent_video_data
    global user_submission_data
    global seen_objects

    if first_run:
        limit = 50
    else:
        limit = 8

    submissions = list(subreddit.get_new(limit=limit))


    for submission in submissions:
        if submission.id not in seen_objects["submissions"]: 
            seen_submissions = seen_objects["submissions"]
            seen_submissions.append(submission.id)
            seen_objects["submissions"] = seen_submissions
            seen_objects.sync()
            
            # for each new submission..
            
            if(title_has_two_tags(submission.title)):
                submission.remove(False)
                submission.add_comment(TWOTAGSCOMMENT).distinguish(sticky=True)
                print("Removed submission " + submission.id + " for having two flair tags.")
            elif is_bad_title(submission.title):
                submission.remove(False)
                submission.add_comment(BADTITLECOMMENT).distinguish(sticky=True)
                r.send_message("theonefoster", "Bad Title - Submission removed", submission.permalink + "\n\nTitle was: \"**" + submission.title + "**\"")
                print("Removed submission " + submission.id + " for having a bad title.")
            elif ("youtube" in submission.url or "youtu.be" in submission.url):
                try:
                    if is_banned_link(submission.url):
                        submission.remove(False)
                        submission.add_comment(CHANNEL_PLAYLIST_EXPLAIN).distinguish(sticky=True)
                        print("Removing submission " + submission.short_link + " (link to channel/playlist)")
                    else:
                        if ("youtube." in submission.url or "youtu.be" in submission.url):
                            is_youtube_link = True
                            if "attribution_link" in submission.url:
                                result = attribution_regex.split(submission.url)
                                vid_id = result[1]
                            else:
                                result = vidIDregex.split(submission.url)
                                vid_id = result[5]

                        if is_youtube_link:
                            channel_id = get_youtube_video_data("videos", "snippet", "id", vid_id, "channelId")                  
                            removed = False

                            if channel_id in BANNEDCHANNELS:
                                submission.remove(False) # checks for banned youtube channels
                                submission.add_comment(BANNEDCHANNELCOMMENT).distinguish(sticky=True)
                                print("Removing submission " + submission.short_link + " (banned youtube channel)..")
                                removed = True
                            elif video_is_unlisted(vid_id):
                                submission.remove(False)
                                submission.add_comment(UNLISTEDCOMMENT).distinguish(sticky=True)
                                print("Removing submission " + submission.short_link + " (unlisted video)..")
                                removed = True
                            elif vid_id in recent_video_data["videos"]: #submission is repost
                                my_old_post = recent_video_data["videos"][vid_id]
                                try:
                                    old_post = r.get_info(thing_id="t3_" + my_old_post.sub_ID)
                                    if old_post is None or old_post.author is None or old_post.banned_by is not None: #if old post isn't live, i.e. is removed or deleted
                                        remove_post = False # allow repost since old one is gone
                                    else: 
                                        remove_post = True # repost will be removed
                                except:
                                    remove_post = True # assume repost isn't allowed by default; will be removed

                                if remove_post: #flag to show if it should be removed
                                    submission.remove(False)
                                    comment = REPOSTCOMMENT.format(old_link=old_post.permalink)
                                    submission.add_comment(comment).distinguish(sticky=True)
                                    removed = True
                                    print("Removing submission " + submission.short_link + " (reposted video)..")

                            if not removed: #successful submission (youtube links only)
                            
                                my_sub = my_submission_type()
                                my_sub.sub_permalink = submission.permalink
                                my_sub.sub_ID = submission.id
                                my_sub.channel_ID = channel_id
                                my_sub.date_created = submission.created_utc

                                if is_roleplay(submission.title, vid_id):
                                    r.send_message(recipient=submission.author.name, subject="Role Play " + submission.id, message="Hey! It looks like you've submitted a roleplay-type on /r/asmr. We're trialling tagging these submissions as [Roleplay] to help users find submisisons that they'll enjoy. If you think your submission is a roleplay, please reply to this message with \"yes\" without altering the subject to re-flair your submission automatically. This will help categorise your submission for users looking for particular video types.\n\n Thanks!")
                                    print("Advising " + str(submission.author.name) + " of Roleplay flair via PM..")
                                    
                                recent_videos_copy = recent_video_data["videos"]
                                recent_videos_copy[vid_id] = my_sub # add submission info to temporary dict
                                recent_video_data["videos"] = recent_videos_copy # copy new dict to shelve (can't add to shelve dict directly)

                                # now check if user has submitted three videos of same channel

                                if submission.author.name not in user_submission_data["submissions"]:
                                    d = user_submission_data["submissions"]
                                    d[submission.author.name] = [my_sub]
                                    user_submission_data["submissions"] = d
                                else:
                                    user_submission_list = user_submission_data["submissions"][submission.author.name]
                                    count = 1 # there's already one in submission, don't forget to count that!
                                
                                    for _submission in user_submission_list:
                                        live_submission = r.get_info(thing_id="t3_" + _submission.sub_ID) #update object (might have been removed etc)

                                        if (not submission_is_deleted(live_submission.id)) and live_submission.banned_by is None: #if submission isn't deleted or removed
                                            if _submission.channel_ID == channel_id:
                                                count += 1

                                    if count >= 3: #3 or more submissions to same channel in past day
                                        submission.remove(False)
                                        submission.add_comment(SPAMCOMMENT).distinguish(sticky=True)
                                        print("Removed submission " + submission.id + " and banned user /u/" + submission.author.name + " for too many links to same youtube channel")
                                    
                                        submissionlinks = submission.permalink + "\n\n"
                                    
                                        for s in user_submission_list:
                                            submissionlinks += s.sub_permalink + "\n\n"
                                            sub_to_remove = r.get_info(thing_id="t3_" + s.sub_ID)
                                            sub_to_remove.remove(False)
                                        user_submission_data["submissions"][submission.author.name] = [] #clear the list (user is banned anyway)
                                        note = "too many links to same youtube channel - 1-day ban"
                                        msg = "Warning ban for spamming links to a youtube channel"
                                        subreddit.add_ban(submission.author, duration=1, note=note, ban_message=msg)
                                        r.send_message("/r/" + subreddit.display_name, "Ban Notification", "I have banned /u/" + submission.author.name + " for spammy behaviour (submitting three links to the same youtube channel in a 24-hour period). The ban will last **1 day only**. \n\nLinks to the offending submissions:\n\n" + submissionlinks)
                                    else:
                                        d = user_submission_data["submissions"]  #copy dict
                                        l = d[submission.author.name] # get list of user submissions
                                        l.append(my_sub) #append submission to list
                                        d[submission.author.name] = l # update dict value
                                        user_submission_data["submissions"] = d #write dict back to shelve 
                except Exception as e:
                    print("exception on removal of submission " + submission.short_link + " - " + str(e))

def check_messages():
    messages = list(r.get_unread(limit=10))

    for message in messages:
        if not message.was_comment:
            user = message.author.name
            print("Message dectected from " + user)

            if ("!recommend" in message.body.lower() or "!recommend" in message.subject.lower()): # recommendation
                print("Recommending popular video")
                message_to_send = recommend_top_submission()
                message.reply(message_to_send)
            elif "Role Play " in message.subject:
                try:
                    id = message.subject[-6:]
                    submission = r.get_info(thing_id = "t3_" + id)
                    if message.author.name == submission.author.name:
                        print("Assigning roleplay flair..")
                        submission.set_flair("ROLEPLAY", "roleplay")
                        message.reply("Thanks! I've updated your submission's flair for you :)")
                    else:
                        message.reply("Command failed - you can't edit flair on other people's submissions.")
                except: # if it fails, oh well
                    message.reply("Command failed for unknown reason. Please [contact mods on modmail](https://www.reddit.com/message/compose?to=%2Fr%2Fasmr)")
            elif(message.subject == "flair request" or message.subject == "re: flair request"): # set flair

                got_from_id = False
                channel_name = message.body
                des = get_youtube_video_data("channels", "snippet", "forUsername", channel_name, "description") # des as in description #tested
            
                if des == -1:
                    des = get_youtube_video_data("channels", "snippet", "id", message.body, "description")
                    channel_name = get_youtube_video_data("channels", "snippet", "id", message.body, "title")
                    got_from_id = True

                if des != -1:
                    if "hey /r/asmr mods!" in des.lower():
                        if got_from_id:
                            subs = int(get_youtube_video_data("channels", "statistics", "id", message.body, "subscriberCount"))
                        else:
                            subs = int(get_youtube_video_data("channels", "statistics", "forUsername", channel_name, "subscriberCount"))

                        if subs >= 1000:
                            if got_from_id:
                                age = days_since_youtube_channel_creation(id=message.body)
                            else:
                                age = days_since_youtube_channel_creation(name=channel_name)

                            if age > 182:

                                if got_from_id:
                                    video_count = int(get_youtube_video_data("channels", "statistics", "id", message.body, "videoCount"))
                                else:
                                    video_count = int(get_youtube_video_data("channels", "statistics", "forUsername", channel_name, "videoCount"))

                                if video_count >= 12:
                                    try:
                                        r.set_flair(subreddit="asmr", item=user, flair_text=channel_name, flair_css_class="purpleflair")
                                        message.reply("Verification has been sucessful! Your flair should be applied within a few minutes, but it can sometimes take up to an hour depending on how slow reddit is being today. Please remember to remove the message from your channel description as soon as possible, otherwise somebody could steal your flair. Enjoy!")
                                        global subreddit
                                        subreddit.add_contributor(user)
                                        print("Verified and set flair for " + user)
                                    except:
                                        message.reply("An unknown error occurred during flair assignment. You passed the flair eligibility test but something went wrong - this could be due to reddit being overloaded. Please contact the mods directly. Sorry about that :\\")
                                else:
                                    message.reply("Unfortunately your channel needs to have at least 12 published videos to be eligible for subreddit flair, but you've only published " + str(video_count) + " so far. Thanks for applying though, and feel free to check back once you've published 12 videos.")
                                    print("flair verification for " + channel_name + " failed - not enough published videos.")
                            else:
                                message.reply("Unfortunately your channel needs to be at least 6 months (182 days) old to be eligible for subreddit flair. Thanks for applying, and feel free to check back when your channel is old enough!")
                                print("flair verification for " + channel_name + " failed - channel too new.")
                        else:
                            message.reply("Unfortunately you need to have 1000 youtube subscribers to qualify for flair. You only have " + str(subs) + " at the moment, but come back once you reach 1000!")
                            print("flair verification for " + channel_name + " failed - not enough subs.")
                    else:
                        message.reply("I couldn't see the verification message in your channel description. Please make sure you include the exact phrase '**Hey \\/r/asmr mods!**' (without the quotes) in your youtube channel description so I can verify that you really own that channel. You should remove the verification message as soon as you've been verified.")
                        print("flair verification for " + channel_name + " failed - no verification message.")
                else:
                    message.reply("""
Sorry, I couldn't find that channel. You can use either the channel name (eg 'asmrtess') or the channel ID (the messy part in the youtube link - go to your page and get just the ID from the URL in the format youtube.com/channel/<ID>, eg "UCb3fNzphmiwDgHO2Yg319uw"). Sending ONLY the username OR the ID will work. 
                
Please make sure that the username/ID is exactly correct as it appears on youtube, and that you're not sending anything but the username or channel ID - for example spaces either side of the username/ID or extra text apart from the username/ID (sending the full "youtube.com" link won't work). See [the wiki page](/r/asmr/wiki/flair_requests) for full instructions. If you're still having problems, please [message the human mods](https://www.reddit.com/message/compose?to=%2Fr%2Fasmr)""")
                    print("flair verification failed - channel not found. Message was: " + message.body)
            elif(message.subject == "delete flair"): # delete flair
                if message.body == "delete flair":
                    r.delete_flair(subreddit="asmr", user=user)
                    message.reply("Your flair has been deleted. To apply for flair again, use [this link.](https://www.reddit.com/message/compose?to=asmr_bot&subject=flair%20request&message=enter your channel name here)")
                    print("Flair deleted for " + user)
            elif("post reply" not in message.subject) and ("comment reply" not in message.subject) and ("username mention" not in message.subject) and ("you've been banned from" not in message.subject):
                print("Command not recognised. Message was " + message.body)
                message.reply("Sorry, I don't recognise that command. If you're trying to request a flair, read [the instructions here](https://www.reddit.com/r/asmr/wiki/flair_requests). For other commands you can send me, read the [asmr_bot wiki page](https://www.reddit.com/r/asmr/wiki/asmr_bot). If you have any questions or feedback, please message /u/theonefoster.")
        else:
            message.reply("I'm a bot, so I can't read replies to my comments. If you have some feedback please message /u/theonefoster.")
        message.mark_as_read()

def title_has_two_tags(title):
    twoTagsRegex = re.compile('.*\[(intentional|unintentional|roleplay|role play|media|article|discussion|question|meta|request)\].*\[(intentional|unintentional|roleplay|role play|media|article|discussion|question|meta|request)\].*', re.I)
    return (re.search(twoTagsRegex, title) is not None) # search the title for two tags; if two are found return true, else return false

def update_top_submissions(): # updates recommendation database. Doesn't usually need to be run unless the data gets corrupt or the top submissions drastically change.
    toplist = shelve.open("topPosts","c")
    submissions = subreddit.get_top_from_all(limit=1000)
    added_count = 0
    total_count = 0
    goal = 700

    for submission in submissions:
        total_count += 1
        print("Got submission " + submission.id + "(" + str(total_count) + ")")
        if (".youtube" in submission.url or "youtu.be" in submission.url) and (not "playlist" in submission.url) and (not "attribution_link" in submission.url):
            try:
                result = vidIDregex.split(submission.url)
                vid_id = result[5]
                channel_name = get_youtube_video_data("videos", "snippet", "id", vid_id, "channelTitle")
                vid_title = get_youtube_video_data("videos", "snippet", "id", vid_id, "title")
                if (channel_name != -1) and (vid_title != -1):
                    toplist[str(added_count)] = {"URL" : submission.url, "Channel": channel_name, "Title": vid_title, "Reddit Link": submission.permalink}
                    added_count += 1
                    if added_count > goal:
                        break
                else:
                    print("Youtube Exception. Bad link?")
            except Exception as e:
                print("Other exception - " + str(e))
                #traceback.print_exc()
    toplist.sync()
    toplist.close()
    print("total videos: " + str(added_count))

def recommend_top_submission():
    toplist = shelve.open("topPosts","c")

    if "1" not in list(toplist): #if the database doesn't exist
        toplist.sync()
        toplist.close()
        update_top_submissions()
        toplist = shelve.open("topPosts","c")

    rand = random.randint(0, len(toplist)-1)
    title = ''.join(char for char in toplist[str(rand)]["Title"] if char in string.printable)

    if title == "":
        title = "this video"

    rtn = "How about [" + title + "](" + (toplist[str(rand)]["URL"]) + ") by " + toplist[str(rand)]["Channel"] + "? \n\n[(Reddit link)](" + toplist[str(rand)]["Reddit Link"] + ") \n\nIf you don't like this video, reply with ""!recommend"" and I'll find you another one."
    
    toplist.sync()
    toplist.close()

    return rtn

def user_is_active(username):# TODO
    return True

def user_is_shadowbanned(username):
    try:
        user = r.get_redditor(user_name=username, fetch=True)
        return False
    except praw.errors.HTTPException:
        return True
    except Exception as e:
        print("Unknown exception when checking shadowban for user " + username + " - exception code: \"" + str(e) + "\"")
        #traceback.print_exc()
        return False

def submission_is_deleted(id):
    try:
        submission = r.get_submission(submission_id = id)
        return (submission.author is None)
    except praw.errors.InvalidSubmission:
        return True

def add_warning(post): # post is a reddit 'thing' (comment or submission) for which the author is receiving a warning
    user = post.author.name
    ordinal = "?"
    # curWar.execute("DELETE FROM warnings WHERE name=?", [user])
    # sqlWar.commit()
    # print "deleted."
    # time.sleep(1000000)

    warnings_cursor.execute("SELECT * FROM warnings WHERE name=?", [user])
    result = warnings_cursor.fetchone()
    
    if not result:
        post.remove(False)
        warnings_cursor.execute("INSERT INTO warnings VALUES(?,?)", [user, 1])
        note = "Auto-ban: first warning - " + post.permalink
        msg = "You have received an automatic warning ban because of your post [here](" + post.permalink + "). This is your first warning, which is accompanied by a 7-day ban. Please take 2 minutes to read [our subreddit rules](/r/asmr/wiki) before participating in the community again."
        subreddit.add_ban(post.author, duration=7, note=note, ban_message=msg)
        ordinal = "First"
    elif result[1] >= 2: 
        post.remove(False)
        warnings_cursor.execute("DELETE FROM warnings WHERE name=?", [user])
        warnings_cursor.execute("INSERT INTO warnings VALUES(?,?)",  [user, 3])
        note = "Auto-ban: Permanent - " + post.permalink
        msg = "You have been automatically banned because of your post [here](" + post.permalink + "). This is your third warning, meaning you are now permanently banned."
        subreddit.add_ban(post.author, note=note, ban_message=msg)
        ordinal = "Third"
    elif result[1] == 1:
        post.remove(False)
        warnings_cursor.execute("DELETE FROM warnings WHERE name=?", [user])
        warnings_cursor.execute("INSERT INTO warnings VALUES(?,?)",  [user, 2])
        note = "Auto-ban: Final warning - " + post.permalink
        msg = "You have received an automatic warning ban because of your post [here](" + post.permalink + "). **This is your final warning**. You will be banned for the next 30 days; if you receive another warning, you will be permanently banned. Please take 2 minutes to read [our subreddit rules](/r/asmr/wiki) before participating in the community again."
        subreddit.add_ban(post.author, duration=30, note=note, ban_message=msg)
        ordinal = "Second"
    warnings_db.commit()
    print(ordinal + " warning added for " + user)

def is_bad_title(title):
    title = title.lower()
    if any(phrase in title for phrase in ["[intentional]", "[unintentional]", "[roleplay]", "[role play]"]):
        for phrase in BADTITLEPHRASES:
            if phrase in title:
                return True
    return False

def is_banned_link(url): 
    if (    (".youtube." in url 
             or "youtu.be" in url
            )
        and ("playlist" in url
             or "list=" in url 
             or "/channel/" in url 
             or "/user/" in url
            )
       ):
        return True
    else:
        return False

def is_roleplay(title, vid_id):
    title = title.lower()
    if "[intentional]" in title: #only care about submissions tagged [intentional]
        if ("role play" in title or "roleplay" in title):
            return True
        else:
            vid_title = get_youtube_video_data("videos", "snippet", "id", vid_id, "title")
            if vid_title != -1:
                vid_title = vid_title.lower()
                if "roleplay" in vid_title or "role play" in vid_title:
                    return True
    return False

def purge_thread(comment): # yay recursion woop woop
    for c in comment.replies:
        purge_thread(c)
    comment.remove(False)

def get_comment_from_submission(comment):
    s = comment.submission
    i = comment.id
    for c in s.comments:
        if c.id == i:
            return c # yes, this is completely dumb. No, there's no other way to do it. Yes, the reddit api is weird sometimes.
    return None      # just don't worry about it too much.

def login():
    print("logging in..")
    r = praw.Reddit(app_user_agent, disable_update_check=True)
    r.set_oauth_app_info(app_id,app_secret, app_URI)
    r.refresh_access_information(app_refresh_token)
    print("logged in as " + str(r.user.name))
    return r

def remove_tech_tuesday():
    sticky = subreddit.get_sticky()
    try:
        if "Tech Tuesday" in sticky.title:
            sticky.unsticky()
        else:
            sticky = subreddit.get_sticky(bottom=True) # get second sticky
            if "Tech Tuesday" in sticky.title:
                sticky.unsticky()
    except praw.errors.HTTPException as e: # if there's no sticky it'll throw a 404 Not Found
        pass

def remove_ffaf(): #can't use parameter in shedules so need separate functions
    sticky = subreddit.get_sticky()
    try:
        if "Free-For-All Friday" in sticky.title:
            sticky.unsticky()
        else:
            sticky = subreddit.get_sticky(bottom=True) # get second sticky
            if "Free-For-All Friday" in sticky.title:
                sticky.unsticky()
    except praw.errors.HTTPException as e: # if there's no sticky it'll throw a 404 Not Found
        pass

def clear_user_submissions():
    # user_submission_data is a dict containing usernames as keys and lists as values
    # Each user's dict value is a list of my_submission_type objects, representing 
    # every submission they've made in the last 24 hours

    submissions = user_submission_data["submissions"]
    users = list(submissions.keys())

    for user in users:
        if user == "un" and len(users) > 2:
            del submissions["un"]
            continue
        submissions_by_user = submissions[user] 
        temp = list(submissions_by_user)
        for s in temp:
            if s.date_created < (time.time()-86400): #if the submission was over 24 hours ago
                submissions_by_user.remove(s) # remove it from the list

        if len(submissions_by_user) == 0: # and if there are no submissions by that user in the past 24 hours
            del submissions[user] # remove the user's key from the dict       
        elif len(submissions[user]) != len(submissions_by_user):
                submissions[user] = submissions_by_user # update submissions log

    user_submission_data["submissions"] = submissions

def update_seen_objects():
    done_submissions = seen_objects["submissions"][:500] # trim to only 500 subs
    seen_objects["submissions"] = done_submissions
    done_comments = seen_objects["comments"][:500] # trim to only 500 comments
    seen_objects["comments"] = done_comments
    seen_objects.sync()

def clear_video_submissions(): # maybe doesn't work??
    submissions_dict = recent_video_data["videos"]

    dict_keys = list(submissions_dict.keys())
    
    for key in dict_keys:
        if key == "id" and len(dict_keys) > 2:
            del submissions_dict[key]
        elif submissions_dict[key].date_created < (time.time() - 7948800): #if submission was more than 3 months ago
            del submissions_dict[key]

    recent_video_data["videos"] = submissions_dict

def asmr_bot():
    schedule.run_pending()
    check_submissions()
    check_comments()
    check_messages()
    check_mod_queue()

# --------------------------------
# END OF FUNCTIONS
# --------------------------------

r = login()
tof = theonefoster_bot.login()
del(theonefoster_bot)
subreddit = r.get_subreddit("asmr")

schedule.every().thursday.at("23:50").do(remove_ffaf)
schedule.every().wednesday.at("18:00").do(remove_tech_tuesday)
schedule.every(28).days.at("03:00").do(update_top_submissions) #once per month ish
schedule.every().hour.do(clear_user_submissions)
schedule.every().day.do(update_seen_objects)
schedule.every().day.at("02:00").do(clear_video_submissions) #once per day

while True:
    try:
        asmr_bot()
    except praw.errors.HTTPException as e:
        try:
            print("HTTP Exception: " + str(e))
            r = login()
        except Exception as f:
            print("Login failed: " + str(f))
            print ("Sleeping....")
            time.sleep(30)
    except Exception as e:
        print("Unknown exception: " + str(e))
        #traceback.print_exc()
        try:
            r = login()
        except Exception as f:
            print(str(f))
            print("Sleeping..")
            time.sleep(30) # usually rate limits or 503. Sleeping reduces reddit load.
    finally:
        r.handler.clear_cache()

        recent_video_data.sync()
        user_submission_data.sync()
        seen_objects.sync()

        recent_video_data.close()
        user_submission_data.close()
        seen_objects.close()

        user_submission_data = shelve.open("user_submission_data", "c") # all submissions from past day by author
        recent_video_data = shelve.open("recent_video_data", "c") # videos submitted over past 3 months
        seen_objects = shelve.open("seen_objects", "c") # to track which objects have been seen.

        if first_run:
            first_run = False

        time.sleep(9) # reduces reddit load and unnecessary processor usage
