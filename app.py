import re
import time
from urllib.parse import urljoin, urlparse
import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

st.set_page_config(page_title='Aziende.it Extractor', page_icon='📊', layout='wide')
HEADERS={'User-Agent':'Mozilla/5.0 (compatible; ProspectResearchTool/1.0)'}

def soup_for(session,url):
    r=session.get(url,headers=HEADERS,timeout=20); r.raise_for_status()
    return BeautifulSoup(r.text,'html.parser')

def clean(x): return re.sub(r'\s+',' ',x or '').strip()

def label_value(soup,label):
    for tag in soup.find_all(['tr','li','p','div']):
        t=clean(tag.get_text(' ',strip=True))
        if t.lower().startswith(label.lower()) and len(t)<500:
            v=re.sub(r'^'+re.escape(label)+r'\s*[:|]?\s*','',t,flags=re.I).strip()
            if v and v.lower()!=label.lower(): return v
    return ''

def company_links(soup,base):
    out=[]; seen=set()
    for a in soup.find_all('a',href=True):
        u=urljoin(base,a['href']); p=urlparse(u)
        if p.netloc.lower()!='www.aziende.it': continue
        path=p.path.rstrip('/')
        if path.count('/')!=1 or not path: continue
        if any(path.startswith(x) for x in ['/piemonte/','/lombardia/','/veneto/','/ateco/','/fatturato/','/servizi/','/blog/','/login','/privacy','/termini']): continue
        if u not in seen: seen.add(u); out.append(u)
    return out

def next_page(soup,current):
    m=re.search(r'[?&]page=(\d+)',current); cur=int(m.group(1)) if m else 1
    for a in soup.find_all('a',href=True):
        label=clean(a.get_text(' ',strip=True)).lower(); u=urljoin(current,a['href'])
        if label.isdigit() and int(label)==cur+1: return u
        if label in {'›','>','next','successiva'} and u!=current: return u
    return None

def extract(url,session):
    s=soup_for(session,url); h1=s.find('h1')
    name=clean(h1.get_text(' ',strip=True)) if h1 else clean(s.title.get_text()) if s.title else ''
    phone=''; tel=s.select_one('a[href^="tel:"]')
    if tel: phone=clean(tel.get('href','').replace('tel:',''))
    if not phone:
        text=clean(s.get_text(' ',strip=True))
        nums=re.findall(r'(?<!\d)(?:\+39[\s./-]?)?(?:0\d{1,3}[\s./-]?\d{5,8}|3\d{2}[\s./-]?\d{6,7})(?!\d)',text)
        if nums: phone=clean(nums[0])
    return {'Azienda':name,'Telefono':phone,'Dipendenti':label_value(s,'Dipendenti'),'Fatturato':label_value(s,'Fatturato'),'URL scheda':url}

def scrape(start,max_n,delay):
    sess=requests.Session(); results=[]; seen=set(); pages=set(); url=start
    bar=st.progress(0); status=st.empty()
    while url and len(results)<max_n and url not in pages:
        pages.add(url); status.info(f'Pagina elenco: {url}')
        s=soup_for(sess,url); links=company_links(s,url)
        if not links: break
        for u in links:
            if len(results)>=max_n: break
            if u in seen: continue
            seen.add(u)
            try: results.append(extract(u,sess))
            except Exception as e: results.append({'Azienda':'','Telefono':'','Dipendenti':'','Fatturato':'','URL scheda':u,'Errore':str(e)})
            bar.progress(min(len(results)/max_n,1)); status.info(f'Elaborate {len(results)}/{max_n}'); time.sleep(delay)
        url=next_page(s,url)
    status.success(f'Completato: {len(results)} aziende.')
    return pd.DataFrame(results)

st.title('📊 Aziende.it Extractor')
st.caption('Estrae telefono, dipendenti e fatturato dalle schede pubblicamente accessibili.')
st.info('Non aggira login, CAPTCHA, paywall o limitazioni tecniche. Verifica i termini d’uso del sito prima di raccolte su larga scala.')
url=st.text_input('URL della ricerca Aziende.it','https://www.aziende.it/piemonte/cuneo/alba/?categoria=&codiceAteco=&comune=alba&fatturato=fascia-1')
max_n=st.number_input('Numero massimo aziende',1,100,20,10)
delay=st.number_input('Pausa tra richieste (secondi)',0.5,10.0,1.5,0.5)
if st.button('🚀 ESTRAI AZIENDE',type='primary'):
    try:
        if urlparse(url if '://' in url else 'https://'+url).netloc.lower() not in {'www.aziende.it','aziende.it'}: st.error('Inserisci un URL di Aziende.it.')
        else: st.session_state['df']=scrape(url if '://' in url else 'https://'+url,int(max_n),float(delay))
    except Exception as e: st.error(f'Errore: {e}')
if 'df' in st.session_state:
    df=st.session_state['df']; st.subheader(f'Risultati — {len(df)} aziende'); st.dataframe(df,use_container_width=True,hide_index=True)
    st.download_button('⬇️ Scarica CSV',df.to_csv(index=False).encode('utf-8-sig'),'aziende_it_estrazione.csv','text/csv')
