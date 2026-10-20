#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
构建云端记录索引 data/_index.json

两种模式：
  1) 本地/远程：从 GitHub API 读取 data/*.json，生成索引（需要 PAT）
     python tools/build_index.py --token ghp_xxx
  2) CI 模式：直接读本地仓库目录（GitHub Actions 用，无需 token）
     python tools/build_index.py --from-local .

索引结构（query.html 依赖）：
[
  {"id","customer","position","dateTime","photoCount","hasVideo","remark","updatedAt","thumb"}
]
"""
import argparse
import base64
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

USER = 'yuanhangkai'
REPO = 'fsint-viewer'
BRANCH = 'main'
OUT_NAME = '_index.json'


def summarize(rid, j):
    photos = [p for p in (j.get('photos') or []) if p]
    return {
        'id': rid,
        'customer': (j.get('customer') or '').strip(),
        'position': (j.get('position') or '').strip(),
        'dateTime': (j.get('dateTime') or '').strip(),
        'photoCount': len(photos),
        'hasVideo': bool(j.get('video')),
        'remark': (j.get('remark') or '').strip()[:80],
        'updatedAt': int(j.get('updatedAt') or 0),
        'thumb': photos[0] if photos else '',
    }


def build_from_local(root):
    data_dir = os.path.join(root, 'data')
    if not os.path.isdir(data_dir):
        print(f'✗ 找不到目录: {data_dir}')
        sys.exit(1)
    out = []
    for name in sorted(os.listdir(data_dir)):
        if not name.endswith('.json') or name == OUT_NAME:
            continue
        p = os.path.join(data_dir, name)
        try:
            with open(p, 'r', encoding='utf-8') as f:
                j = json.load(f)
        except Exception as e:
            print(f'  ⚠ 跳过 {name}: {e}')
            continue
        out.append(summarize(name[:-5], j))
    return out


def build_from_api(token):
    import requests
    H = {'Authorization': 'token ' + token, 'Accept': 'application/vnd.github+json'}
    r = requests.get(
        f'https://api.github.com/repos/{USER}/{REPO}/contents/data',
        headers=H, params={'ref': BRANCH}, timeout=30)
    r.raise_for_status()
    items = [x for x in r.json() if x['name'].endswith('.json') and x['name'] != OUT_NAME]
    print(f'  发现 {len(items)} 个记录文件')

    def fetch(it):
        try:
            rr = requests.get(
                f'https://api.github.com/repos/{USER}/{REPO}/contents/data/{it["name"]}',
                headers=H, params={'ref': BRANCH}, timeout=30)
            if rr.status_code != 200:
                print(f'  ⚠ {it["name"]}: HTTP {rr.status_code}')
                return None
            j = json.loads(base64.b64decode(rr.json()['content']).decode('utf-8'))
            return summarize(it['name'][:-5], j)
        except Exception as e:
            print(f'  ⚠ {it["name"]}: {e}')
            return None

    out = []
    with ThreadPoolExecutor(max_workers=10) as ex:
        for i, res in enumerate(ex.map(fetch, items), 1):
            if res:
                out.append(res)
            if i % 25 == 0:
                print(f'  已读取 {i}/{len(items)}')
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--token', default=os.environ.get('GH_TOKEN', ''))
    ap.add_argument('--from-local', default='')
    ap.add_argument('--out', default='')
    args = ap.parse_args()

    if args.from_local:
        records = build_from_local(args.from_local)
    else:
        if not args.token:
            print('✗ 需要 --token 或 GH_TOKEN')
            sys.exit(1)
        records = build_from_api(args.token)

    records.sort(key=lambda x: (x['updatedAt'], x['dateTime']), reverse=True)

    # 紧凑输出：一行一条，省体积
    body = '[\n' + ',\n'.join(
        json.dumps(r, ensure_ascii=False, separators=(',', ':')) for r in records
    ) + '\n]\n'

    out_path = args.out
    if not out_path:
        base = args.from_local or '.'
        out_path = os.path.join(base, 'data', OUT_NAME)
    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(body)

    print(f'✓ 索引写入 {out_path}')
    print(f'  记录数: {len(records)}')
    print(f'  体积: {len(body.encode("utf-8"))} bytes')


if __name__ == '__main__':
    main()
