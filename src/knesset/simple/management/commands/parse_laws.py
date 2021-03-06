#encoding: utf-8
import urllib,urllib2
from BeautifulSoup import BeautifulSoup
from HTMLParser import HTMLParseError
import datetime
import re
import parse_knesset_bill_pdf
import logging
from parse_government_bill_pdf import GovProposal

logger = logging.getLogger("open-knesset.parse_laws")

class ParseLaws(object):
    """partially abstract class for parsing laws. contains one function used in few
       cases (private and other laws). this function gives the required page 	
    """

    url = None
    
    def get_page_with_param(self,params):
        #print self.url
        if params == None:
            try:
                html_page = urllib2.urlopen(self.url).read().decode('windows-1255').encode('utf-8')
            except urllib2.URLError:
                logger.error("can't open URL: %s" % self.url)
                return None
            try:
                soup = BeautifulSoup(html_page)
            except HTMLParseError, e:
                logger.debug("parsing URL: %s - %s. will try harder." % (self.url, e))
                html_page = re.sub("(?s)<!--.*?-->"," ", html_page) # cut anything that looks suspicious
                html_page = re.sub("(?s)<script>.*?</script>"," ", html_page)
                html_page = re.sub("(?s)<!.*?>"," ", html_page)
                try:
                    soup = BeautifulSoup(html_page)
                except HTMLParseError, e:
                    logger.debug("error parsing URL: %s - %s" % (self.url, e))
                    return None
            return soup
        else:	
            data = urllib.urlencode(params)
            try:
                url_data = urllib2.urlopen(self.url,data)
            except urllib2.URLError:
                logger.error("can't open URL: %s" % self.url)
                return None
            html_page = url_data.read().decode('windows-1255').encode('utf-8')
            return BeautifulSoup(html_page)

def fix_dash(s):
    """returns s with normalized spaces before and after the dash"""
    if not s:
        return None
    m = re.match(r'(תיקון)( ?)(-)( ?)(.*)'.decode('utf8'),s)
    if not m:
        return s
    return ' '.join(m.groups()[0:5:2])

class ParsePrivateLaws(ParseLaws):
    """a class that parses private laws proposed
    """

    #the constructor parses the laws data from the required pages
    def __init__(self,days_back):
        self.url =r"http://www.knesset.gov.il/privatelaw/Plaw_display.asp?lawtp=1"
        self.rtf_url=r"http://www.knesset.gov.il/privatelaw"
        self.laws_data=[]
        self.parse_pages_days_back(days_back)

    #parses the required pages data
    def parse_pages_days_back(self,days_back):
        today = datetime.date.today()
        last_required_date = today + datetime.timedelta(days=-days_back)
        last_law_checked_date = today
        index = None
        while last_law_checked_date > last_required_date:
            if index:
                params = {'RowStart':index}
            else:
                params = None
            soup_current_page = self.get_page_with_param(params)
            if not soup_current_page:
                return
            index = self.get_param(soup_current_page)
            self.parse_private_laws_page(soup_current_page)
            last_law_checked_date = self.update_last_date()

    def get_param(self,soup):
        name_tag = soup.findAll(lambda tag: tag.name == 'a' and tag.has_key('href') and re.match("javascript:SndSelf\((\d+)\);",tag['href']))
        m=re.match("javascript:SndSelf\((\d+)\);",name_tag[0]['href'])
        return m.groups(1)[0]

    def parse_private_laws_page(self,soup):
        name_tag = soup.findAll(lambda tag: tag.name == 'tr' and tag.has_key('valign') and tag['valign']=='Top')
        for tag in name_tag: 
            tds = tag.findAll(lambda td: td.name == 'td')
            x={}
            x['knesset_id'] = int(tds[0].string.strip())
            x['law_id'] = int(tds[1].string.strip())
            if tds[2].findAll('a')[0].has_key('href'):
                x['text_link'] = self.rtf_url + r"/" + tds[2].findAll('a')[0]['href']
            x['law_full_title'] = tds[3].string.strip()
            m = re.match(u'הצעת ([^\(,]*)(.*?\((.*?)\))?(.*?\((.*?)\))?(.*?,(.*))?',x['law_full_title'])
            if not m:
                logger.warn("can't parse proposal title: %s" % x['law_full_title']) 
                continue
            x['law_name'] = m.group(1).strip().replace('\n','').replace('&nbsp;',' ')
            comment1 = m.group(3)
            comment2 = m.group(5)
            if comment2:                    
                x['correction'] = comment2.strip().replace('\n','').replace('&nbsp;',' ')
                x['comment'] = comment1
            else:                
                x['comment'] = None
                if comment1:
                    x['correction'] = comment1.strip().replace('\n','').replace('&nbsp;',' ')
                else:
                    x['correction'] = None
            x['correction'] = fix_dash(x['correction'])
            x['law_year'] = m.group(7)
            x['proposal_date'] = datetime.datetime.strptime(tds[4].string.strip(), '%d/%m/%Y').date() 
            names_string = ''.join([unicode(y) for y in tds[5].findAll('font')[0].contents])
            names_string = names_string.replace('\n','').replace('&nbsp;',' ')
            proposers = []
            joiners = []
            if re.search('ONMOUSEOUT',names_string)>0:
                splitted_names= names_string.split('ONMOUSEOUT')
                joiners = [ name for name in re.match('(.*?)\',\'',splitted_names[0]).group(1).split('<br />') if len(name)>0 ]
                proposers = splitted_names[1][10:].split('<br />')
            else:
                proposers = names_string.split('<br />')
            x['proposers'] = proposers
            x['joiners'] = joiners
            self.laws_data.append(x)

    def update_last_date(self):
        return self.laws_data[-1]['proposal_date']

class ParseKnessetLaws(ParseLaws):
    """A class that parses Knesset Laws (laws after committees)
	   the constructor parses the laws data from the required pages
    """
    def __init__(self,min_booklet):
        self.url =r"http://www.knesset.gov.il/laws/heb/template.asp?Type=3"
        self.pdf_url=r"http://www.knesset.gov.il"
        self.laws_data=[]
        self.min_booklet = min_booklet
        self.parse_pages_booklet()	

    def parse_pages_booklet(self):
        full_page_parsed = True
        index = None
        while full_page_parsed:
            if index:
                params = {'First':index[0],'Start':index[1]}	
            else:
                params = None
            soup_current_page = self.get_page_with_param(params)
            index = self.get_param(soup_current_page)
            full_page_parsed = self.parse_laws_page(soup_current_page)

    def get_param(self,soup):
        name_tag = soup.findAll(lambda tag: tag.name == 'a' and tag.has_key('href') and re.match("javascript:SndSelf\((\d+),(\d+)\);",tag['href']))
        if name_tag:
            m = re.match("javascript:SndSelf\((\d+),(\d+)\);",name_tag[0]['href'])
            return m.groups()
        else:
            return None

    def parse_pdf(self,pdf_url):
        return parse_knesset_bill_pdf.parse(pdf_url)

    def parse_laws_page(self,soup):
        name_tag = soup.findAll(lambda tag: tag.name == 'a' and tag.has_key('href') and tag['href'].find(".pdf")>=0)
        for tag in name_tag:
            pdf_link = self.pdf_url + tag['href']
            booklet = re.search(r"/(\d+)/",tag['href']).groups(1)[0]
            if int(booklet) <= self.min_booklet:
                return False
            pdf_data = self.parse_pdf(pdf_link)
            for j in range(len(pdf_data)): # sometime there is more than 1 law in a pdf
                title = pdf_data[j]['title']
                m = re.findall('[^\(\)]*\((.*?)\)[^\(\)]',title)
                try:
                    comment = m[-1].strip().replace('\n','').replace('&nbsp;',' ')
                    law = title[:title.find(comment)-1]
                except:
                    comment = None
                    law = title.replace(',','')
                try:
                    correction = m[-2].strip().replace('\n','').replace('&nbsp;',' ')
                    law = title[:title.find(correction)-1]
                except:
                    correction = None
                correction = fix_dash(correction)
                law = law.strip().replace('\n','').replace('&nbsp;',' ')
                if law.find("הצעת ".decode("utf8"))==0:
                    law = law[5:]
                
                law_data = {'booklet':booklet,'link':pdf_link, 'law':law, 'correction':correction,
                                       'comment':comment, 'date':pdf_data[j]['date']}
                if 'original_ids' in pdf_data[j]:
                    law_data['original_ids'] = pdf_data[j]['original_ids']
                if 'bill' in pdf_data[j]:
                    law_data['bill'] = pdf_data[j]['bill']
                self.laws_data.append(law_data)
        return True               

    def update_booklet(self):
        return int(self.laws_data[-1]['booklet'])

class ParseGovLaws(ParseKnessetLaws):

    def __init__(self,min_booklet):
        self.url =r"http://www.knesset.gov.il/laws/heb/template.asp?Type=4"
        self.pdf_url=r"http://www.knesset.gov.il"
        self.laws_data=[]
        self.min_booklet = min_booklet
        self.parse_pages_booklet()

    def parse_pdf(self,pdf_url):
        filename = 'tmp.pdf'
        f = open(filename,'wb')
        d = urllib2.urlopen(pdf_url)
        f.write(d.read())
        f.close()
        prop = GovProposal(filename)
        
        # TODO: check if parsing handles more than 1 prop in a booklet                
        return [{'title':prop.get_title(),'date':prop.get_date(), 'bill':prop}]
        
#############
#   Main    #
#############	

if __name__ == '__main__':
    m = ParsePrivateLaws(15)


