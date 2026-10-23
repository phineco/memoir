"""Provider boundary. No keys, body text, voice IDs or provider response bodies in errors."""
import base64
import re
from urllib.parse import urlsplit

import requests


class VoiceError(Exception):
    def __init__(self,code='provider_unavailable',uncertain=False):
        super().__init__(code);self.code=code;self.uncertain=uncertain


class VoiceProvider:
    def create(self,sample,model,prefix):raise NotImplementedError
    def query(self,voice_id):raise NotImplementedError
    def list(self,prefix):raise NotImplementedError
    def delete(self,voice_id):raise NotImplementedError
    def synthesize(self,voice_id,model,text):raise NotImplementedError


class CosyVoiceProvider(VoiceProvider):
    def __init__(self,key,workspace):
        if not key or not re.fullmatch(r'[A-Za-z0-9-]{1,80}',workspace):raise VoiceError('configuration')
        self.base=f'https://{workspace}.cn-beijing.maas.aliyuncs.com/api/v1/services/audio/tts/'
        self.headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'}

    def _post(self,path,data,mutation=False):
        try:
            response=requests.post(self.base+path,headers=self.headers,json=data,timeout=(10,120),allow_redirects=False)
            if not 200<=response.status_code<300:raise VoiceError('provider_rejected',mutation and response.status_code>=500)
            body=response.json()
            if not isinstance(body.get('output'),dict):raise VoiceError('invalid_response',mutation)
            identifier=body.get('request_id','')
            self.last_request_id=identifier if isinstance(identifier,str) and re.fullmatch(r'[A-Za-z0-9_-]{1,128}',identifier) else ''
            return body['output']
        except VoiceError:raise
        except (requests.RequestException,ValueError,TypeError,AttributeError):raise VoiceError('provider_unavailable',mutation) from None

    def _manage(self,action,mutation=False,**data):
        return self._post('customization',{'model':'voice-enrollment','input':dict(action=action,**data)},mutation)

    def create(self,sample,model,prefix):
        data=self._manage('create_voice',True,target_model=model,prefix=prefix,
                          audio='data:audio/wav;base64,'+base64.b64encode(sample).decode('ascii'))
        voice=data.get('voice_id')
        if not isinstance(voice,str) or not 1<=len(voice)<=255 or '-'+prefix+'-' not in voice:raise VoiceError('invalid_response',True)
        return voice

    def query(self,voice_id):
        data=self._manage('query_voice',voice_id=voice_id)
        if data.get('status') not in ('OK','DEPLOYING','UNDEPLOYED'):raise VoiceError('invalid_response')
        return data['status'],data.get('target_model')

    def list(self,prefix):
        voices=[]
        for page in range(11):
            data=self._manage('list_voice',prefix=prefix,page_index=page,page_size=100)
            rows=data.get('voice_list')
            if not isinstance(rows,list):raise VoiceError('invalid_response')
            for row in rows:
                identifier=row.get('voice_id') if isinstance(row,dict) else None
                if not isinstance(identifier,str) or ('-'+prefix+'-') not in identifier:raise VoiceError('invalid_response')
                voices.append(identifier)
            if len(rows)<100:return voices
        raise VoiceError('incomplete_listing')

    def delete(self,voice_id):
        self._manage('delete_voice',True,voice_id=voice_id)
        return self.last_request_id

    def synthesize(self,voice_id,model,text):
        data=self._post('SpeechSynthesizer',{'model':model,'input':{'text':text,'voice':voice_id,'format':'wav','sample_rate':24000}},True)
        url=(data.get('audio') or {}).get('url')
        if not isinstance(url,str):raise VoiceError('invalid_response',True)
        parsed=urlsplit(url)
        # Download only provider OSS output. Never forward credentials, redirects or arbitrary URLs.
        if parsed.scheme!='https' or parsed.port not in (None,443) or parsed.username or not re.fullmatch(r'[A-Za-z0-9-]+\.oss-[A-Za-z0-9-]+\.aliyuncs\.com',parsed.hostname or ''):
            raise VoiceError('invalid_audio_url',True)
        try:
            with requests.get(url,timeout=(10,120),stream=True,allow_redirects=False) as response:
                if response.status_code!=200:raise VoiceError('audio_download',True)
                pieces=[];size=0
                for piece in response.iter_content(65536):
                    size+=len(piece)
                    if size>100*1024*1024:raise VoiceError('audio_too_large',True)
                    pieces.append(piece)
                return b''.join(pieces)
        except requests.RequestException:raise VoiceError('audio_download',True) from None


def get_provider(cleanup=False,profile=None):
    from flask import current_app
    if current_app.testing and current_app.config.get('VOICE_TEST_PROVIDER'):
        return current_app.config['VOICE_TEST_PROVIDER']
    if not cleanup and not current_app.config.get('VOICE_COMPLIANCE_APPROVED'):raise VoiceError('compliance_pending')
    if len(current_app.secret_key or '')<32:raise VoiceError('configuration')
    if profile and profile.workspace_id!=current_app.config['VOICE_WORKSPACE_ID']:raise VoiceError('workspace_changed')
    return CosyVoiceProvider(current_app.config['VOICE_API_KEY'],current_app.config['VOICE_WORKSPACE_ID'])
