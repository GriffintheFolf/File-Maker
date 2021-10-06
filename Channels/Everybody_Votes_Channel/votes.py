#!/usr/bin/python
# -*- coding: utf-8 -*-

# ===========================================================================
# EVERYBODY VOTES CHANNEL GENERATION SCRIPT
# AUTHORS: JOHN PANSERA, LARSEN VALLECILLO
# ***************************************************************************
# Copyright (c) 2015-2021 RiiConnect24, and its (Lead) Developers
# ===========================================================================

import binascii
import calendar
import CloudFlare
import datetime
import json
import logging
import nlzss
import os
import struct
import subprocess
import sys
import textwrap
import time

import MySQLdb
import requests
import rsa

from utils import setup_log, log, u8, u16, u32
from Channels.Everybody_Votes_Channel.voteslists import *

with open("./Channels/Everybody_Votes_Channel/config.json", "rb") as f:
    config = json.load(f)

if config["production"]: setup_log(config["sentry_url"], True)

print("Everybody Votes Channel File Generator \n")
print("By John Pansera / Larsen Vallecillo / www.rc24.xyz \n")

worldwide = 0
national = 0
national_results = 0
worldwide_results = 0
question_data = collections.OrderedDict()
results = collections.OrderedDict()
country_code = 49
country_count = 0
language_code = 1
languages = {}
num = 0
number = 0
file_type = sys.argv[1]

if file_type != "v":
    arg = sys.argv[2]
else:
    arg = None

def get_timestamp(mode, type, date):
    if mode == 0:
        timestamp = int((time.time() - 946684800) / 60)
    elif mode == 1 or mode == 2:
        timestamp = int((time.mktime(date.timetuple()) - 946684800) / 60 + 120)
        if mode == 2:
            if config["production"]:
                if type == "n":
                    timestamp += 10080
                elif type == "w":
                    timestamp += 21600
            else:
                timestamp += 5
    return timestamp


def days_ago():
    return 7 if national_results > 0 else 14 if worldwide_results > 0 else 0


def get_name():
    now = datetime.datetime.now() - datetime.timedelta(days=days_ago())
    day = str(now.day).zfill(2)
    month = str(now.month).zfill(2)
    return month + day


def get_year():
    now = datetime.datetime.now() - datetime.timedelta(days=days_ago())
    year = str(now.year)
    return year


def pad(amnt): return b"\0" * amnt


def prepare():
    global country_count, countries, questions, poll_id, results, position, national, worldwide
    print("Preparing ...")
    mysql_connect()
    if len(sys.argv) == 1:
        manual_run()
    elif len(sys.argv) >= 2:
        if file_type == "q":
            automatic_questions()
        elif file_type == "r":
            automatic_results()
        elif file_type == "v":
            automatic_votes()
    cnx.close()
    make_language_table()


"""Automatically run the scripts. This will be what the crontab uses."""


def automatic_questions():
    global write_results, questions
    if arg == "n":
        days = 7
    elif arg == "w":
        days = 15
    mysql_get_questions(days, 1, arg)
    question_sort()
    questions = 1


def automatic_results():
    global results, national, worldwide, questions, national_results, worldwide_results
    if arg == "n":
        days = 7
    elif arg == "w":
        days = 15
    results[poll_id] = mysql_get_votes(days, arg, 1)
    try:
        del results[None]
    except KeyError:
        pass
    national = 0
    worldwide = 0
    questions = 0


def automatic_votes():
    global questions, results, national, worldwide, questions
    mysql_get_questions(15, 1, "w")
    mysql_get_questions(7, 3, "n")
    question_sort()
    questions = national + worldwide
    question_count = len(question_data)
    print("Loaded %s %s" % (question_count, "Question" if question_count == 1 else "Questions"))
    for v in list(reversed(list(range(1, 7)))):
        results[poll_id] = mysql_get_votes(7, "n", v)
    results[poll_id] = mysql_get_votes(15, "w", 1)
    try:
        del results[None]
    except KeyError:
        pass

def question_sort():
    global question_keys
    question_keys = sorted(question_data.keys())

    for q in question_keys:
        if get_type(q) == "w": # put the worldwide questions at the end
            question_keys.remove(q)
            question_keys.append(q)

def mysql_connect():
    print("Connecting to MySQL ...")
    try:
        global cnx
        cnx = MySQLdb.connect(user=config["mysql_user"], password=config["mysql_password"],
                                      host='127.0.0.1',
                                      database=config["mysql_database"],
                                      charset='utf8',
                                      use_unicode=True)
    except:
        sys.exit(1)

def mysql_get_votes(days, vote_type, index):
    cursor = cnx.cursor()
    query = "SELECT questionID from rc24_EVC.questions WHERE DATE(date) <= CURDATE() - INTERVAL %s DAY AND type = '%s' ORDER BY questionID DESC" % (days, vote_type)
    cursor.execute(query)
    global poll_id, poll_type

    i = 0

    while i < index:
        row = cursor.fetchone()
        if row is None:
            poll_id = None
            return None
        i += 1

    poll_id = row[0]
    query = "SELECT * from rc24_EVC.votes WHERE questionID = %s"
    cursor.execute(query, [poll_id])

    global national_results, worldwide_results

    if vote_type == "n":
        national_results += 1
    elif vote_type == "w":
        worldwide_results += 1

    # initialize blank lists to store votes in

    male_voters_response_1 = [0] * 34
    female_voters_response_1 = [0] * 34
    male_voters_response_2 = [0] * 34
    female_voters_response_2 = [0] * 34

    region_response_1 = [0] * 34
    region_response_2 = [0] * 34

    for k, v in list(region_number.items()):
        region_response_1[country_codes.index(k)] = [0] * v
        region_response_2[country_codes.index(k)] = [0] * v

    predict_response_1 = [0] * 34
    predict_response_2 = [0] * 34

    """Grab the votes from the database."""

    for row in cursor:
        if row[4] == 99:
            continue
        country_index = country_codes.index(row[4])
        anscnt = str(row[6]).zfill(4)
        region_id = row[5] - 2

        if row[1] == 0:
            try:
                male_voters_response_1[country_index] += int(anscnt[0])
                female_voters_response_1[country_index] += int(anscnt[1])
                male_voters_response_2[country_index] += int(anscnt[2])
                female_voters_response_2[country_index] += int(anscnt[3])

                region_response_1[country_index][region_id] += int(anscnt[0]) + int(anscnt[1])
                region_response_2[country_index][region_id] += int(anscnt[2]) + int(anscnt[3])
            except:
                pass
        elif row[1] == 1:
            try:
                predict_response_1[country_index] += int(anscnt[0]) + int(anscnt[1])
                predict_response_2[country_index] += int(anscnt[2]) + int(anscnt[3])
            except:
                pass

    # print("Male Voters Response 1: %s" % male_voters_response_1)
    # print("Female Voters Response 1: %s" % female_voters_response_1)
    # print("Male Voters Response 2: %s" % male_voters_response_2)
    # print("Female Voters Response 2: %s" % female_voters_response_2)
    # print("Predict Response 1: %s" % predict_response_1)
    # print("Predict Response 2: %s" % predict_response_2)
    # print("Region Response 1: %s" % region_response_1)
    # print("Region Response 2: %s" % region_response_2)

    cursor.close()

    return [male_voters_response_1, female_voters_response_1,
            male_voters_response_2, female_voters_response_2,
            predict_response_1, predict_response_2,
            region_response_1, region_response_2,
            vote_type]


def mysql_get_questions(days, count, vote_type):
    cursor = cnx.cursor()
    query = "SELECT * from rc24_EVC.questions WHERE DATE(date) > CURDATE() - INTERVAL %s DAY AND DATE(date) <= CURDATE() AND type = '%s' ORDER BY questionID DESC" % (days, vote_type)

    cursor.execute(query)

    i = 0

    while i < count:
        row = cursor.fetchone()
        if row is None: break
        add_question(row)
        i += 1

    cursor.close()


def num():
    global number
    num1 = number
    number += 1
    return num1


def get_question(id, language_code): return question_data[id][0][language_code]


def get_response1(id, language_code): return question_data[id][1][language_code]


def get_response2(id, language_code): return question_data[id][2][language_code]


def get_type(id): return question_data[id][3]


def get_category(id): return question_data[id][4]


def get_date(id): return question_data[id][5]


def add_question(row):
    global question_data, national, worldwide

    i = 0

    question = [[None] * 9, [None] * 9, [None] * 9, None, None, None]

    for r in row:
        if row[i] is not None:
            if i >= 1 and i <= 9:
                question[0][i - 1] = question_text_replace(row[i])
            elif i >= 10 and i <= 18:
                question[1][i - 10] = question_text_replace(row[i])
            elif i >= 19 and i <= 27:
                question[2][i - 19] = question_text_replace(row[i])
            elif i > 27:
                question[i - 25] = row[i]
        i += 1

    question_data[row[0]] = question

    if row[28] == "n":
        national += 1
    elif row[28] == "w":
        worldwide += 1


# this will fix the "..." on the questions, and wrap the text correctly so words aren't cut off


def question_text_replace(text):
    text = text.replace("\u2026", " . . .").replace("...", " . . .")
    text = "\\n".join(textwrap.wrap(text, 50))
    for i in range(1, 4):
        text = text.replace(" .\\n", "\\n .")
    return text


def webhook():
    for q in question_keys:
        if get_type(q) == "n":
            webhook_type = "national"
        elif get_type(q) == "w":
            webhook_type = "worldwide"
        webhook_text = "New %s Everybody Votes Channel question is out!\n\n%s (%s / %s)" % (
            webhook_type, get_question(q, 1), get_response1(q, 1), get_response2(q, 1))
        if config["production"]:
                data = {"username": "Votes Bot",
                               "content": "New %s Everybody Votes Channel question is out!" % type,
                               "avatar_url": "http://rc24.xyz/images/logo-small.png", "attachments": [
                {"fallback": "Everybody Votes Channel Data Update", "color": "#68C7D0",
                 "author_name": "RiiConnect24 Everybody Votes Channel Script",
                 "author_icon": "https://rc24.xyz/images/webhooks/votes/profile.png", "text": webhook_text,
                 "title": "Update!",
                 "fields": [{"title": "Script", "value": "Everybody Votes Channel", "short": "false"}],
                 "thumb_url": "https://rc24.xyz/images/webhooks/votes/vote_%s.png" % webhook_type,
                 "footer": "RiiConnect24 Script", "footer_icon": "https://rc24.xyz/images/logo-small.png",
                 "ts": int(calendar.timegm(datetime.datetime.utcnow().timetuple()))}]}
        for url in config["webhook_urls"]:
            post_webhook = requests.post(url, json=data, allow_redirects=True)

def purge_cache():
    if config["production"]:
        if config["cloudflare_cache_purge"]:
            print("Purging cache...")

            for country_code in country_codes:
                purge_list = []

                url = "http://{}/{}/".format(
                    config["cloudflare_hostname"],
                    str(country_code).zfill(3),
                )

                purge_list.append(url + "voting.bin")

            cf = CloudFlare.CloudFlare(token=config["cloudflare_token"])

            cf.zones.purge_cache.post(
                config["cloudflare_zone_name"],
                data={"files": purge_list},
            )

dictionaries = []


def offset_count(): return u32(12 + sum(len(values) for dictionary in dictionaries for values in list(dictionary.values()) if values))


def sign_file(name):
    final = name + '.bin'
    print("Processing " + final + " ...")
    file = open(name, 'rb')
    copy = file.read()
    file.close()
    print("Calculating CRC32 ...")
    crc32 = format(binascii.crc32(copy) & 0xFFFFFFFF, '08x')
    print("Calculating Size ...")
    size = os.path.getsize(name) + 12
    dest = open(final + '-1', 'wb+')
    dest.write(u32(0))
    dest.write(u32(size))
    dest.write(binascii.unhexlify(crc32))
    dest.write(copy)
    os.remove(name)
    dest.close()
    print("Compressing ...")
    nlzss.encode_file(final + '-1', final + '-1')
    file = open(final + '-1', 'rb')
    new = file.read()
    dest = open(final, "wb+")
    key = open(config["key_path"], 'rb')
    print("RSA Signing ...")
    private_key = rsa.PrivateKey.load_pkcs1(key.read(), "PEM")  # Loads the RSA key.
    signature = rsa.sign(new, private_key, "SHA-1")  # Makes a SHA1 with ASN1 padding. Beautiful.
    dest.write(b"\0" * 64)  # Padding. This is where data for an encrypted WC24 file would go (such as the header and IV), but this is not encrypted so it's blank.
    dest.write(signature)
    dest.write(new)
    dest.close()
    file.close()
    key.close()
    if config["production"]:
        if file_type == "q" or file_type == "r":
            if arg == "n":
                folder = str(country_code).zfill(3)
            elif arg == "w":
                folder = "world"
            subprocess.call(["mkdir", "-p", "%s/%s/%s" % (
                config["file_path"], folder, get_year())])  # If folder for the year does not exist, make it.
            path = "/".join([config["file_path"], folder, get_year(), final])
        elif file_type == "v":
            path = "/".join([config["file_path"], str(country_code).zfill(3), ""])
            if config["packVFF"]:
                os.makedirs(path + "wc24dl", exist_ok=True)
                with open(path + "voting.bin", "rb") as source:
                    with open(path + "wc24dl/VOTING.BIN", "wb") as dest:
                            dest.write(source.read()[320:])
                subprocess.call(
                    [
                        config["winePath"],
                        config["prfArcPath"],
                        "-v",
                        "64",
                        path + "wc24dl",
                        path + "wc24dl.vff",
                    ],
                    stdout=subprocess.DEVNULL,
                )  # Pack VFF
                
                os.remove(path + "wc24dl/VOTING.BIN")
                os.rmdir(path + "wc24dl")
            path += final
    subprocess.call(["mv", final, path])
    os.remove(final + '-1')


def make_bin(country_code):
    global countries
    print("Processing ...")
    voting = make_header()

    if file_type == "v" or file_type == "q":
        make_national_question_table(voting)
        make_worldwide_question_table(voting)
        question_text_table = make_question_text_table(voting)

    if file_type == "v" or file_type == "r" and national_results > 0:
        make_national_result_table(voting)
        make_national_result_detailed_table(voting)
        make_position_entry_table(voting)

    if file_type == "v" or file_type == "r" and worldwide_results > 0:
        make_worldwide_result_table(voting)
        make_worldwide_result_detailed_table(voting)

    if file_type == "v" or file_type == "r" and national_results == 0:
        country_table = make_country_name_table(voting)

    if file_type == "v" or file_type == "q":
        make_question_text(question_text_table)

    if file_type == "v" or file_type == "r" and national_results == 0:
        make_country_table(country_table)

    if file_type == "q" or file_type == "r":
        question_file = get_name() + "_" + file_type

    else:
        question_file = "voting"
    
    print("Writing to %s.bin ..." % question_file)

    with open(question_file, "wb") as f:
        for dictionary in dictionaries:
            # print("Writing to %s ..." % hex(f.tell()).rstrip("L"))
            for name, values in dictionary.items():
                f.write(values)
        f.write(pad(16))
        f.write('RIICONNECT24'.encode("ASCII"))
        f.flush()

    if config["production"]:
        sign_file(question_file)

    if file_type == "v":
        purge_cache()

    print("Writing Completed")

    for dictionary in dictionaries:
        dictionary.clear()

def make_header():
    header = collections.OrderedDict()
    dictionaries.append(header)

    header["timestamp"] = u32(get_timestamp(0, None, None))
    header["country_code"] = u8(country_code)
    header["publicity_flag"] = u8(0)
    header["question_version"] = u8(0 if file_type == "r" else 1)
    header["result_version"] = u8(1 if file_type == "r" else 0)
    header["national_question_number"] = u8(national)
    header["national_question_offset"] = u32(0)
    header["worldwide_question_number"] = u8(worldwide)
    header["worldwide_question_offset"] = u32(0)
    header["question_number"] = u8(questions * len(country_language[country_code]))
    header["question_offset"] = u32(0)
    header["national_result_entry"] = u8(national_results)
    header["national_result_offset"] = u32(0)
    header["national_result_detailed_number"] = u16(national_results * region_number[country_code])
    header["national_result_detailed_offset"] = u32(0)
    header["position_number"] = u16(0 if file_type == "q" or national_results == 0 else 22 if country_code == 77 else len(position_table[country_code]) if country_code in list(position_table.keys()) else 0)
    header["position_offset"] = u32(0)
    header["worldwide_result_number"] = u8(worldwide_results)
    header["worldwide_result_offset"] = u32(0)
    header["worldwide_result_detailed_number"] = u16(0)
    header["worldwide_result_detailed_offset"] = u32(0)
    header["country_name_number"] = u16(len(countries) * 7 if file_type == "r" and arg == "w" else 0 if file_type == "q" or file_type == "r" else len(countries) * 7)
    header["country_name_offset"] = u32(0)

    return header


def make_national_question_table(header):
    global national
    national_question_table = collections.OrderedDict()
    dictionaries.append(national_question_table)

    question_table_count = 0

    for q in question_keys:
        if get_type(q) == "n":
            if header["national_question_offset"] == u32(0):
                header["national_question_offset"] = offset_count()
            national_question_table["poll_id_%s" % num()] = u32(q)
            national_question_table["poll_category_1_%s" % num()] = u8(get_category(q))
            national_question_table["poll_category_2_%s" % num()] = u8(categories[get_category(q)])
            national_question_table["opening_timestamp_%s" % num()] = u32(get_timestamp(1, "n", get_date(q)))
            national_question_table["closing_timestamp_%s" % num()] = u32(get_timestamp(2, "n", get_date(q)))
            national_question_table["question_table_count_%s" % num()] = u8(len(country_language[country_code]))
            national_question_table["question_table_start_%s" % num()] = u32(question_table_count)
            question_table_count += len(country_language[country_code])

    return national_question_table


def make_worldwide_question_table(header):
    global worldwide
    worldwide_question_table = collections.OrderedDict()
    dictionaries.append(worldwide_question_table)

    question_table_start = 0
    for q in question_keys:
        if get_type(q) == "w":
            if header["worldwide_question_offset"] == u32(0):
                header["worldwide_question_offset"] = offset_count()
        if file_type == "v":
            question_table_start = len(country_language[country_code]) * national

    if file_type == "v":
        question_table_count = len(country_language[country_code])
    elif file_type == "q":
        question_table_count = 9

    for q in question_keys:
        if get_type(q) == "w":
            worldwide_question_table["poll_id_%s" % num()] = u32(q)
            worldwide_question_table["poll_category_1_%s" % num()] = u8(get_category(q))
            worldwide_question_table["poll_category_2_%s" % num()] = u8(categories[get_category(q)])
            worldwide_question_table["opening_timestamp_%s" % num()] = u32(get_timestamp(1, "w", get_date(q)))
            worldwide_question_table["closing_timestamp_%s" % num()] = u32(get_timestamp(2, "w", get_date(q)))
            worldwide_question_table["question_table_count_%s" % num()] = u8(question_table_count)
            worldwide_question_table["question_table_start_%s" % num()] = u32(question_table_start)
            question_table_count += 1

    return worldwide_question_table


def make_question_text_table(header):
    global questions
    question_text_table = collections.OrderedDict()
    dictionaries.append(question_text_table)

    header["question_offset"] = offset_count()

    for q in question_keys:
        if get_type(q) == "w":
            if file_type == "v":
                poll_list = country_language[country_code]
            elif file_type == "q":
                poll_list = list(range(1, 9))
        elif get_type(q) == "n":
            poll_list = country_language[country_code]
        for language_code in poll_list:
            if get_question(q, language_code) is not None:
                num = question_keys.index(q)
                question_text_table["language_code_%s_%s" % (num, language_code)] = u8(language_code)
                question_text_table["question_offset_%s_%s" % (num, language_code)] = u32(0)
                question_text_table["response_1_offset_%s_%s" % (num, language_code)] = u32(0)
                question_text_table["response_2_offset_%s_%s" % (num, language_code)] = u32(0)

    return question_text_table


def make_national_result_table(header):
    table = collections.OrderedDict()
    dictionaries.append(table)

    national_result_detailed_number_count = 0
    national_result_detailed_number_tables = region_number[country_code]
    header["national_result_offset"] = offset_count()

    for i in results:
        if results[i][8] == "n":
            country_index = country_codes.index(country_code)

            table["poll_id_%s" % num()] = u32(i)
            table["male_voters_response_1_num_%s" % num()] = u32(results[i][0][country_index])
            table["male_voters_response_2_num_%s" % num()] = u32(results[i][2][country_index])
            table["female_voters_response_1_num_%s" % num()] = u32(results[i][1][country_index])
            table["female_voters_response_2_num_%s" % num()] = u32(results[i][3][country_index])
            table["predictors_response_1_num_%s" % num()] = u32(results[i][4][country_index])
            table["predictors_response_2_num_%s" % num()] = u32(results[i][5][country_index])
            table["show_voter_number_flag_%s" % num()] = u8(1)
            table["detailed_results_flag_%s" % num()] = u8(1)
            table["national_result_detailed_number_number_%s" % num()] = u8(national_result_detailed_number_tables)
            table["starting_national_result_detailed_number_table_number_%s" % num()] = u32(national_result_detailed_number_count)
            national_result_detailed_number_count += national_result_detailed_number_tables

    return table


def make_national_result_detailed_table(header):
    table = collections.OrderedDict()
    dictionaries.append(table)

    header["national_result_detailed_offset"] = offset_count()

    for i in results:
        if results[i][8] == "n":
            for j in range(region_number[country_code]):
                country_index = country_codes.index(country_code)
                table["voters_response_1_num_%s" % num()] = u32(results[i][6][country_index][j])
                table["voters_response_2_num_%s" % num()] = u32(results[i][7][country_index][j])
                table["position_entry_table_count_%s" % num()] = u8(0 if (results[i][6][country_index][j] == 0 and results[i][7][country_index][j] == 0) or (country_code not in list(position_table.keys())) else position_table[country_code][j])
                table["starting_position_entry_table_%s" % num()] = u32(sum(position_table[country_code][:j]) if country_code in list(position_table.keys()) else 0)

    return table


def make_position_entry_table(header):
    table = collections.OrderedDict()
    dictionaries.append(table)

    if country_code in list(position_table.keys()):
        header["position_offset"] = offset_count()
        table["data_%s" % num()] = binascii.unhexlify(position_data[country_code])


def make_worldwide_result_table(header):
    table = collections.OrderedDict()
    dictionaries.append(table)

    worldwide_detailed_table_count_all = 0
    header["worldwide_result_offset"] = offset_count()

    for i in results:
        if results[i][8] == "w":
            worldwide_detailed_table_count = 0
            for j in range(len(countries)):  # 33
                total = 0
                for voters in range(0, 4):
                    total += results[i][voters][j]
                if total > 0:
                    worldwide_detailed_table_count += 1

            table["poll_id_%s" % num()] = u32(i)
            table["male_voters_response_1_num_%s" % num()] = u32(sum(results[i][0]))
            table["male_voters_response_2_num_%s" % num()] = u32(sum(results[i][2]))
            table["female_voters_response_1_num_%s" % num()] = u32(sum(results[i][1]))
            table["female_voters_response_2_num_%s" % num()] = u32(sum(results[i][3]))
            table["predictors_response_1_num_%s" % num()] = u32(sum(results[i][4]))
            table["predictors_response_2_num_%s" % num()] = u32(sum(results[i][5]))
            table["total_worldwide_detailed_tables_%s" % num()] = u8(worldwide_detailed_table_count)
            table["starting_worldwide_detailed_table_number_%s" % num()] = u32(worldwide_detailed_table_count_all)
            worldwide_detailed_table_count_all += worldwide_detailed_table_count

    return table


def make_worldwide_result_detailed_table(header):
    table = collections.OrderedDict()
    dictionaries.append(table)

    country_table_count = 0
    header["worldwide_result_detailed_offset"] = offset_count()

    worldwide_region_number = 0

    for i in results:
        if results[i][8] == "w":
            for j in range(len(countries)):  # 33
                total = 0
                for voters in range(0, 4):
                    total += results[i][voters][j]
                if total > 0:
                    table["unknown_%s" % num()] = u32(0)
                    table["male_voters_response_1_num_%s" % num()] = u32(results[i][0][j])
                    table["male_voters_response_2_num_%s" % num()] = u32(results[i][2][j])
                    table["female_voters_response_1_num_%s" % num()] = u32(results[i][1][j])
                    table["female_voters_response_2_num_%s" % num()] = u32(results[i][3][j])
                    table["country_table_count_%s" % num()] = u16(7)
                    table["starting_country_table_number_%s" % num()] = u32(country_table_count)
                    worldwide_region_number += 1
                country_table_count += 7

    header["worldwide_result_detailed_number"] = u16(worldwide_region_number)

    return table


def make_country_name_table(header):
    global countries
    country_name_table = collections.OrderedDict()
    dictionaries.append(country_name_table)

    header["country_name_offset"] = offset_count()

    for k in list(countries.keys()):
        num = list(countries.keys()).index(k)
        for i in range(len(languages)):
            country_name_table["language_code_%s_%s" % (num, i)] = u8(i)
            country_name_table["text_offset_%s_%s" % (num, i)] = u32(0)

    return country_name_table


def make_language_table():  # Default channel language table
    global languages
    languages["Japanese"] = 0
    languages["English"] = 1
    languages["German"] = 2
    languages["French"] = 3
    languages["Spanish"] = 4
    languages["Italian"] = 5
    languages["Dutch"] = 6


def make_country_table(country_name_table):
    country_table = collections.OrderedDict()
    dictionaries.append(country_table)

    j = 0
    for k in list(countries.keys()):
        num = list(countries.keys()).index(k)
        for i in range(len(languages)):
            country_name_table["text_offset_%s_%s" % (num, i)] = offset_count()
            country_table[j] = countries[k][i].encode("utf-16be") + pad(2)
            j += 1

    return country_table


def make_question_text(question_text_table):
    global question_data
    question_text = collections.OrderedDict()
    dictionaries.append(question_text)

    for q in question_keys:
        for language_code in country_language[country_code]:
            if get_question(q, language_code) is not None:
                num = question_keys.index(q)
                question_text_table["question_offset_%s_%s" % (num, language_code)] = offset_count()
                question_text["question_%s_%s" % (num, language_code)] = get_question(q, language_code).encode("utf-16be")
                question_text["question_pad_%s_%s" % (num, language_code)] = pad(2)
                question_text_table["response_1_offset_%s_%s" % (num, language_code)] = offset_count()
                question_text["response_1_%s_%s" % (num, language_code)] = get_response1(q, language_code).encode("utf-16be")
                question_text["response_1_pad_%s_%s" % (num, language_code)] = pad(2)
                question_text_table["response_2_offset_%s_%s" % (num, language_code)] = offset_count()
                question_text["response_2_%s_%s" % (num, language_code)] = get_response2(q, language_code).encode("utf-16be")
                question_text["response_2_pad_%s_%s" % (num, language_code)] = pad(2)

    return question_text


prepare()
if arg != "w":
    for country_code in country_codes:
        make_bin(country_code)
else:
    make_bin(country_code)

if file_type == "q":
    webhook()

print("Completed Successfully")
