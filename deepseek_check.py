#!/usr/bin/env python3
"""与应用共用配置的模型自检；--chat 可发送一次最小请求并产生实际用量。"""
import json
import sys
import urllib.error
import urllib.request

from config import Config


def run_check(config=Config, chat=False, open_url=None):
    open_url=open_url or urllib.request.urlopen
    if not config.DEEPSEEK_API_KEY:
        print('[FAIL] AI 凭据未配置；请在受限配置中填写后再检查。')
        return 2
    print('[OK] AI 凭据已配置（不输出内容）。')
    base=config.DEEPSEEK_BASE_URL.rstrip('/')
    headers={'Authorization':'Bearer '+config.DEEPSEEK_API_KEY,'Content-Type':'application/json'}
    try:
        request=urllib.request.Request(base+'/models',headers=headers)
        with open_url(request,timeout=20) as response:data=json.load(response)
        if config.DEEPSEEK_MODEL not in [model.get('id') for model in data.get('data',[])]:
            print('[FAIL] 当前配置的模型不在返回列表中，请核对服务账户。')
            return 2
        print('[OK] 模型列表检查通过；这不代表问答全流程已验收。')
        if chat:
            payload=json.dumps({'model':config.DEEPSEEK_MODEL,'messages':[{'role':'user','content':'只回复 OK'}],'max_tokens':5}).encode()
            request=urllib.request.Request(base+'/chat/completions',data=payload,headers=headers)
            with open_url(request,timeout=60) as response:data=json.load(response)
            if not data['choices'][0]['message']['content'].strip():raise ValueError('empty')
            print('[OK] 最小模型请求收到非空回复；请继续在专门测试家庭核验网页、来源和失败恢复。')
        return 0
    except urllib.error.HTTPError as error:
        print('[FAIL] 服务返回 HTTP %s；限速、鉴权或服务失败均不计为通过。' % error.code)
    except Exception:
        print('[FAIL] 连接或响应校验失败，请核对网络、服务地址和配置（不输出响应正文或凭据）。')
    return 2


def main():
    return run_check(chat='--chat' in sys.argv)


if __name__=='__main__':raise SystemExit(main())
