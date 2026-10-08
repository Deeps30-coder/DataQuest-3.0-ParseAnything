import json, requests, streamlit as st
st.set_page_config(page_title='ParseAnything',layout='wide')
st.title('ParseAnything — DataQuest 3.0')
st.caption('Turn your documents into clear text, tables and structured data.')
api=st.sidebar.text_input('Server address','http://127.0.0.1:8000',help='Where the ParseAnything API is running.')
f=st.file_uploader('Choose a document (PDF, scanned PDF, image, Word, Excel or PowerPoint, old or new)',type=['pdf','doc','docx','xls','xlsx','ppt','pptx','png','jpg','jpeg','tif','tiff','bmp'])
if f and st.button('Parse document',type='primary'):
    with st.spinner('Reading your document...'):
        r=requests.post(api+'/parse',files={'file':(f.name,f.getvalue(),f.type)},timeout=120)
    if not r.ok: st.error(r.text); st.stop()
    data=r.json(); st.session_state['data']=data
if 'data' in st.session_state:
    d=st.session_state['data']
    c1,c2,c3=st.columns(3); c1.metric('Pages',d['pages']); c2.metric('Text and table pieces',len(d['blocks'])); c3.metric('Result',d['status'])
    tab1,tab2,tab3=st.tabs(['Readable view','Raw JSON','Blocks'])
    with tab1: st.markdown(d['markdown'])
    with tab2: st.code(json.dumps(d,indent=2,ensure_ascii=False),language='json')
    with tab3:
        for b in d['blocks']:
            with st.expander(f"{b['id']} · {b['type']} · confidence {b['confidence']:.2f}"):
                st.write(b.get('text',''))
                st.json({'page':b['page'],'bbox':b.get('bbox'),'source':b.get('source'),'status':b.get('status'),'metadata':b.get('metadata')})
