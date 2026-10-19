#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DeepSeek 联调自检脚本（memoir-prototype 配套）

用法（在服务器上，venv 已激活、项目目录下）：
    python3 deepseek_check.py              # 只检配置 + 密钥有效性（不花 token）
    python3 deepseek_check.py --chat       # 再发一次最小 chat 请求，验证端到端（几分钱）

读 key 的顺序：环境变量 DEEPSEEK_API_KEY > 同目录 .env 文件。
"""
import json
import os
import sys
import urllib.request
import urllib.error

BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-flash")

failures = []


def ok(msg):
    print("[OK] " + msg)


def bad(msg):
    print("[FAIL] " + msg)
    failures.append(msg)


def load_dotenv(path=".env"):
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip("'\"")
            if k and k not in os.environ:
                os.environ[k] = v


def main():
    load_dotenv()
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()

    # 1. 配置检查
    if key:
        ok("DEEPSEEK_API_KEY 已设置（长度 %d，前 6 位 %s…）" % (len(key), key[:6]))
    else:
        bad("DEEPSEEK_API_KEY 未设置：网页 /ask 会显示“AI 未启用：请联系管理员配置 DEEPSEEK_API_KEY”\n"
            "      修复：在 .env 或环境变量里加 DEEPSEEK_API_KEY=你的key，然后重启 gunicorn")
    print("      当前模型默认：%s（2026-10-19 官方仍有效，调用方式不变）" % MODEL)
    print("      接口地址：%s" % BASE_URL)
    if not key:
        sys.exit(2)

    headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}

    # 2. 密钥有效性（GET /models，不花 token）
    try:
        req = urllib.request.Request(BASE_URL + "/models", headers=headers)
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.load(r)
        ids = [m.get("id") for m in data.get("data", [])]
        if MODEL in ids:
            ok("密钥有效，/models 返回含 %s（共 %d 个模型）" % (MODEL, len(ids)))
        else:
            bad("密钥有效但模型列表里没有 %s（实际有：%s），先别改代码，把报错发过来" % (MODEL, ids))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")[:200]
        if e.code == 401:
            bad("密钥被拒（401）：key 错了或被禁用——去 DeepSeek 开发者平台重新复制，确认没多空格/换行")
        elif e.code == 429:
            ok("密钥有效但触发限速（429）：等一分钟再跑")
        else:
            bad("接口返回 %s：%s" % (e.code, body))
        print("\n" + "\n".join(failures))
        sys.exit(2)
    except Exception as e:
        bad("连不上 %s：%s（服务器出境网络或 DNS 问题，ping 下 api.deepseek.com 试试）" % (BASE_URL, e))
        print("\n" + "\n".join(failures))
        sys.exit(2)

    # 3. 端到端 chat（可选，极小 token）
    if "--chat" in sys.argv:
        payload = json.dumps({
            "model": MODEL,
            "messages": [{"role": "user", "content": "只回复 OK"}],
            "max_tokens": 5,
        }).encode()
        try:
            req = urllib.request.Request(BASE_URL + "/chat/completions", data=payload, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.load(r)
            text = data["choices"][0]["message"]["content"].strip()
            ok("chat 端到端通：模型回了「%s」" % text)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "ignore")[:200]
            if e.code == 429:
                ok("密钥有效，chat 触发并发限速（429）：网页会显示“AI 繁忙请稍后再试”，等一会重试")
            else:
                bad("chat 返回 %s：%s" % (e.code, body))
        except Exception as e:
            bad("chat 请求失败：%s" % e)

    print()
    if failures:
        print("发现 %d 个问题，见上。修完重跑。" % len(failures))
        sys.exit(2)

    print("配置层全部通过。网页端这样验（用种子数据）：")
    print("  1. 打开任意家庭的 🤖 问 AI，问“这个家有几个人物”——应引用知识库作答，注明来源")
    print("  2. 周报页点“生成 AI 导读”（管理员）——导读+3 条看点，按周缓存")
    print("  3. 写作计划页点“✨ AI 给出计划建议”——长辈优先排序")
    print("网页报错对照：401=key 错；429=AI 繁忙稍后再试；“AI 未启用”=环境变量没进 gunicorn（检查 .env + 重启）")


if __name__ == "__main__":
    main()
