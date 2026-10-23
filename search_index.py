"""Normalize current article text without matching formatting tags or old revisions."""
from html.parser import HTMLParser
import re


def plain_text(content):
    value=content or ''
    if not value.lstrip().startswith('<'):return re.sub(r'\s+',' ',value).strip()
    class Parser(HTMLParser):
        def __init__(self):super().__init__(convert_charrefs=True);self.parts=[];self.skip=0
        def handle_starttag(self,tag,attrs):
            if tag in ('script','style'):self.skip+=1
            if tag in ('p','div','br','li','blockquote','h1','h2','h3'):self.parts.append(' ')
        def handle_endtag(self,tag):
            if tag in ('script','style'):self.skip=max(0,self.skip-1)
            if tag in ('p','div','li','blockquote','h1','h2','h3'):self.parts.append(' ')
        def handle_data(self,data):
            if not self.skip:self.parts.append(data)
    parser=Parser();parser.feed(value);parser.close()
    return re.sub(r'\s+',' ',''.join(parser.parts)).strip()


def backfill_drafts(connection,text):
    while True:
        rows=connection.execute(text('SELECT id,content FROM drafts WHERE search_text IS NULL ORDER BY id LIMIT 200')).fetchall()
        if not rows:return
        for identifier,content in rows:
            connection.execute(text('UPDATE drafts SET search_text=:value WHERE id=:id'),dict(value=plain_text(content),id=identifier))
