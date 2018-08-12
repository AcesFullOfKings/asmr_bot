# for /u/asmr_bot 
# REQUIRES PRAW 5.4 OR LATER
import praw
import prawcore
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
from difflib import SequenceMatcher as matcher

import schedule

import asmr_bot_data as d # d for data

# PRAW details, other imported data
bad_title_phrases = d.bad_title_phrases
banned_channels = d.BANNED_CHANNELS

# gdata details
g_browser_key = d.g_browser_key

# global variables
mod_list = {'theonefoster', 'nvadergir', 'mahi-mahi', 'asmr_bot', 'underscorewarrior', 'roflbbq', 'unicornica', 'automoderator'}
viewed_mod_queue = set()
modqueue_is_full = True # if bot is restarted it will wait for empty modqueue before full queue notifications begin
unactioned_modqueue = queue.Queue(0)
first_run = True # does a lot more processing on first run to catch up with anything missed during downtime
first_run_backcheck = 100
general_backcheck = 6
banned_channels = set()

# Messages
meta_explain = d.META_EXPLAIN
mus_explain = d.MUS_EXPLAIN
mod_title_explain = d.MOD_TITLE_EXPLAIN
two_tags_explain = d.TWO_TAGS_COMMENT
banned_channel_explain = d.BANNED_CHANNEL_COMMENT
auto_title_explain = d.AUTO_TITLE_COMMENT
unlisted_explain = d.UNLISTED_COMMENT
spam_explain = d.SPAM_COMMENT
repost_explain = d.REPOST_COMMENT
channel_or_playlist_explain = d.CHANNEL_PLAYLIST_EXPLAIN
nsfw_explain = d.NSFW_EXPLAIN
replies = d.messages
comment_reply = d.comment_reply
taggable_channels = d.linkable_channels
capital_explain = d.CAPITAL_TITLE
edit_link_explain = d.EDIT_LINK
del(d)

vid_id_regex = re.compile('(youtu\.be\/|youtube\.com\/(watch\?(.*&)?v=|(embed|v)\/))([^\?&\"\'>]+)')
attribution_regex = re.compile("\/attribution_link\?.*v%3D([^%&]*)(%26|&|$)")
channel_name_regex = re.compile("\[\[(.*?)\]\]")

# Open sql databases
print("Opening databases..")

warnings_db = sqlite3.connect('warnings.db', detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES) # for warnings database
warnings_cursor = warnings_db.cursor()
warnings_cursor.execute("CREATE TABLE IF NOT EXISTS warnings(NAME TEXT, LINK TEXT, BANNING_MOD TEXT, REASON TEXT, TIMESTAMP INT, BAN_NUM INT)")
warnings_db.commit()

user_submissions_db = sqlite3.connect("user_submissions.db")
user_submissions_cur = user_submissions_db.cursor()
user_submissions_cur.execute("CREATE TABLE IF NOT EXISTS user_submissions(USERNAME TEXT, SUBMISSION_ID TEXT, SUBMISSION_DATE INT, SUBMISSION_PERMALINK TEXT, CHANNEL_ID TEXT)")
user_submissions_db.commit()

recent_videos_db = sqlite3.connect("recent_videos.db")
recent_videos_cur = recent_videos_db.cursor()
recent_videos_cur.execute("CREATE TABLE IF NOT EXISTS recent_videos(ID TEXT, SUBMISSION_DATE INT, REDDIT_ID TEXT)")
recent_videos_db.commit()

with open("seen_comments.txt", "a+") as f:
   pass # guarantees that the file exists: creates it if it doesn't.

with open("seen_submissions.txt", "a+") as f:
   pass # ditto

# ----------------------
# BEGIN FUNCTIONS
# ----------------------

def get_youtube_video_data(location, part, input_type, input_val, return_val):
    # read like "from LOCATION, get the PART where INPUT_TYPE is INPUT_VAL and return RETURN_VAL"
    # where location is channels/videos, part is statistics/snippet/status, type is id or fromUsername, val is the search value, return value is the data you want
     
    input_val = input_val.replace(" ", "") # remove spaces (http doesn't like spaces, and it works fine without them: usernames don't have spaces but people think they do: "CGP Grey" is really "cgpgrey")

    try:
        URL = ("https://www.googleapis.com/youtube/v3/" + location + "?part=" + part + "&" + input_type + "=" + input_val + "&key=" + g_browser_key)
        response = requests.get(URL).json()
        items = response[u'items']
        snippet = items[0][part]
        if return_val == "all":
            return snippet
        else:
            rtn = snippet[return_val]
            return rtn
    except Exception as e:
        # traceback.print_exc()
        return -1

def days_since_youtube_channel_creation(**kwargs):
    if "id" in kwargs:
        creation_date = get_youtube_video_data("channels", "snippet", "id", kwargs["id"], "publishedAt")
    elif "name" in kwargs:
        creation_date = get_youtube_video_data("channels", "snippet", "forUsername", kwargs["name"], "publishedAt")
    else:
        creation_date = -1

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

def get_vid_id(url):
    if "attribution_link" in url:
        result = attribution_regex.split(url)
        vid_id = result[1]
    elif "youtube." in url or "youtu.be" in url:
        result = vid_id_regex.split(url)
        vid_id = result[5]
    else:
        return -1

    return vid_id

def check_mod_queue(): #tested - works
    global modqueue_is_full
    global unactioned_modqueue
    global seen_objects
    global user_submission_data
    global recent_video_data # shouldn't really need these but seems not to work on linux without them
    
    modqueue = list(subreddit.mod.modqueue()) #modqueue is a list of comments. Each comment has attributes mod_reports and user_reports, which are lists. Each is a list of reports, where each report is a list of ["report reason", int:num reports].
 
    for item in modqueue:
        if item.fullname not in viewed_mod_queue:
            print("New modqueue item!")
            viewed_mod_queue.add(item.fullname)

            #for 4 hours in future:
            hour = str((time.struct_time(time.strptime(time.ctime())).tm_hour + 4)%24)
            min = str(time.struct_time(time.strptime(time.ctime())).tm_min)

            #for 1 min in future (for testing):
            #hour = str((time.struct_time(time.strptime(time.ctime())).tm_hour)%24)
            #min = str((time.struct_time(time.strptime(time.ctime())).tm_min + 1)%60)

            schedule_time = hour+":"+min
            unactioned_modqueue.put(item)
            schedule.every().day.at(schedule_time).do(check_old_mod_queue_item) #cancels after first run, so effectively just schedules the function to run once at schedule_time

            if len(modqueue) >= 4 and modqueue_is_full == False:
                print("Full modqueue detected! Messaging mods..")
                subject = "Modqueue items require attention!"
                message = "The modqueue has multiple unactioned items in it - please review them asap! \n\n https://www.reddit.com/r/asmr/about/modqueue/"
                subreddit.message(subject=subject, message=message)
                modqueue_is_full = True
            elif len(modqueue) <=3:
                modqueue_is_full = False

def check_old_mod_queue_item(): #tested - works
    submission = unactioned_modqueue.get()
    modqueue = list(subreddit.mod.modqueue())
    for item in modqueue:
        if item.id == submission.id:
            print("Modqueue item unactioned for 4 hours - messaging mods")
            subject = "Unactioned Modqueue Item (bot v5.0)"
            message = "Attention - a modqueue item hasn't been actioned for 4 hours. Please review it asap!\n\nhttps://www.reddit.com/r/asmr/about/modqueue/"
            subreddit.message(subject=subject, message=message)
    return schedule.CancelJob

def check_comments():
    global first_run
    global seen_objects
    global user_submission_data
    global recent_video_data # shouldn't really need these but seems not to work on linux without them

    limit = first_run_backcheck if first_run else general_backcheck

    comments = list(subreddit.comments(limit=limit)) # sends request  

    with open("seen_comments.txt", "r") as f:
        seen_ids=f.read().split("\n")

    for comment in comments:
        if comment.id not in seen_ids:
            with open("seen_comments.txt", "a") as f:
                f.write(comment.id + "\n")

            try:
                comment_author = comment.author.name.lower()
                comment_body = comment.body.lower()

                # public commands:
                if any(comment_body == x for x in ["ayy", "ayyy", "ayyyy", "ayyyyy"]):
                    print("Responding to ayy by /u/" + comment_author)
                    comment.reply("lmao").mod.distinguish()
                    continue

                if comment_author != "asmr_bot":
                    unescaped_body = comment.body.replace("\\", "") #remove any single backslashes added by reddit's "fancy" (read: stupid) comment editor
                    channels = re.findall(channel_name_regex, unescaped_body)
                    if len(channels) > 0:
                        reply = ""
                        message = ""
                        for channel in channels:
                            details = link_youtube_channel(channel)
                            if details != -1: #rogue value indicates no details found
                                reply += details + "\n\n"
                            else:
                                if message == "":
                                    message = "I couldn't find any details on the following tagged channels:\n\n"
                                message += ("* {channel}\n\n".format(channel=channel))
                        print("Replying to tagged channel(s)..")

                        if reply != "": #channels with details found
                            comment.reply(reply).mod.distinguish()

                        if message != "": #channels with no details found
                            comment.author.message(subject="Tagged channel(s) not found", message=message)

                        continue # don't carry out further checks
                    
                # moderator commands
                if (comment_author in mod_list) and comment.banned_by is None: #if mod comment not removed..
                    if comment.is_root:
                        #commands which can only be used at the top-level (as comments in reply to submissions)
                        if comment_body.startswith("!meta"):
                            print("Removing submission in response to " + comment_author + " (bad meta post)")
                            remove_mod_comment(comment)
                            submission = r.submission(id=comment.parent_id[3:]) #will break here if command is not top-level comment
                            submission.mod.remove()
                            submission.reply(meta_explain.format(mod=comment_author)).mod.distinguish()
                            continue
                        elif comment_body.startswith("!music"):
                            print("Removing submission in response to " + comment_author + " (music)")
                            remove_mod_comment(comment)
                            submission = r.submission(id=comment.parent_id[3:])
                            submission.mod.remove()
                            submission.reply(mus_explain.format(mod=comment_author)).mod.distinguish()
                            continue
                        elif comment_body.startswith("!title"):
                            print("Removing submission in response to " + comment_author + " (bad title)")
                            remove_mod_comment(comment)
                            submission = r.submission(id=comment.parent_id[3:])
                            submission.mod.remove()
                            submission.reply(mod_title_explain.format(mod=comment_author)).mod.distinguish()
                            continue
                        elif comment_body.startswith("!nsfw"):
                            print("Removing submission in response to " + comment_author + " (nsfw content)")
                            remove_mod_comment(comment)
                            submission = r.submission(id=comment.parent_id[3:])
                            submission.mod.remove()
                            submission.reply(nsfw_explain.format(mod=comment_author)).mod.distinguish()
                            continue
                    if comment_body.startswith("!remove"):
                        print("Removing submission in response to " + comment_author + " (remove by command)")
                        remove_mod_comment(comment)
                        parent = r.comment(id=comment.parent_id[3:])
                        parent.mod.remove()
                    elif comment_body.startswith("!warning"):
                        reason = comment_body[9:]
                        remove_mod_comment(comment)
                        parent = r.comment(id=comment.parent_id[3:])
                        if not user_is_subreddit_banned(parent.author.name):
                            # comment_author is mod who is giving the warning
                            print("Removing post in response to " + comment_author + " (add warning)")
                            parent.mod.remove()
                            new_warning(parent, comment_author, reason, False)
                        else:
                            print("Not adding warning in response to " + comment_author + " - user /u/" + parent.author.name + " is already banned.")
                            r.redditor(comment_author).message(subject="Warning not added", message="No warning ban for /u/" + parent.author.name + " was added because that user is already banned. Their comment and your command have been removed.")

                    elif comment_body.startswith("!purge"):
                        print("Removing comment tree in response to " + comment_author + " (kill thread)")
                        try:
                            parent = r.comment(id=comment.parent_id[3:])
                            parent.refresh()
                            purge_thread(parent)
                            remove_mod_comment(comment)
                        except praw.exceptions.PRAWException as e: # tried to assign submission to a comment object; !purge was used at top-level
                            r.redditor(comment_author).message(subject="Failed command", message="The !purge command can only be used in reply to a comment. It cannot be a top-level comment.")
                        except Exception as e:
                            print("Exception when purging comment tree - " + str(e) + "\nParent was " + parent.id)
                            # traceback.print_exc()
                            r.redditor(comment_author).message(subject="Failed command", message="Your purge command failed for an unknown reason. Your comment was removed.")
                        finally:
                            comment.mod.remove()
                    elif comment_body.startswith("!ban"):
                        reason = comment_body[5:]
                        if reason == "":
                            reason = "<No reason given>"

                        parent = r.comment(id=comment.parent_id[3:])

                        ban_user = parent.author.name
                        msg = "You have been banned by {mod} for [your post here]({link}). The moderator who banned you provided the following reason:\n\n**{reason}**"

                        try:
                            print("Banning user {ban_user} for post {post}. Reason given: ""{reason}""".format(ban_user=ban_user, post=parent.id, reason=reason))
                            parent.mod.remove(False)
                            remove_mod_comment(comment)
                        
                            note = comment.author.name + ": " + reason + ": " + parent.permalink
                            subreddit.banned.add(redditor=ban_user, note=note, ban_message=msg.format(mod=comment.author.name, link=parent.permalink, reason=reason))

                            message = "I have permanently banned {ban_user} for their [post here]({ban_post}?context=9) in response to [your comment here]({comment}?context=9), with the reason: \n\n\> {reason} \n\n Ban list: /r/asmr/about/banned"

                            r.redditor(comment_author).message(subject="Ban successful", message=message.format(ban_user=ban_user, ban_post=parent.permalink, comment=comment.permalink, reason=reason))
                        except PermissionError:
                            r.send_message(recipient=comment_author, subject="Ban failed", message="You issued a command [here]({link}) in which you tried to ban a moderator, which is not possible.".format(link=comment.permalink))
                        except praw.exceptions.APIException as ex:
                            if ex.error_type == "CANT_RESTRICT_MODERATOR":
                                r.send_message(recipient=comment_author, subject="Ban failed", message="You issued a command [here]({link}) in which you tried to ban a moderator, which is not possible.".format(link=comment.permalink))
                            else:
                                raise #act as if the exception was never caught here
                    else:
                        if any(comment_body.startswith(command) for command in ["!meta", "!music", "!title"]):
                            print("Invalid command from " + comment_author + " - submission command in reply to comment.")
                            r.redditor(comment.author.name).message(subject="Invalid bot command", message="You issued a command [here]({link}) in reply to a comment, but that command can only be used in reply to a submission. Please re-issue the command as a top-level comment.".format(link=comment.permalink))
                            remove_mod_comment(comment)
                       

            except AttributeError as ex: # if comment has no author (is deleted) (comment.author.name returns AttributeError), do nothing
                print("Attribute Error! Comment was probably deleted. Comment was " + str(comment.fullname))
                print(str(ex))
                # traceback.print_exc()
    
def check_submissions():
    global first_run
    global recent_video_data
    global user_submission_data
    global seen_objects # shouldn't really need these but seems not to work on linux without them

    limit = first_run_backcheck if first_run else general_backcheck

    submissions = list(subreddit.new(limit=limit))

    with open("seen_submissions.txt", "r") as f:
        seen_submissions = f.read().split("\n")

    for submission in submissions:
        try:
            if submission.id not in seen_submissions:
                with open("seen_submissions.txt", "a") as f:
                    f.write(submission.id + "\n")
            
                # for each new submission..
                if(title_has_two_tags(submission.title)):
                    submission.mod.remove(False)
                    submission.reply(two_tags_explain).mod.distinguish(sticky=True)
                    print("Removed submission " + submission.id + " for having two flair tags.")
                elif is_bad_title(submission.title):
                    submission.mod.remove(False)
                    submission.reply(auto_title_explain).mod.distinguish(sticky=True)
                    r.redditor("theonefoster").message(subject="Bad title - submission removed", message=submission.permalink + "\n\nTitle was: \"**" + submission.title + "**\"")
                    print("Removed submission " + submission.id + " for having a bad title.")
                elif title_is_caps(submission.title):
                    submission.mod.remove(False)
                    submission.reply(capital_explain).mod.distinguish(sticky=True)
                    r.redditor("theonefoster").message(subject="Upper case title - submission removed", message=submission.permalink + "\n\nTitle was: \"**" + submission.title + "**\"")
                    print("Removed submission " + submission.id + " for having an uppercase title.")
                elif is_edit_link(submission.url):
                    submission.mod.remove(False)
                    submission.reply(edit_link_explain).mod.distinguish(sticky=True)
                    print("Removed submission " + submission.id + " - link to edit page.")
                elif ("youtube." in submission.url or "youtu.be" in submission.url):
                    try:
                        if is_channel_or_playlist_link(submission.url):
                            submission.mod.remove(False)
                            submission.reply(channel_or_playlist_explain).mod.distinguish(sticky=True)
                            print("Removed submission " + submission.id + " (link to channel/playlist)")
                        else:
                            vid_id = get_vid_id(submission.url)
                            channel_id = get_youtube_video_data("videos", "snippet", "id", vid_id, "channelId")                  
                            removed = False
                            
                            recent_videos_cur.execute("Select * FROM recent_videos")
                            past_videos = recent_videos_cur.fetchall()

                            if channel_id in banned_channels:
                                submission.mod.remove(False) # checks for banned youtube channels
                                submission.reply(banned_channel_explain).mod.distinguish(sticky=True)
                                print("Removed submission " + submission.id + " (banned youtube channel)")
                                removed = True
                            elif video_is_unlisted(vid_id):
                                submission.mod.remove(False)
                                submission.reply(unlisted_explain).mod.distinguish(sticky=True)
                                print("Removed submission " + submission.shortlink + " (unlisted video)")
                                removed = True
                            elif vid_id in [v[0] for v in past_videos]: # submission is repost
                                post_detail = [v for v in past_videos if v[0] == vid_id][0]
                                try:
                                    old_post = r.submission(id=post_detail[2])
                                    if old_post is None or old_post.author is None or old_post.banned_by is not None: # if old post isn't live, i.e. is removed or deleted
                                        remove_post = False # allow repost since old one is gone
                                    else: 
                                        if old_post.permalink != submission.permalink:
                                            remove_post = True # repost will be removed
                                        else:
                                            continue # already processed this post, so don't process it again
                                except (prawcore.exceptions.PrawcoreException, praw.exceptions.PRAWException):
                                    remove_post = False # assume repost is allowed by default; won't be removed

                                #recent_videos(ID TEXT, SUBMISSION_DATE INT, REDDIT_ID TEXT

                                if remove_post: # flag to show if it should be removed
                                    submission.mod.remove(False)
                                    comment = repost_explain.format(old_link=old_post.permalink)
                                    submission.reply(comment).mod.distinguish(sticky=True)
                                    removed = True
                                    print("Removed submission " + submission.id + " (reposted video)")

                            data = [vid_id, submission.created_utc, submission.id]
                            recent_videos_cur.execute("INSERT INTO recent_videos VALUES (?,?,?)", data)
                            recent_videos_db.commit()

                            if not removed: # successful submission (youtube links only)
                                data = [submission.author.name.lower(), submission.id, submission.created_utc, submission.permalink, channel_id]
                                user_submissions_cur.execute("INSERT into user_submissions VALUES (?,?,?,?,?)", list(data))
                                user_submissions_db.commit()

                                time.sleep(1)
                                submission = r.submission(id=submission.id) # Refreshes submission; solves the "Nonetype has no attribute 'lower()'" issue..

                                if submission.link_flair_text is not None and submission.link_flair_text.lower() != "roleplay" and "[intentional]" in submission.title.lower() and is_roleplay(submission.title, vid_id):
                                    choices = submission.flair.choices() #get flair choices
                                    template_id = next(x for x in choices if x['flair_text'] == "ROLEPLAY")['flair_template_id'] #select flair template for ROLEPLAY flair
                                    submission.flair.select(template_id, "ROLEPLAY") #set slair with text of "ROLEPLAY"
                                    print("Reflaired submission " + submission.id + " as roleplay.")

                                # now check if user has submitted three videos of same channel

                                user_submissions_cur.execute("SELECT * FROM user_submissions WHERE USERNAME=?", [submission.author.name.lower()])
                                user_submission_list = user_submissions_cur.fetchall() #list of type [[name, id, time, link, channel]]

                                submission_links = ""
                                count = 0

                                for db_submission in user_submission_list:
                                    live_submission = r.submission(id = db_submission[1]) # update object (might have been removed etc)

                                    if (not submission_is_deleted(live_submission.id)) and live_submission.banned_by is None: # if submission isn't deleted or removed
                                        if db_submission[4] == channel_id:
                                            count += 1

                                if count >= 3: # 3 or more submissions to same channel in past day                                    
                                    for s in user_submission_list:
                                        submission_links += s[3] + "\n\n"
                                        sub_to_remove = r.submission(id=s[1])
                                        sub_to_remove.mod.remove(False)

                                    user_submissions_cur.execute("DELETE FROM user_submissions WHERE USERNAME=?", [submission.author.name.lower()]) # clear the list (user is banned anyway)
                                    user_submissions_db.commit()

                                    submission.mod.remove(False)
                                    submission.reply(spam_explain).mod.distinguish(sticky=True) # doesn't mention ban length
                                    duration = new_warning(submission, "asmr_bot", "spam", spam_warning=True)

                                    if duration == 1:
                                        duration = "1 day only"
                                    elif duration is None:
                                        duration = "forever"
                                    else:
                                        duration = str(duration) + " days"

                                    subreddit.message(subject="Ban Notification", message="I have banned /u/" + submission.author.name + " for spammy behaviour (submitting three links to the same youtube channel in a 24-hour period). The ban will last **" + duration + "**.\n\nLinks to the offending submissions:\n\n" + submission_links + "\n\n/r/asmr/about/banned")
                                    print("Removed submission " + submission.id + " and banned user /u/" + submission.author.name + " for too many links to same youtube channel")
                    except Exception as ex:
                        print("exception on processing of submission " + submission.shortlink + " - " + str(ex))
                        traceback.print_exc()
                        #if "ran out of input" in str(ex).lower(): #shouldn't get this any more since switching to database storage over shelve storage
                        #    break
        except praw.exceptions.APIException as ex:
            if ex.error_type == 'TOO_OLD': #post is archived so can't be commented on
                continue
            else:
                raise

def check_messages():
    messages = list(r.inbox.unread())

    for message in messages:
        try:
            if not message.was_comment:
                user = message.author.name
                print("Message dectected from " + user)

                if ("!recommend" in message.body.lower() or "!recommend" in message.subject.lower()): # recommendation
                    print("Recommending popular video to " + message.author.name)
                    message_to_send = recommend_top_submission()
                    message.reply(message_to_send)
                elif("flair request" in message.subject): # set flair
                
                    global replies

                    using_id = False
                    channel_name = message.body.replace(" ", "").replace(".", "")
                    description = get_youtube_video_data("channels", "snippet", "forUsername", channel_name, "description")
                
                    if description == -1:
                        description = get_youtube_video_data("channels", "snippet", "id", message.body, "description")
                        channel_name = get_youtube_video_data("channels", "snippet", "id", message.body, "title")
                        using_id = True

                    if description != -1:
                        if using_id:
                            subs = int(get_youtube_video_data("channels", "statistics", "id", message.body, "subscriberCount"))
                        else:
                            subs = int(get_youtube_video_data("channels", "statistics", "forUsername", channel_name, "subscriberCount"))

                        if subs >= 1000:
                            if using_id:
                                age = days_since_youtube_channel_creation(id=message.body)
                            else:
                                age = days_since_youtube_channel_creation(name=channel_name)

                            if age > 182:
                                if using_id:
                                    video_count = int(get_youtube_video_data("channels", "statistics", "id", message.body, "videoCount"))
                                else:
                                    video_count = int(get_youtube_video_data("channels", "statistics", "forUsername", channel_name, "videoCount"))

                                if video_count >= 15:
                                    if not user_is_inactive(message.author):
                                        if "hey /r/asmr mods!" in description.lower():
                                            try:
                                                global subreddit
                                                subreddit.flair.set(redditor=user, text=channel_name, css_class="purpleflair")
                                                subreddit.contributor.add(user)
                                                message.reply("Verification has been successful! Your flair should be applied within a few minutes, but it can sometimes take up to an hour depending on how slow reddit is being today. Please remember to remove the verification message from your channel description as soon as possible, otherwise somebody could steal your flair. Enjoy!")

                                                global lounge
                                                lounge.contributor.add(user)
                                                lounge.flair.set(redditor=user, text=channel_name, css_class="purpleflair")
                                                print("Verified and set flair for " + user)
                                            except Exception as ex:
                                                message.reply(replies.unknown_error)
                                                r.redditor("theonefoster").message(subject="Failed flair assignment", message="/u/" + user + " passed flair eligibility but flair assignment failed. Please ensure their flair is set correctly on /r/asmr and /r/asmrCreatorLounge, and that they are an approved submitter on both subreddits. \n\nChannel was: " + channel_name + "\n\n Exception was: " + str(ex))
                                        else:
                                            message.reply(replies.no_verification)
                                            print("flair verification for " + channel_name + " failed - no verification message.")
                                    else:
                                        message.reply(replies.inactive)
                                        print("flair verification for " + channel_name + " failed - account is too new.")
                                else:
                                    message.reply(replies.not_enough_videos.format(vid_count = str(video_count)))
                                    print("flair verification for " + channel_name + " failed - not enough published videos.")
                            else:
                                message.reply(replies.underage)
                                print("flair verification for " + channel_name + " failed - channel too new.")
                        else:
                            message.reply(replies.not_enough_subs.format(current_subs=str(subs)))
                            print("flair verification for " + channel_name + " failed - not enough subs.")
                    else:
                        message.reply(replies.channel_not_found)
                        print("flair verification failed - channel not found. Message was: " + message.body)
                elif(message.subject == "delete flair"): # delete flair
                    if message.body == "delete flair":
                        subreddit.flair.delete(user)
                        message.reply(replies.flair_deleted)
                        print("Flair deleted for " + user)
                elif("post reply" not in message.subject) and ("username mention" not in message.subject) and ("you've been banned from" not in message.subject):
                    print("Command not recognised. Message was " + message.body)
                    message.reply(replies.command_not_recognised)
            else:
                channels = re.findall(channel_name_regex, message.body)
                if len(channels) == 0:
                    print("Replying to comment in messages..")
                    message.reply(comment_reply).mod.distinguish()
                else:
                    pass #double tag detected in message, so it will be dealt with in check_comments
        except prawcore.exceptions.Forbidden as ex: # probably tried to distinguish comment in other subreddit
            pass
        except Exception as ex:
            print("Exception in check_messages(): " + ex.message + " - message was: " + message.body)
        finally:
            message.mark_read()

def remove_mod_comment(comment):
    """If comment was made by me, I have the authentication to delete it, which is preferred. 
    Otherwise Remove it since I can't delete other mods' comments"""

    if comment.author.name == "theonefoster":
        my_comment = tof.comment(id = comment.id) #re-fetch the comment with my personal credentials
        my_comment.delete() #delete comment while authenticated as u/theonefoster
    else:
        comment.mod.remove()

def get_channel_id(name):
    url = 'https://www.youtube.com/results?search_query='
    r_id = re.compile("/channel/(UC[a-zA-Z0-9\-\_]*?)\"")
    r_name = re.compile("href=\"/user/([a-zA-Z0-9]*?)\"")
    name = "".join(c for c in name.lower() if c in "abcdefghijklmnopqrstuvwxyz0123456789")

    page = requests.get(url + name).text
    names = set(name.lower() for name in re.findall(r_name, page))

    for match_name in names: #might be linked by username
        if matcher(a=match_name, b=name).ratio() > 0.8: #check for close matches
            URL = ("https://www.googleapis.com/youtube/v3/channels?part=statistics&forUsername={name}&key=" + g_browser_key).format(name=match_name)
            json = requests.get(URL).json()
            id = json["items"][0]["id"]
            return id

    #username not found, so look for ID:

    channels = re.findall(r_id, page)
    unique_channels = []

    #stupid default channels (News, Sport etc):
    dumb_channels = {'UCOpNcN46UbXVtpKMrmU4Abg', 'UCYfdidRxbB8Qhf0Nx7ioOYw', 'UCwWxEudXr2xxrbVfulvvd8g', 
                    'UCEgdi0XIXXZ-qJOFPf4JSKw', 'UClgRkhTL3_hImCAmdLfDE4g', 'UC4R8DWoMoI7CAwX8_LjQHig', 
                    'UC-9-kyTW8ZkZNDHQJ6FgpwQ', 'UCULkRHBdLC5ZcEQBaL0oYHQ', 'UCzuqhhs6NWbgTzMuM09WKDQ'}

    for c in channels:
        if c not in unique_channels and c not in dumb_channels:
            unique_channels.append(c) #remove duplicates while preserving list order

    snippets = []

    for channel in unique_channels:
        URL = ("https://www.googleapis.com/youtube/v3/channels?part=snippet&id={id}&key=" + g_browser_key).format(id=channel)
        try: 
            result = requests.get(URL)
            json = result.json()
            snippet = json["items"][0]["snippet"]
            try:
                custom_url = snippet["customUrl"].lower()
            except KeyError:
                custom_url = ""
            description = snippet["description"].lower()
            channel_title = snippet["title"].lower()

            if name in custom_url or name in description or name in channel_title:
                return channel #exact match
            snippets.append((channel, custom_url, description, channel_title))
        except (KeyError, IndexError) as ex:
            continue
        
    for channel, custom_url, description, channel_title in snippets: #check for any asmr channel
        if any(word in info for word in ["asmr", "tingle", "relax"] for info in [custom_url, description, channel_title]):
            return channel
    return -1

def link_youtube_channel(name):
    channel_id = ""
    name = "".join(c for c in name.lower() if c in "abcdefghijklmnopqrstuvwxyz0123456789")

    for channel_names in taggable_channels:
        if name in channel_names:
            channel_id = taggable_channels[channel_names] #check if the Id is in the commonly-used list
            break
    else:
        channel_id = get_channel_id(name)
    
    if channel_id == -1:
        print("Channel ID not found for " + name)
        return -1

    URL = ("https://www.googleapis.com/youtube/v3/channels?part=statistics&id={id}&key=" + g_browser_key).format(id=channel_id)
    response = requests.get(URL)

    if response.status_code == 200:
        try:
            json = response.json()
            id = json["items"][0]["id"]
            video_count = "{:,}".format(int(json["items"][0]["statistics"]["videoCount"]))
            view_count = "{:,}".format(int(json["items"][0]["statistics"]["viewCount"]))
            subscribers = "{:,}".format(int(json["items"][0]["statistics"]["subscriberCount"]))
            link = "https://www.youtube.com/channel/" + id

            URL = ("https://www.googleapis.com/youtube/v3/channels?part=snippet&id={id}&key=" + g_browser_key).format(id=id)
            json = requests.get(URL).json()
            channel_title = json["items"][0]["snippet"]["title"]

            table = ("Channel Link|[{name}]({link})\n" + 
                     "---|---\n" +
                     "Number of Videos|{videos}\n" +
                     "Total views|{views}\n" +
                     "Subscribers|{subs}").format(videos=video_count, views=view_count, subs=subscribers, name=channel_title, link=link)
        
            return table
        except (KeyError, AttributeError, IndexError):
            return -1

    else: #NOT FOUND
        return -1
    
def update_top_submissions(): # updates recommendation database. Doesn't usually need to be run unless the data gets corrupt or the top submissions drastically change.
    toplist = shelve.open("topPosts","c")
    submissions = subreddit.top(limit=1000)
    added_count = 0
    total_count = 0
    goal = 750

    for submission in submissions:
        total_count += 1
        print("Got submission " + submission.id + " (" + str(total_count) + ")")
        if is_youtube_link(submission.url):
            try:
                result = vid_id_regex.split(submission.url)
                vid_id = result[5]
                vid_data = get_youtube_video_data("videos", "snippet", "id", vid_id, "all")
                if vid_data != -1:
                    channel_name = vid_data["channelTitle"]
                    vid_title = vid_data["title"]
                    toplist[str(added_count)] = {"URL" : submission.url, "Channel": channel_name, "Title": vid_title, "Reddit Link": submission.permalink}
                    added_count += 1
                    if added_count > goal:
                        break
                else:
                    print("Youtube Exception. Bad link?")
            except Exception as e:
                print("Other exception - " + str(e))
                # traceback.print_exc()
    toplist.sync()
    toplist.close()
    print("total videos: " + str(added_count))

def recommend_top_submission():
    toplist = shelve.open("topPosts","c")

    if "1" not in list(toplist): # if the database doesn't exist
        toplist.sync()
        toplist.close()
        update_top_submissions()
        toplist = shelve.open("topPosts","c")

    rand = random.randint(0, len(toplist)-1)
    title = ''.join(char for char in toplist[str(rand)]["Title"] if char in string.printable)

    if title == "":
        title = "this video"

    message = ("How about [{title}]({URL}) by {channel}?\n\n"
               "[(Reddit link)]({permalink})\n\n"
               "If you don't like this video, reply with \"!recommend\" and I'll find you another one.")
    
    URL = toplist[str(rand)]["URL"]
    channel = toplist[str(rand)]["Channel"]
    permalink = toplist[str(rand)]["Reddit Link"]
    
    #rtn = "How about [" + title + "](" + (toplist[str(rand)]["URL"]) + ") by " + toplist[str(rand)]["Channel"] + "? \n\n[(Reddit link)](" + toplist[str(rand)]["Reddit Link"] + ") \n\nIf you don't like this video, reply with ""!recommend"" and I'll find you another one."
    
    toplist.sync()
    toplist.close()

    return message.format(title=title, URL=URL, channel=channel, permalink=permalink)

def user_is_inactive(user): #works in bot_5
    if user.created_utc > time.time()-(60*60*24*120): #reddit account is LESS than 4 months (182 days) old
        return True

    comment_count = 0 #look for 5 comments in /r/asmr
    submission_ids = set()

    for comment in user.comments.new(limit=1000):
        if comment.created_utc < time.time()-(60*60*24*151): #yielding comments from over 5 months ago
            return True #not enough comments in last 6 months
        elif comment.created_utc > time.time()-(60*60*24*28):
            continue #don't count comments from the past 28 days

        if (comment.subreddit.display_name == "asmr" and 
           (comment.submission.author is None or comment.submission.author.name != user.name) and #don't count comments on own submissions. Count comments on deleted submissions.
            comment.submission.id not in submission_ids): #don't count more than one comment on a given submission
                submission_ids.add(comment.submission.id)
                comment_count += 1 #count comments in r/asmr
                if comment_count >=5:
                    break #enough comments found; continue checks
    else: #didn't break the for loop
        return True #not enough comments in last 6 months

    return False #all tests passed; user is not inactive.

def submission_is_deleted(id):
    """Returns True if a submission has been deleted. Does not work for comments."""
    try:
        submission = r.submission(id = id)
        return (submission.author is None)
    except prawcore.exceptions.NotFound:
        return True

def new_warning(post, banning_mod, reason="", spam_warning=False):
    user = post.author.name.lower()

    reason = "".join(c for c in reason if 32 <= ord(c) <= 125) #filter out weird characters in reason

    if type(banning_mod) != type(""):
        raise TypeError("banning_mod must be of type string")
    
    if user in mod_list:
        raise PermissionError("Error on ban attempt - cannot ban moderator " + user)

    if reason == "spam" and banning_mod != "asmr_bot": # only asmr_bot can give spam warnings, which are identified by the reason of "spam"
        reason = "user was spamming"

    if spam_warning:
        msg_intro = "You have received an automatic warning ban for spamming links to a youtube channel after your post [here]({link}).\n\n"
    else:
        msg_intro = "You have received an automatic warning ban because of your post [here]({link}).\n\n"

    if reason == "":
        reason_text = "The moderator who invoked this ban, /u/{mod}, did not provide a reason for the ban.\n\n"
        if spam_warning:
            reason = "spam"
        else:
            reason = "<No reason provided>"
    else:
        message_reason = reason if reason != "spam" else "Spam - multiple links to same youtube channel in a short period" #only used in the below line:
        reason_text = "The moderator who invoked this ban, /u/{mod}, gave the following reason: \n\n>**" + message_reason + "**\n\n"

    if post.fullname[:2] == "t3": # submission
        link = post.shortlink
    else: # comment
        link = post.permalink

    note = "{mod} - {reason} - {link}".format(mod=banning_mod, reason=reason, link=link)
    msg_intro = msg_intro.format(link=link)
    reason_text = reason_text.format(mod=banning_mod)

    # at this point, got user, note, link, msg_intro, reason_text. 

    warnings_cursor.execute("SELECT * FROM warnings WHERE name=?", [user])
    db_result = warnings_cursor.fetchall()

    previous_bans = len(db_result) # count number of previous bans
    ban_nums = [ban[5] for ban in db_result]

    if previous_bans == 0 and spam_warning:
        ban_number = 0
    else:
        if 0 in ban_nums:
            ban_number = previous_bans
        else:
            ban_number = previous_bans + 1

    if ban_number == 0: #add zeroeth (spam) warning (user only qualifies if no previous warnings)
        reason_text = ""
        duration = 1
        description = ("This warning is to give you an opportunity to read the subreddit and site-wide rules on self-promotion and spam."+
                       "\n\nThis is your soft warning, which is accompanied by a 1-day subreddit ban. " + 
                       "Please take 2 minutes to read [our subreddit rules](/r/asmr/wiki) before participating in the community again.") 
    elif ban_number == 1:
        duration = 7
        description = ("This is your first official warning, which is accompanied by a 7-day subreddit ban. " +
                        "Please take 2 minutes to read [our subreddit rules](/r/asmr/wiki) before participating in the community again. " +
                        "If you message the moderators referencing the rule that you broke and how you broke it, we **may consider** unbanning you early.")
    elif ban_number == 2:
        duration = 30
        description = ("**This is your final warning**, which is accompanied by a 30-day subreddit ban; " +
                        "if you receive another warning, you will be permanently banned. " +
                        "Please take this opportunity to read [our subreddit rules](/r/asmr/wiki) before participating in the community again.")
    elif ban_number >= 2: #should never be >2 though, unless they get a third warning, are then manually unbanned by a mod, then later get another warning
        description = "You have ignored multiple previous warnings and continued to break our subreddit rules, meaning you are now permanently banned."
        duration = None
        
    ban_date = int(time.time())
    msg = msg_intro + reason_text + description
    print("Adding ban for user " + user + ". (reason: " + reason + ")")
    subreddit.banned.add(post.author, duration=duration, note=note, ban_message=msg)

    warnings_cursor.execute("INSERT INTO warnings VALUES(?,?,?,?,?,?)",  [user, link, banning_mod, reason, ban_date, ban_number])
    warnings_db.commit()
    update_warnings_wiki()

    return duration

def is_bad_title(title):
    title = title.lower()
    if any(tag in title for tag in ["[intentional]", "[unintentional]", "[roleplay]", "[role play]"]):
        for phrase in bad_title_phrases:
            if phrase in title:
                return True
    return False

def title_has_two_tags(title):
    title = title.lower()
    two_tags_regex = re.compile('.*\[(intentional|unintentional|roleplay|role play|journalism|discussion|question|meta|request)\].*\[(intentional|unintentional|roleplay|role play|journalism|discussion|question|meta|request)\].*', re.I)
    two_tags = (re.search(two_tags_regex, title) is not None) # search the title for two tags; if two are found set true, else set false

    if two_tags:
       if "[intentional]" in title and ("[roleplay]" in title or "[role play]" in title):
            title = title.replace("[intentional]", "").replace("[roleplay]", "").replace("[role play]", "")
            
            if any(f in title for f in ["[unintentional]", "[journalism]", "[question]", "[discussion]", "[request]", "[meta]"]): # remove detected tags and check if there are still some left
                return True # another tag is found
            else: 
                return False # those were the only ones

            return False # if the two tags are [intentional] and [roleplay] then allow it
       return True # two tags in title but not intentional and roleplay
    else:
        return False

def title_is_caps(title):
    if not any(tag in title.lower() for tag in ["[intentional]", "[unintentional]", "[roleplay]", "[role play]"]):
        return False #only care about triggering submissions - ignore e.g. [discussion] posts

    title = title.replace("ASMR", "") # Remove the string "ASMR"
    title = title.replace("[INTENTIONAL]", "") # Remove the string "INTENTIONAL"
    title = title.replace("[Intentional]", "")
    title = title.replace("[intentional]", "")
    title = title.replace("[UNINTENTIONAL]", "") # Remove the string "UNINTENTIONAL"
    title = title.replace("[Unintentional]", "")
    title = title.replace("[unintentional]", "")
    title = ''.join(char for char in title if char in "etaoinsrhldcufmpgwybvkxjqzABCDEFGHIJKLMNOPQRSTUVWXYZ ")  # Remove anything that isn't alphabetic or a space

    words = title.split(" ")
    tails = []

    for word in words:
        tails.append(word[1:]) #Remove first letter of each word

    normalised_title = "".join(word for word in tails) # merge words back together
    capitals = "".join(char for char in normalised_title if char.upper() == char) # copy only capitals
    
    if len(capitals) >= 2 and len(capitals) >= 0.2 * len(normalised_title): #if capitals are 20% of remaining title
        return True
    else:
        return False

def is_channel_or_playlist_link(url):
    if (   (    ".youtube." in url 
             or "youtu.be"  in url
           )
        and(    "playlist"  in url
             or "list="     in url 
             or "/channel/" in url 
             or "/user/"    in url
           )
       ): # sadface
        return True
    else:
        return False

def is_edit_link(url):
    return "youtube.com/edit" in url

def is_youtube_link(url):
    return ((".youtube." in url or "youtu.be" in url)
            and not("playlist"  in url or
                    "list="     in url or 
                    "/channel/" in url or
                    "/user/"    in url
                   ))
        
def is_roleplay(title, vid_id):
    try:
        title = title.lower()
        rp_types = ["role play", "roleplay", "role-play", " rp "]
        if "[intentional]" in title: # only care about submissions tagged [intentional]
            if any(rp in title for rp in rp_types):
                return True
            else:
                vid_title = get_youtube_video_data("videos", "snippet", "id", vid_id, "title")
                if vid_title != -1:
                    vid_title = vid_title.lower()
                    if "roleplay" in vid_title or "role play" in vid_title:
                        return True
                    else:
                        tags = get_youtube_video_data("videos", "snippet", "id", vid_id, "tags")
                        if tags != -1:
                            return any(rp in tags for rp in rp_types) # true if roleplay in tags; false otherwise
        return False
    except: 
        #don't want any errors to cause a removal
        return False

def purge_thread(comment): #works
    for reply in comment.replies: #lists all replies, replies to replies, etc
        reply.replies.replace_more()
        purge_thread(reply) # recursion is cool
    comment.mod.remove(False)

def remove_ffaf(): # called from schedule where parameters can't be used
    #tested in bot_5, works
    try:
        sticky = subreddit.sticky()
        if "Free-For-All Friday" in sticky.title:
            sticky.mod.sticky(state=False)
        else:
            sticky = subreddit.sticky(number=2) # get second sticky
            if "Free-For-All Friday" in sticky.title:
                sticky.mod.sticky(state=False)
    except prawcore.NotFound as e: # if there's no sticky it'll throw a 404 Not Found
        pass

def clear_user_submissions(): #works
    #Clean up database - only care about submissions in last 24 hours.
    user_submissions_cur.execute("DELETE from user_submissions WHERE SUBMISSION_DATE < ?", [time.time()-86400])

def update_seen_objects(): #works
    with open("seen_comments.txt", "r") as f:
        seen_comments = f.read().split("\n")

    with open("seen_submissions.txt", "r") as f:
        seen_submissions = f.read().split("\n")

    with open("seen_comments.txt", "w") as f:
        f.write("\n".join(id for id in seen_comments[-200:]))

    with open("seen_submissions.txt", "w") as f:
        f.write("\n".join(id for id in seen_submissions[-200:]))

def clear_video_submissions():
    #Clean up database - only care about reposted videos from past 3 months
    recent_videos_cur.execute("DELETE FROM recent_videos WHERE SUBMISSION_DATE < ?", [time.time() - 7948800])

def get_banned_channels(): #tesdted in bot_5, works
    global banned_channels
    try:
        wiki = subreddit.wiki["banned"]
        banned_channels = eval(wiki.content_md)
    except Exception as ex:
        import asmr_bot_data as d # d for data
        banned_channels = d.BANNED_CHANNELS #fall back on known (but probably incomplete) list
        del(d)
        r.redditor("theonefoster").message(subject="Error getting banned channels", message="Exeption when getting banned channels!\n\n" + str(ex) + "\n\n /r/asmr/wiki/banned")

def update_warnings_wiki():
    warnings_cursor.execute("SELECT * FROM warnings")
    db_result = sorted(warnings_cursor.fetchall(), key=lambda x: x[4]) # sort by timestamp

    user_warnings = dict() #dict of form {username: [(ban info)]} 
    warned_user_list = [] #list of users sorted by date first banned

    for war in db_result:
        username, link, mod, reason, date, ban_num = war
        if username not in user_warnings:
            warned_user_list.append(username) # list of users sorted by date first banned
            user_warnings[username] = [(link, mod, reason, str(date), ban_num)]
        else:
            bans = user_warnings[username] # must be of length >= 1
            bans.append((link, mod, reason, date, ban_num))
            user_warnings[username] = bans

    header = "**This page is READ-ONLY - the bot will ignore and overwrite anything changed here. This page is for information about past bans only. To add a warning use the `!warning <reason>` comand. To permanently ban a user use the `!ban <reason>` command.**"
    page = header + "\n\nName | Post | Banned by | Reason for ban | Date banned | Status\n---|---|---|---|---|---\n"

    for user in warned_user_list:
        bans = user_warnings[user]
        warnings = len(bans)

        page += "/u/" + user

        readable_date = lambda x: str(datetime.datetime.fromtimestamp(int(x)).strftime('%Y-%m-%d'))
       
        for ban in bans:
            link, mod, reason, date, ban_number = ban
            if ban_number == 0:
                status = "Spam warning"
            elif ban_number == 1:
                status = "First warning"
            elif ban_number == 2:
                status = "LAST warning"
            else:
                status = "Permanent"

            reason = "".join(c for c in reason if 32 <= ord(c) <= 125) #filter out weird characters in reason

            page += " | " + link + " | " + "/u/" + mod + " | " + reason + " | " + readable_date(date) + " | " + status + "\n"

    subreddit.wiki["warnings"].edit(page)

def user_is_subreddit_banned(username): #tested, works
    banned = subreddit.banned()
    names = [user.name.lower() for user in banned]

    return username.lower() in names

## ----------------------------
## END OF FUNCTIONS
## ----------------------------

r = praw.Reddit("asmr_bot")
print("Logged in as ", end="")
print(r.user.me())
subreddit = r.subreddit("asmr")
lounge = r.subreddit("asmrcreatorlounge")

###### TEST CODE GOES HERE

###### END OF TEST CODE

if __name__ == "__main__":
    tof = praw.Reddit("theonefoster")
    
    print("Fetching banned channels..")
    get_banned_channels()
    update_warnings_wiki()

    schedule.every().thursday.at("23:50").do(remove_ffaf)
    schedule.every(14).days.at("03:00").do(update_top_submissions) # once per fortnight
    schedule.every().hour.do(clear_user_submissions)
    schedule.every().day.do(update_seen_objects)
    schedule.every().day.at("02:00").do(clear_video_submissions) # once per day
    schedule.every(4).hours.do(get_banned_channels) # 6 times per day

    print("Updating submissions files..")
    clear_user_submissions()
    clear_video_submissions()
    update_seen_objects()

    print("Setup complete. Starting bot duties.")

    exponential_dropoff = 5

    while True:
        try:
            check_submissions()
            check_comments()
            check_mod_queue()
            check_messages()
            schedule.run_pending()
            exponential_dropoff = 5
        except prawcore.exceptions.ServerError as e:
            print("Server Exception: " + str(e))
            #traceback.print_exc()
            time.sleep(exponential_dropoff) #usually 503 so just try again soon
            exponential_dropoff *= 2
        except Exception as e:
            print("Unknown exception: " + str(e))
            if "Read timed out" not in str(e): #don't care about reddit 503
                traceback.print_exc()
            print("Sleeping..")
            time.sleep(30) #unknown error.
        finally:
            first_run = False
            time.sleep(9) # reduces reddit load and unnecessary processor usage
