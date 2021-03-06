import logging
import requests
import re
from lxml import etree
# from lxml.html.clean import Cleaner
from io import StringIO
import difflib
import webbrowser
import os
import argparse
from urllib.parse import urlparse
from http.cookies import SimpleCookie
from hashlib import md5
import time
import copy
import json
import urllib3
from lxml import html
from colorama import Back, Style
import colorama

colorama.init()
logging.basicConfig(filename="ivdiff.log", level=logging.INFO)
htmlparser = etree.HTMLParser(remove_blank_text=True)
# cleaner = Cleaner(style=True)
verify = False
if not verify:
    urllib3.disable_warnings()


global unpaused
unpaused = None


def diffonlyParse(rules, template, reverse=False):
    r = rules.splitlines()
    domode = 0
    ff = []
    lines = ""
    variables = {}
    for j in r:
        i = j.strip()
        if i.startswith("##"):
            args = i[2:].split(" ")
            ff = args[1:]
            for i in variables:
                v = variables[i]
                if i in ff:
                    ff.append(v)

            if args[0] == "do":
                # print("diffonly start")
                domode = 1
                if reverse or (len(ff) > 0 and str(template) not in ff):
                    # print("REVERSE")
                    domode = -domode
            elif args[0] == "?":
                # print("else")
                domode = -domode
            elif args[0] == "cdo":
                # print("comment diffonly start")
                domode = -1
                if reverse or (len(ff) > 0 and str(template) not in ff):
                    # print(ff)
                    # print(template)
                    # print("REVERSE")
                    domode = -domode
            elif args[0] == "" and len(args) == 1:
                # print("end")
                domode = 0
            elif args[0] == "s":
                variables[args[1]] = args[2]
                # print(variables)
        else:
            if domode == 1:
                # print(f"uncomment line {j}")
                j = re.sub(r"^(\s*)#+(.*)$", "\\1\\2", j)
            elif domode == -1:
                # print(f"comment line {j}")
                if re.match(r"^(\s*)#+(.*)$", j) is None:
                    j = "#" + j
        lines += j + "\n"
    # print(lines)
    return lines


def getHtml(domain, cookies, url, template, c_with=None):
    rules = ""
    if template != "~":
        try:
            templNumber = str(int(template))
            contest = "contest"
        except ValueError:
            la = open(template, "r", encoding='utf8')
            rules = str(la.read())
            la.close()
            contest = "my"
            templNumber = ""
    else:
        contest = "my"
        templNumber = ""

    if contest == "my":
        d = "https://instantview.telegram.org/{}/{}".format(contest, domain)
    else:
        d = "https://instantview.telegram.org/{}/{}/template{}".format(contest, domain, templNumber)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:65.0) Gecko/20100101 Firefox/65.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": d,
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "max-age=0"
    }
    logging.info("-- Getting html for {} --".format(url.encode("ascii")))
    # print("-- Getting html for {} --".format(url.encode("ascii")))

    if contest == "my" and template == "~":
        all = getHashAndRules(domain, url, cookies)
        rules = diffonlyParse(all[0], c_with, c_with == template)
        hash = all[1]
        cookies = all[2]
        if len(rules) < 10:
            print(f"CRITICAL ERROR RULES EMPTY! {rules}")
            return None
    else:
        r = requests.get(d, headers=headers, verify=verify, cookies=cookies, params=dict(url=url))
        cookies = dict(list(cookies.items()) + list(r.cookies.get_dict().items()))

        hash = re.search("{}\\?hash=(.*?)\",".format(contest), str(r.content)).group(1)
    # logging.info("hash={}".format(hash))
    # print(f"got hash {hash}")

    rules = rules.encode('utf-8')
    headers["X-Requested-With"] = "XMLHttpRequest"
    headers["Accept"] = "application/json, text/javascript, */*; q=0.01"
    r = requests.post("https://instantview.telegram.org/api/{}".format(contest), headers=headers, verify=verify, cookies=cookies, params=dict(hash=hash), data=dict(url=url, section=domain, method="processByRules", rules_id=templNumber, rules=rules, random_id=""))
    random_id = r.json()["random_id"]
    # logging.info("random_id={}".format(random_id))
    # print(f"got random id {random_id}")

    final = ""
    fail = time.time()
    lastTry = False
    # total_fail = 0
    while "result_doc_url" not in final:
        r = requests.post("https://instantview.telegram.org/api/{}".format(contest), headers=headers, verify=verify, cookies=cookies, params=dict(hash=hash), data=dict(url=url, section=domain, method="processByRules", rules_id=templNumber, rules=rules, random_id=random_id))
        final = r.json()
        try:
            random_id = final["random_id"]

            # if "status" not in final:
            if "result_doc_url" not in final:
                # print(time.time() - fail)
                if time.time() - fail >= 5:
                    if lastTry:
                        # print(f"struggling on page for more than 10 seconds, trying from start in 45s {url}")
                        print(Back.LIGHTRED_EX + "5" + Style.RESET_ALL, end="")
                        return None

                    # print(f"struggling on page for more than 5 seconds, trying without random_id {url}")
                    random_id = ""
                    lastTry = True
                    fail = time.time()

        except Exception as ex:
            print(f"{ex} {final}")

    random_id = final["random_id"]
    u = final["result_doc_url"]
    preview_html = final["preview_html"]

    logging.info("loading page {}".format(u))
    r = requests.get(u, verify=verify, cookies=cookies)
    if r.status_code != 200:
        print(f"{r.status_code}, trying again {url}")
        return None
    error = ""

    if "NESTED_ELEMENT_NOT_SUPPORTED" in str(r.content):
        # print(Back.LIGHTRED_EX + "N" + Style.RESET_ALL, end="")
        error = Back.LIGHTRED_EX + "N" + Style.RESET_ALL
        print(error, end="")
        logging.error("NESTED_ELEMENT_NOT_SUPPORTED in {}".format(url.encode("ascii")))
    if "PAGE_NOT_FETCHED" in str(r.content):
        error = Back.RED + "P" + Style.RESET_ALL
        print(error, end="")
        logging.error("PAGE_NOT_FETCHED in {}".format(url.encode("ascii")))
    b = r.content.decode("utf-8").replace(u"\xa0", " ")
    b = re.sub(' +', ' ', b)
    tree = etree.parse(StringIO(b), htmlparser)
    if preview_html is not False:
        preview_html_tree = etree.parse(StringIO(preview_html), htmlparser)
    else:
        preview_html_tree = None
    # remove nbsp and bullshit
    # tree = cleaner.clean_html(tree)

    logging.info("-- FINISHED --")
    return (d + "?url=" + url, tree, preview_html_tree, cookies)


def compare(f, s):
    # You can remove elements before diff if you want to

    # for bad in s.xpath("//h6[@data-block=\"Kicker\"]"):
    #     bad.getparent().remove(bad)
    # for bad in f.xpath("//footer[last()]"):
    #    bad.getparent().remove(bad)
    # for bad in f.xpath("//*[contains(@class, \"related\")]"):
    #     # del bad.attrib["href"]
    #     # del bad.attrib["target"]
    #     # del bad.attrib["onclick"]
    #     bad.getparent().remove(bad)
    # for bad in s.xpath("//*[contains(@class, \"related\")]"):
    #     # del bad.attrib["href"]
    #     # del bad.attrib["target"]
    #     # del bad.attrib["onclick"]
    #     bad.getparent().remove(bad)
    for bad in f.xpath("//article/address//a[@rel=\"author\"]"):
        try:
            del bad.attrib["href"]
            del bad.attrib["target"]
            del bad.attrib["onclick"]
        except Exception:
            pass

    # for bad in f.xpath("//article/address/figure"):
    #     bad.getparent().remove(bad)

    # for bad in s.xpath("//article/address/figure"):
    #     bad.getparent().remove(bad)

    for bad in f.xpath("//h4[@data-block=\"Subheader\"]"):
        bad.attrib["data-block"] = "Header"
        bad.tag = "h3"

    for bad in s.xpath("//h4[@data-block=\"Subheader\"]"):
        bad.attrib["data-block"] = "Header"
        bad.tag = "h3"

    for bad in f.xpath("//article/address//a[@onclick]"):
        try:
            del bad.attrib["onclick"]
        except Exception:
            pass

    for bad in s.xpath("//article/address//a[@rel=\"author\"]"):
        try:
            del bad.attrib["href"]
            del bad.attrib["target"]
            del bad.attrib["onclick"]
        except Exception:
            pass

    for bad in f.xpath("//p[string-length(normalize-space(.)) = 0]"):
        bad.getparent().remove(bad)

    for bad in s.xpath("//p[string-length(normalize-space(.)) = 0]"):
        bad.getparent().remove(bad)

    # for bad in f.xpath("//section[@class=\"related\"]"):
    #     bad.getparent().remove(bad)

    # for bad in s.xpath("//section[@class=\"related\"]"):
    #     bad.getparent().remove(bad)

    for bad in f.xpath("//div[@class=\"iframe-wrap\"]"):
        try:
            del bad.attrib["style"]
            for bad_i in bad.xpath(".//*"):
                if "width" in bad_i.attrib:
                    del bad_i.attrib["width"]
                    del bad_i.attrib["height"]
                if "style" in bad_i.attrib:
                    del bad_i.attrib["style"]
        except Exception:
            pass

    for bad in s.xpath("//div[@class=\"iframe-wrap\"]"):
        try:
            del bad.attrib["style"]
            for bad_i in bad.xpath(".//*"):
                if "width" in bad_i.attrib:
                    del bad_i.attrib["width"]
                    del bad_i.attrib["height"]
                if "style" in bad_i.attrib:
                    del bad_i.attrib["style"]
        except Exception:
            pass

    for bad in f.xpath("//p"):
        if bad.text is not None:
            bad.text = re.sub(r"^\s*(.*?)\s*$", "\\1", bad.text)

    for bad in s.xpath("//p"):
        if bad.text is not None:
            bad.text = re.sub(r"^\s*(.*?)\s*$", "\\1", bad.text)

    # for bad in s.xpath("//figure[@data-block=\"Slideshow\"]"):
    #     slideshow = bad.xpath(".//figure[@class=\"slideshow\"]/*")
    #     for i in slideshow[::-1]:
    #         fc = i.xpath("./figcaption")[0]
    #         span = fc.xpath("./span")[0]
    #         for j in span.xpath("./*"):
    #             span.addprevious(j)
    #         if span.text is not None:
    #             fc.text = span.text
    #         fc.remove(span)
    #         bad.addnext(i)
    #     bad.getparent().remove(bad)

    # for bad in f.xpath("//figure[@data-block=\"Slideshow\"]"):
    #     slideshow = bad.xpath(".//figure[@class=\"slideshow\"]/*")
    #     for i in slideshow[::-1]:
    #         fc = i.xpath("./figcaption")[0]
    #         span = fc.xpath("./span")[0]
    #         for j in span.xpath("./*"):
    #             span.addprevious(j)
    #         if span.text is not None:
    #             fc.text = span.text
    #         fc.remove(span)
    #         bad.addnext(i)
    #     bad.getparent().remove(bad)

    for bad in s.xpath("//article/address//a[@onclick]"):
        try:
            del bad.attrib["onclick"]
        except Exception:
            pass

    # for bad in s.xpath("//article//footer"):
    #     bad.getparent().remove(bad)

    # for bad in f.xpath("//article//footer"):
    #     bad.getparent().remove(bad)

    # for bad in s.xpath("//article/address"):
    #     # del bad.attrib["href"]
    #     # del bad.attrib["target"]
    #     # del bad.attrib["onclick"]
    #     bad.getparent().remove(bad)

    # for bad in s.xpath("//article/address/time"):
    #     bad.getparent().remove(bad)

    # for bad in f.xpath("//article/address/time"):
    #     bad.getparent().remove(bad)
    # # # for bad in s.xpath("//article/address"):
    # # #     # del bad.attrib["href"]
    # # #     # del bad.attrib["target"]
    # # #     # del bad.attrib["onclick"]
    # # #     bad.getparent().remove(bad)

    for img in f.xpath("//img"):
        del img.attrib["alt"]
        del img.attrib["title"]
    for img in s.xpath("//img"):
        del img.attrib["alt"]
        del img.attrib["title"]

    for img in f.xpath("//video"):
        del img.attrib["alt"]
        del img.attrib["title"]
    for img in s.xpath("//video"):
        del img.attrib["alt"]
        del img.attrib["title"]

    pass


def setup(event):
    global unpaused
    unpaused = event


def getHashAndRules(domain, url, cookies):
    d = "https://instantview.telegram.org/my/{}".format(domain)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:65.0) Gecko/20100101 Firefox/65.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": d,
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "max-age=0"
    }
    r = requests.get(d, headers=headers, verify=verify, cookies=cookies, params=dict(url=url))
    cookies = dict(list(cookies.items()) + list(r.cookies.get_dict().items()))

    hash = re.search("my\\?hash=(.*?)\",", str(r.content)).group(1)
    tree = html.fromstring(r.content.decode("utf8"))

    rules = json.loads(re.search("initWorkspace\\(\".*?\",(.*)\\);", tree.xpath("//script[last()]/text()")[0]).group(1))
    return (rules["rules"], hash, cookies)


def checkDiff(nobrowser, cookies, url, t1, t2, browser=""):
    try:
        if unpaused is not None:
            unpaused.wait()
        print(Back.LIGHTYELLOW_EX + " " + Style.RESET_ALL, end="")
        if not url.startswith("http"):
            url = "http://" + url

        domain = urlparse(url).hostname
        if domain.startswith("www."):
            domain = domain[4:]

        f1 = None
        s1 = None

        # TODO switch to next cookie if this fails too much
        # For now just start over with the same cookie
        cookies = [cookies]
        cookie = -1
        while f1 is None:
            cookie += 1
            if cookie >= len(cookies):
                cookie = 0
                time.sleep(45)
            f1 = getHtml(domain, cookies[cookie], url, t1, t2)

        if unpaused is not None:
            unpaused.wait()
        cookie = -1
        while s1 is None:
            cookie += 1
            if cookie >= len(cookies):
                cookie = 0
                time.sleep(45)
            s1 = getHtml(domain, cookies[cookie], url, t2, t1)
        if unpaused is not None:
            unpaused.wait()
        if f1 is None or s1 is None:
            return (url, -1, cookies)
        f = f1[1]
        s = s1[1]
        preview_html_first = f1[2]
        preview_html_second = s1[2]

        compare(f, s)

        a1 = f.xpath("//article")
        showDiff = True

        if len(a1) == 0:
            a1 = f.xpath("//section[@class=\"message\"]")
            copy1 = copy.deepcopy(a1)
            preview_html_first = None
            showDiff = False
        else:
            copy1 = copy.deepcopy(a1)
            for img in copy1[0].xpath("//img"):
                del img.attrib["src"]
            # if preview_html_first is not None:
            #     copy1[0].append(copy.deepcopy(preview_html_first).xpath("//div[@class='page-preview']")[0])

        a2 = s.xpath("//article")
        if len(a2) == 0:
            a2 = s.xpath("//section[@class=\"message\"]")
            copy2 = copy.deepcopy(a2)
            preview_html_second = None
            if not showDiff:
                showDiff = False
        else:
            if not showDiff:
                showDiff = True
            copy2 = copy.deepcopy(a2)
            for img in copy2[0].xpath("//img"):
                del img.attrib["src"]
            # if preview_html_second is not None:
            #     copy2[0].append(copy.deepcopy(preview_html_second).xpath("//div[@class='page-preview']")[0])

        first_gen = etree.tostring(copy1[0], pretty_print=True, encoding='UTF-8').decode("utf-8")
        second_gen = etree.tostring(copy2[0], pretty_print=True, encoding='UTF-8').decode("utf-8")

        # first_gen = re.sub(r"\s*?(</p>)", "\\1", first_gen)
        # first_gen = re.sub(r">\s*<", "><", first_gen, flags=re.S)
        # second_gen = re.sub(r"\s*?(</p>)", "\\1", second_gen)
        # second_gen = re.sub(r">\s*<", "><", second_gen, flags=re.S)

        diff = difflib.HtmlDiff(wrapcolumn=90).make_file(first_gen.split("\n"), second_gen.split("\n"))
        htmlparser = etree.HTMLParser(remove_blank_text=True)
        tree = etree.parse(StringIO(str(diff)), htmlparser)

        frame1_link = f.xpath("//head/link")
        frame1_link[0].attrib["href"] = "https://ivwebcontent.telegram.org{}".format(frame1_link[0].attrib["href"])
        frame1_script = f.xpath("//head/script[@src]")
        frame1_script[0].attrib["src"] = "../../instantview-frame.js"

        tree.xpath("//head")[0].append(frame1_link[0])
        tree.xpath("//head")[0].append(frame1_script[0])

        htmlparser = etree.HTMLParser(remove_blank_text=True, encoding='utf-8')
        append = etree.parse(open("append.html", "r", encoding='utf8'), htmlparser)

        frames = append.xpath("//div[contains(@id, 'frame')]")
        frames[0].append(a1[0])
        frames[1].append(a2[0])

        previews = append.xpath("//div[contains(@id, 'preview')]")
        if preview_html_first is not None:
            previews[0].append(preview_html_first.xpath("//div[@class='page-preview']")[0])
        if preview_html_second is not None:
            previews[1].append(preview_html_second.xpath("//div[@class='page-preview']")[0])

        first_link = append.xpath("//a[@id='first_template']")[0]
        first_link.attrib["href"] = f1[0]
        first_link.text = "Template {}\n".format(t1)

        second_link = append.xpath("//a[@id='second_template']")[0]
        second_link.attrib["href"] = s1[0]
        second_link.text = "Template {}\n".format(t2)

        append.xpath("//input")[0].attrib["value"] = url

        tree.xpath("//body//table")[0].addprevious(append.xpath("//main/div[1]")[0])
        tree.xpath("//body//table")[0].addnext(append.xpath("//main/div[1]")[0])

        for bad in tree.xpath("//table[@summary='Legends']"):
            bad.getparent().remove(bad)
        final = etree.tostring(tree, pretty_print=True).decode("utf-8")
        if unpaused is not None:
            unpaused.wait()

        # ДУМОТЬ ВСО ЕСЧО ВПАДЛУ
        # ХТО ЗАРЖАВ СТАВ РОФЛАН ЇБАЛО
        if showDiff and ("class=\"diff_add\"" in final or "class=\"diff_chg\"" in final or "class=\"diff_sub\"" in final):
            print(Back.LIGHTGREEN_EX + "D" + Style.RESET_ALL, end="")
            md = md5()
            md.update(url.encode('utf-8'))

            fn = "gen/{}/{}_{}_{}.html".format(domain, "t1", "t2", str(md.hexdigest()))
            try:
                os.makedirs(os.path.dirname(fn))
            except Exception:
                pass
            file = open(fn, "w")
            file.write(final)
            file.close()
            if not nobrowser:
                browser = webbrowser if browser == "" else webbrowser.get(browser)
                browser.open_new_tab("file:///{}/{}".format(os.getcwd(), fn))
            return (url, 1, cookies)
        else:
            print(Back.LIGHTGREEN_EX + " " + Style.RESET_ALL, end="")
            return (url, 0, cookies)
    except Exception as ex:
        raise ex
        print(ex)
        return (url, -2, cookies)


def parseCookies(cookiesFile):
    c = open(cookiesFile, "r")
    cl = c.read()
    c.close()

    cookie = SimpleCookie()
    cookie.load(cl)

    cookies = {}
    for key, morsel in cookie.items():
        cookies[key] = morsel.value
    return cookies


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Get pretty HTML diff between two IV templates.')
    parser.add_argument('t1', metavar='first_template', type=str, help='first template number OR template file path')
    parser.add_argument('t2', metavar='second_template', type=str, help='second template number OR template file path')
    parser.add_argument('url', metavar='url', nargs='+', type=str, help='original page url to diff')
    parser.add_argument('--cookies', '-c', help='path to file with cookies (default is cookies.txt)', nargs='?', default="cookies.txt")
    parser.add_argument('--nobrowser', '-n', help='do not open browser when diff is found', action='store_true')
    parser.add_argument('--browser', '-b', help='browser or path to program to open diff', nargs='?', default="")

    args = parser.parse_args()
    for i in args.url:
        cookies = parseCookies(args.cookies)

        checkDiff(args.nobrowser, cookies, i, args.t1, args.t2, args.browser)
