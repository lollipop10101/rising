from __future__ import annotations
import os, yaml
from dotenv import load_dotenv
load_dotenv()
def load_yaml_config(path='config.yaml'):
    try:
        with open(path,'r',encoding='utf-8') as f: return yaml.safe_load(f) or {}
    except FileNotFoundError: return {}
def nested_get(c,path,default):
    cur=c
    for p in path.split('.'):
        if not isinstance(cur,dict) or p not in cur: return default
        cur=cur[p]
    return cur
def env_or_cfg(key,c,path,default): return os.getenv(key) or nested_get(c,path,default)
def to_int(v,default=0):
    try: return int(v)
    except Exception: return default
def to_float(v,default=0.0):
    try: return float(v)
    except Exception: return default
