#!/usr/bin/env python
# pylint: disable=line-too-long
# pylint: disable=W0702, W0703, C0103, C0410
# encoding=utf8
'''
# IAFD - (IAFD)
                                                  Version History
                                                  ---------------
    Date            Version                         Modification
    22 Apr 2020   2020.04.22.01    Creation
    15 May 2020   2020.04.22.02    Corrected search string to account for titles that have a Colon in them
                                   added/merge matching string routines - filename, studio, release date
                                   included cast with non-sexual roles
    19 May 2020   2020.04.22.03    Corrected search to look past the results page and get the movie title page to find
                                   studio/release date as the results page only listed the distributor/production year
                                   updated date match function
    01 Jun 2020   2020.04.22.04    Implemented translation of summary
                                   put back scrape from local media assets
    27 Jun 2020   2020.04.22.05    Improvement to Summary Translation: Translate into Plex Library Language
                                   stripping of intenet domain suffixes from studio names when matching
                                   handling of unicode characters in film titles and comparision string normalisation
    12 Sep 2020   2020.04.22.06    Titles with hyphens failing as these were converted to ":"
                                   corrected by splitting and using string upto that position as search...
    20 Sep 2020   2020.04.22.07    Titles with '[', '(' were corrected by splitting and using string upto that position as search...
    07 Oct 2020   2020.04.22.08    IAFD - change to https

---------------------------------------------------------------------------------------------------------------
'''
import datetime, linecache, platform, os, re, string, subprocess, sys, unicodedata, urllib, urllib2
from googletrans import Translator

# Version / Log Title
VERSION_NO = '2020.04.22.08'
PLUGIN_LOG_TITLE = 'IAFD'

# Pattern: (Studio) - Title (Year).ext: ^\((?P<studio>.+)\) - (?P<title>.+) \((?P<year>\d{4})\)
REGEX = Prefs['regex']

# Delay used when requesting HTML, may be good to have to prevent being banned from the site
DELAY = int(Prefs['delay'])

# detect the language the summary appears in on the web page
DETECT = Prefs['detect']

# URLS
BASE_URL = 'https://www.iafd.com'
BASE_SEARCH_URL = BASE_URL + '/results.asp?searchtype=comprehensive&searchstring={0}'

# Date Formats used by website
DATE_YMD = '%Y%m%d'
DATEFORMAT = '%b %d, %Y'

# Website Language
SITE_LANGUAGE = 'en'

# ----------------------------------------------------------------------------------------------------------------------------------
def Start():
    ''' initialise process '''
    HTTP.CacheTime = CACHE_1WEEK
    HTTP.Headers['User-agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.113 Safari/537.36'

# ----------------------------------------------------------------------------------------------------------------------------------
def ValidatePrefs():
    ''' validate changed user preferences '''
    pass

# ----------------------------------------------------------------------------------------------------------------------------------
def anyOf(iterable):
    '''  used for matching strings in lists '''
    for element in iterable:
        if element:
            return element
    return None

# ----------------------------------------------------------------------------------------------------------------------------------
class IAFD(Agent.Movies):
    ''' define Agent class '''
    name = 'Internet Adult Film Database'
    languages = [Locale.Language.English]
    primary_provider = False
    preference = True
    media_types = ['Movie']
    contributes_to = ['com.plexapp.agents.GayAdult', 'com.plexapp.agents.GayAdultFilms', 'com.plexapp.agents.GayAdultScenes']
    accepts_from = ['com.plexapp.agents.localmedia']

    # -------------------------------------------------------------------------------------------------------------------------------
    def matchFilename(self, filename):
        ''' return groups from filename regex match else return false '''
        pattern = re.compile(REGEX)
        matched = pattern.search(filename)
        if matched:
            groups = matched.groupdict()
            return groups['studio'], groups['title'], groups['year']
        else:
            raise Exception("File Name [{0}] not in the expected format: (Studio) - Title (Year)".format(filename))

    # -------------------------------------------------------------------------------------------------------------------------------
    def matchStudioName(self, fileStudioName, siteStudioName):
        ''' match file studio name against website studio name: Boolean Return '''
        siteStudioName = self.NormaliseComparisonString(siteStudioName)

        if siteStudioName == fileStudioName:
            self.log('SELF:: Studio: Full Word Match: Site: {0} = File: {1}'.format(siteStudioName, fileStudioName))
        elif siteStudioName in fileStudioName:
            self.log('SELF:: Studio: Part Word Match: Site: {0} IN File: {1}'.format(siteStudioName, fileStudioName))
        elif fileStudioName in siteStudioName:
            self.log('SELF:: Studio: Part Word Match: File: {0} IN Site: {1}'.format(fileStudioName, siteStudioName))
        else:
            raise Exception('Match Failure: File: {0} != Site: {1} '.format(fileStudioName, siteStudioName))

        return True

    # -------------------------------------------------------------------------------------------------------------------------------
    def matchReleaseDate(self, fileDate, siteDate):
        ''' match file year against website release date: return formatted site date if no error or default to formated file date '''
        if len(siteDate) == 4:      # a year has being provided - default to 31st December of that year
            siteDate = siteDate + '1231'
            siteDate = datetime.datetime.strptime(siteDate, DATE_YMD)
        else:
            siteDate = datetime.datetime.strptime(siteDate, DATEFORMAT)

        # there can not be a difference more than 366 days between FileName Date and SiteDate
        dx = abs((fileDate - siteDate).days)
        msg = 'Match{0}: File Date [{1}] - Site Date [{2}] = Dx [{3}] days'.format(' Failure' if dx > 366 else '', fileDate.strftime('%Y %m %d'), siteDate.strftime('%Y %m %d'), dx)
        if dx > 366:
            raise Exception('Release Date: {0}'.format(msg))
        else:
            self.log('SELF:: Release Date: {0}'.format(msg))

        return siteDate

    # -------------------------------------------------------------------------------------------------------------------------------
    def NormaliseComparisonString(self, myString):
        ''' Normalise string for Comparison, strip all non alphanumeric characters, Vol., Volume, Part, and 1 in series '''
        # convert to lower case and trim
        myString = myString.strip().lower()

        # normalise unicode characters
        myString = unicode(myString)
        myString = unicodedata.normalize('NFD', myString).encode('ascii', 'ignore')

        # replace ampersand with 'and'
        myString = myString.replace('&', 'and')

        # strip domain suffixes, vol., volume from string, standalone "1's"
        pattern = ur'[.](org|com|net|co[.][a-z]{2})|Vol[.]|\bPart\b|\bVolume\b|(?<!\d)1(?!\d)|[^A-Za-z0-9]+'
        myString = re.sub(pattern, '', myString, flags=re.IGNORECASE)

        return myString

    #-------------------------------------------------------------------------------------------------------------------------------
    def CleanSearchString(self, myString):
        ''' Prepare Video title for search query '''
        self.log('SELF:: Original Search Query [{0}]'.format(myString))

        myString = myString.strip().lower()

        # split and take up to first occurence of character
        splitChars = ['-', '[', '(', ur'\u2013', ur'\u2014']
        pattern = u'[{0}]'.format(''.join(splitChars))
        matched = re.search(pattern, myString)  # match against whole string
        if matched:
            numPos = matched.start()
            self.log('SELF:: Search Query:: Splitting at position [{0}]. Found one of these {1}'.format(numPos, pattern))
            myString = myString[:numPos]
            self.log('SELF:: Amended Search Query [{0}]'.format(myString))
        else:
            self.log('SELF:: Search Query:: Split not attempted. String has none of these {0}'.format(pattern))

        myString = String.StripDiacritics(myString)
        myString = String.URLEncode(myString)

        # sort out double encoding: & html code %26 for example is encoded as %2526; on MAC OS '*' sometimes appear in the encoded string 
        myString = myString.replace('%25', '%').replace('*', '')

        self.log('SELF:: Returned Search Query [{0}]'.format(myString))

        return myString

    # -------------------------------------------------------------------------------------------------------------------------------
    def TranslateString(self, myString, language):
        ''' Translate string into Library language '''
        myString = myString.strip()
        if language == 'xn' or language == 'xx':    # no language or language unknown
            self.log('SELF:: Library Language: [%s], Run Translation: [False]', 'No Language' if language == 'xn' else 'Unknown')
        elif myString:
            translator = Translator(service_urls=['translate.google.com', 'translate.google.ca', 'translate.google.co.uk',
                                                  'translate.google.com.au', 'translate.google.co.za', 'translate.google.br.com',
                                                  'translate.google.pt', 'translate.google.es', 'translate.google.com.mx',
                                                  'translate.google.it', 'translate.google.nl', 'translate.google.be',
                                                  'translate.google.de', 'translate.google.ch', 'translate.google.at',
                                                  'translate.google.ru', 'translate.google.pl', 'translate.google.bg',
                                                  'translate.google.com.eg', 'translate.google.co.il', 'translate.google.co.jp',
                                                  'translate.google.co.kr', 'translate.google.fr', 'translate.google.dk'])
            runTranslation = (language != SITE_LANGUAGE)
            self.log('SELF:: [Library:Site] Language: [%s:%s], Run Translation: [%s]', language, SITE_LANGUAGE, runTranslation)
            if DETECT:
                detectString = re.findall(ur'.*?[.!?]', myString)[:4]   # take first 4 sentences of string to detect language
                detectString = ''.join(detectString)
                self.log('SELF:: Detect Site Language [%s] using this text: %s', DETECT, detectString)
                try:
                    detected = translator.detect(detectString)
                    runTranslation = (language != detected.lang)
                    self.log('SELF:: Detected Language: [%s] Run Translation: [%s]', detected.lang, runTranslation)
                except Exception as e:
                    self.log('SELF:: Error Detecting Text Language: %s', e)

            try:
                myString = translator.translate(myString, dest=language).text if runTranslation else myString
                self.log('SELF:: Translated [%s] Summary Found: %s', runTranslation, myString)
            except Exception as e:
                self.log('SELF:: Error Translating Text: %s', e)

        return myString if myString else ' '     # return single space to initialise metadata summary field

    # -------------------------------------------------------------------------------------------------------------------------------
    def log(self, message, *args):
        ''' log messages '''
        if re.search('ERROR', message, re.IGNORECASE):
            Log.Error(PLUGIN_LOG_TITLE + ' - ' + message, *args)
        else:
            Log.Info(PLUGIN_LOG_TITLE + ' - ' + message, *args)

    # -------------------------------------------------------------------------------------------------------------------------------
    def search(self, results, media, lang, manual):
        ''' Search For Media Entry '''
        if not media.items[0].parts[0].file:
            return
        folder, filename = os.path.split(os.path.splitext(media.items[0].parts[0].file)[0])

        self.log('-----------------------------------------------------------------------')
        self.log('SEARCH:: Version               : v.%s', VERSION_NO)
        self.log('SEARCH:: Python                : %s', sys.version_info)
        self.log('SEARCH:: Platform              : %s %s', platform.system(), platform.release())
        self.log('SEARCH:: Prefs-> delay         : %s', DELAY)
        self.log('SEARCH::      -> detect        : %s', DETECT)
        self.log('SEARCH::      -> regex         : %s', REGEX)
        self.log('SEARCH:: Library:Site Language : %s:%s', lang, SITE_LANGUAGE)
        self.log('SEARCH:: Media Title           : %s', media.title)
        self.log('SEARCH:: File Name             : %s', filename)
        self.log('SEARCH:: File Folder           : %s', folder)
        self.log('-----------------------------------------------------------------------')

        # Check filename format
        try:
            group_studio, group_title, group_year = self.matchFilename(filename)
            self.log('SEARCH:: Processing: Studio: %s   Title: %s   Year: %s', group_studio, group_title, group_year)
        except Exception as e:
            self.log('SEARCH:: Error: %s', e)
            return

        # Compare Variables used to check against the studio name on website: remove all umlauts, accents and ligatures
        compareStudio = self.NormaliseComparisonString(group_studio)
        compareTitle = self.NormaliseComparisonString(group_title)
        compareReleaseDate = datetime.datetime(int(group_year), 12, 31)  # default to 31 Dec of Filename year

        # Search Query - for use to search the internet
        searchTitle = self.CleanSearchString(group_title)
        searchQuery = BASE_SEARCH_URL.format(searchTitle)
        self.log('SEARCH:: Search Query: %s', searchQuery)

        # iafd displays the first 50 results, clicking on "See More Results"  appends the rest
        try:
            html = HTML.ElementFromURL(searchQuery, timeout=90, errors='ignore', sleep=DELAY)
        except Exception as e:
            self.log('SEARCH:: Error: Search Query did not pull any results: %s', e)
            return

        try:
            searchQuery = html.xpath('//a[text()="See More Results..."]/@href')[0].strip()
            if BASE_URL not in searchQuery:
                searchQuery = BASE_URL + '/' + searchQuery
            self.log('SEARCH:: Loading Additional Search Results: %s', searchQuery)
            html = HTML.ElementFromURL(searchQuery, timeout=90, errors='ignore', sleep=DELAY)
        except:
            self.log('SEARCH:: No Additional Search Results')

        titleList = html.xpath('//table[@id="titleresult"]/tbody/tr')
        self.log('SEARCH:: Titles List: %s Found', len(titleList))
        for title in titleList:
            # Site Title Check
            try:
                siteTitle = title.xpath('./td[1]/a/text()')[0]
                self.log('SEARCH:: Site Title: "%s"', siteTitle)
                siteTitle = self.NormaliseComparisonString(siteTitle)
                self.log('SEARCH:: Title Match: [%s] Compare Title - Site Title "%s - %s"', (compareTitle == siteTitle), compareTitle, siteTitle)
                if siteTitle != compareTitle: # compare against AKA column
                    try:
                        siteAKATitle = title.xpath('./td[4]/text()')[0]
                        siteAKATitle = self.NormaliseComparisonString(siteAKATitle)
                        if siteAKATitle != compareTitle:
                            continue
                    except:
                        self.log('SEARCH:: Error getting Site AKA Title')
                        continue
            except:
                self.log('SEARCH:: Error getting Site Title')
                continue

            # Site Title URL Check
            try:
                siteURL = title.xpath('./td[1]/a/@href')[0]
                siteURL = ('/' if siteURL[0] != '/' else '') + siteURL
                siteURL = (BASE_URL if BASE_URL not in siteURL else '') + siteURL
                self.log('SEARCH:: Site Title url: %s', siteURL)
            except:
                self.log('SEARCH:: Error getting Site Title Url')

            # Search Website for date - date is in format yyyy
            try:
                siteReleaseDate = title.xpath('./td[2]/text()')[0].strip()
                self.log('SEARCH:: Site Release Date: %s', siteReleaseDate)
                try:
                    siteReleaseDate = self.matchReleaseDate(compareReleaseDate, siteReleaseDate)
                except Exception as e:
                    self.log('SEARCH:: Error getting Site Release Date: %s: Default to Filename Date', e)
                    siteReleaseDate = compareReleaseDate
            except:
                self.log('SEARCH:: Error getting Site Release Date: Default to Filename Date')
                siteReleaseDate = compareReleaseDate

            # Site Studio Check: IAFD lists distributor on main page, look in Site URL for this
            try:
                siteDistributor = title.xpath('./td[3]/text()')[0]
                self.log('SEARCH:: Site Distributor: %s', siteDistributor)
                html = HTML.ElementFromURL(siteURL, sleep=DELAY)
                siteStudio = html.xpath('//p[@class="bioheading" and text()="Studio"]//following-sibling::p[1]/a/text()')[0]
                try:
                    self.matchStudioName(compareStudio, siteStudio)
                except Exception as e:
                    self.log('SEARCH:: Error: Site URL Studio: %s', e)
                    continue

                # get release date: if none recorded use main results page value
                try:
                    siteReleaseDate = html.xpath('//p[@class="bioheading" and text()="Release Date"]//following-sibling::p[1]/text()')[0].strip()
                    self.log('SEARCH:: Site URL Release Date: %s', siteReleaseDate)
                    try:
                        siteReleaseDate = self.matchReleaseDate(compareReleaseDate, siteReleaseDate)
                    except Exception as e:
                        self.log('SEARCH:: Error getting Site URL Release Date: %s: Default to Filename Date', e)
                        siteReleaseDate = compareReleaseDate
                except:
                    self.log('SEARCH:: Error getting Site URL Release Date: Default to Filename Date')
                    siteReleaseDate = compareReleaseDate

            except:
                self.log('SEARCH:: Error getting Site Studio')
                continue

            # we should have a match on studio, title and year now
            results.Append(MetadataSearchResult(id=siteURL + '|' + siteReleaseDate.strftime(DATE_YMD), name=group_title, score=100, lang=lang))
            return

    # -------------------------------------------------------------------------------------------------------------------------------
    def update(self, metadata, media, lang, force=True):
        ''' Update Media Entry '''
        folder, filename = os.path.split(os.path.splitext(media.items[0].parts[0].file)[0])
        self.log('-----------------------------------------------------------------------')
        self.log('UPDATE:: Version    : v.%s', VERSION_NO)
        self.log('UPDATE:: File Name  : %s', filename)
        self.log('UPDATE:: File Folder: %s', folder)
        self.log('-----------------------------------------------------------------------')

        # Check filename format
        try:
            group_studio, group_title, group_year = self.matchFilename(filename)
            self.log('UPDATE:: Processing: Studio: %s   Title: %s   Year: %s', group_studio, group_title, group_year)
        except Exception as e:
            self.log('UPDATE:: Error: %s', e)
            return

        # Fetch HTML.
        html = HTML.ElementFromURL(metadata.id.split('|')[0], timeout=60, errors='ignore', sleep=DELAY)

        #  The following bits of metadata need to be established and used to update the movie on plex
        #    1.  Metadata that is set by Agent as default
        #        a. Studio               : From studio group of filename - no need to process this as is used to find it on website
        #        b. Title                : From title group of filename - no need to process this as is used to find it on website
        #        c. Tag line             : Corresponds to the url of movie
        #        d. Originally Available : set from metadata.id (search result)
        #        e. Content Rating       : Always X
        #    2.  Metadata retrieved from website
        #        a. Summary              : Synopsis, Scene Breakdown and Comments
        #        b. Cast                 : List of Actors and Photos (alphabetic order)
        #        c. Directors

        # 1a.   Studio - straight of the file name
        metadata.studio = group_studio
        self.log('UPDATE:: Studio: "%s"' % metadata.studio)

        # 1b.   Set Title
        metadata.title = group_title
        self.log('UPDATE:: Video Title: "%s"' % metadata.title)

        # 1c/d. Set Tagline/Originally Available from metadata.id
        metadata.tagline = metadata.id.split('|')[0]
        metadata.originally_available_at = datetime.datetime.strptime(metadata.id.split('|')[1], DATE_YMD)
        metadata.year = metadata.originally_available_at.year
        self.log('UPDATE:: Tagline: %s', metadata.tagline)
        self.log('UPDATE:: Default Originally Available Date: %s', metadata.originally_available_at)

        # 1e.   Set Content Rating to Adult
        metadata.content_rating = 'X'
        self.log('UPDATE:: Content Rating: X')

        # 2a.   Summary (synopsis + Scene Breakdown + Comments)
        try:
            synopsis = html.xpath('//div[@id="synopsis"]/div/ul/li//text()')[0].strip()
            self.log('UPDATE:: Summary - Synopsis Found: %s', synopsis)
        except Exception as e:
            synopsis = ''
            self.log('UPDATE:: Error: Summary - No Synopsis: %s', e)

        try:
            scene = html.xpath('//div[@id="sceneinfo"]/ul/li//text()')[0] # will error if no scenebreakdown
            htmlscenes = html.xpath('//div[@id="sceneinfo"]/ul/li//text()')
            scene = ''
            for item in htmlscenes:
                scene += '{0}\n'.format(item)
            scene = '\nScene Breakdown:\n' + scene
            self.log('UPDATE:: Summary - Scene Breakdown Found: %s', scene)
        except Exception as e:
            scene = ''
            self.log('UPDATE:: Error: Summary - No Scene Breakdown: %s', e)

        try:
            comment = html.xpath('//div[@id="commentsection"]/ul/li//text()')[0] # will error if no comments
            htmlcomments = html.xpath('//div[@id="commentsection"]/ul/li//text()')
            listEven = htmlcomments[::2] # Elements from htmlcomments starting from 0 iterating by 2
            listOdd = htmlcomments[1::2] # Elements from htmlcomments starting from 1 iterating by 2
            comment = ''
            for sceneNo, movie in zip(listEven, listOdd):
                comment += '{0} -- {1}\n'.format(sceneNo, movie)
            comment = 'Comments:\n' + comment
            self.log('UPDATE:: Summary - Comments Found: %s', comment)
        except Exception as e:
            comment = ''
            self.log('UPDATE:: Error: Summary - No Comments: %s', e)

        summary = synopsis + scene + comment
        metadata.summary = self.TranslateString(summary, lang)

        # 2b.   Cast
        try:
            castdict = {}
            htmlcastnames = html.xpath('//div[contains(@class,"castbox")]/p/a//text()')
            htmlcastphotos = html.xpath('//div[contains(@class,"castbox")]/p/a/img/@src')
            self.log('UPDATE:: %s Cast Names: %s', len(htmlcastnames), htmlcastnames)
            self.log('UPDATE:: %s Cast Photos: %s', len(htmlcastphotos), htmlcastphotos)
            for castname, castphoto in zip(htmlcastnames, htmlcastphotos):
                castdict[castname] = '' if 'nophoto' in castphoto else castphoto

            # sort the dictionary and add kv to metadata
            metadata.roles.clear()
            for key in sorted(castdict):
                role = metadata.roles.new()
                role.name = key
                role.photo = castdict[key]
        except Exception as e:
            self.log('UPDATE:: Error getting Cast: %s', e)

        # 2c.   Directors
        try:
            directors = []
            htmldirector = html.xpath('//p[@class="bioheading" and text()="Directors"]//following-sibling::p[1]/a/text()')
            self.log('UPDATE:: Director List %s', htmldirector)
            for director in htmldirector:
                director = director.strip()
                if director:
                    directors.append(director)

            # sort the dictionary and add kv to metadata
            directors.sort()
            metadata.directors.clear()
            for director in directors:
                Director = metadata.directors.new()
                Director.name = director
        except Exception as e:
            self.log('UPDATE:: Error getting Director(s): %s', e)
