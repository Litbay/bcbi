"""
PubMed API 客户端模块

提供与 NCBI E-utilities API 的底层交互:
- Credentials: API 凭据
- Client: HTTP 客户端，处理请求、限速和重试
- TokenBucket: 令牌桶限速器
"""

import sys
import time
import random
import threading
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
import xml.etree.ElementTree as ET

try:
    import requests
except ImportError:
    print("错误: 需要安装 requests")
    print("安装命令: pip install requests")
    sys.exit(1)


class TokenBucket:
    """令牌桶限速器，支持高并发和平滑限速"""
    
    def __init__(self, rate: float, capacity: int):
        self.rate = rate
        self.capacity = capacity
        self.tokens = float(capacity)
        self.last_update = time.time()
        self._lock = threading.Lock()
    
    def acquire(self, timeout: Optional[float] = None) -> bool:
        """获取1个令牌，超时返回 False"""
        start_time = time.time()
        
        while True:
            with self._lock:
                now = time.time()
                elapsed = now - self.last_update
                self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
                self.last_update = now
                
                if self.tokens >= 1:
                    self.tokens -= 1
                    return True
                
                wait_time = (1 - self.tokens) / self.rate
            
            if timeout is not None:
                remaining = timeout - (time.time() - start_time)
                if remaining <= 0:
                    return False
                wait_time = min(wait_time, remaining)
            
            time.sleep(max(0.001, wait_time))
    
    def try_acquire(self) -> bool:
        """尝试获取令牌，不等待"""
        with self._lock:
            now = time.time()
            elapsed = now - self.last_update
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.last_update = now
            
            if self.tokens >= 1:
                self.tokens -= 1
                return True
            return False


@dataclass
class Credentials:
    """PubMed API 凭据"""
    api_key: str = ""
    email: str = ""
    tool: str = ""
    
    def __hash__(self):
        return hash((self.api_key, self.email, self.tool))


class Client:
    """PubMed API 客户端"""
    
    BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    _session_pool: Dict[Credentials, requests.Session] = {}
    _bucket_pool: Dict[Credentials, TokenBucket] = {}
    _stats_pool: Dict[Credentials, Dict[str, Any]] = {}
    
    def __init__(self, credentials: Optional[Credentials] = None):
        self.credentials = credentials or Credentials()
        self.session = self._get_session(self.credentials)
        self._bucket = self._get_bucket(self.credentials)
    
    @classmethod
    def _get_session(cls, creds: Credentials) -> requests.Session:
        if creds not in cls._session_pool:
            session = requests.Session()
            session.headers.update({
                'User-Agent': f'{creds.tool or "bcbi"}/1.0 ({creds.email or "anonymous"})'
            })
            cls._session_pool[creds] = session
        return cls._session_pool[creds]
    
    @classmethod
    def _get_bucket(cls, creds: Credentials) -> TokenBucket:
        if creds not in cls._bucket_pool:
            has_full_creds = creds.api_key and creds.email and creds.tool
            rate = 10.0 if has_full_creds else 3.0
            capacity = int(rate * 3)
            cls._bucket_pool[creds] = TokenBucket(rate=rate, capacity=capacity)
        return cls._bucket_pool[creds]
    
    @classmethod
    def _get_stats(cls, creds: Credentials) -> Dict[str, Any]:
        if creds not in cls._stats_pool:
            cls._stats_pool[creds] = {
                'total_requests': 0,
                'success_requests': 0,
                'failed_requests': 0,
                'retries': 0,
                'start_time': None,
            }
        return cls._stats_pool[creds]
    
    @classmethod
    def get_stats(cls, credentials: Optional[Credentials] = None) -> Dict[str, Any]:
        """获取请求统计"""
        creds = credentials or Credentials()
        stats = cls._get_stats(creds)
        
        elapsed = 0
        if stats['start_time']:
            elapsed = time.time() - stats['start_time']
        
        rps = stats['total_requests'] / elapsed if elapsed > 0 else 0
        error_rate = stats['failed_requests'] / stats['total_requests'] * 100 if stats['total_requests'] > 0 else 0
        
        return {
            'total_requests': stats['total_requests'],
            'success_requests': stats['success_requests'],
            'failed_requests': stats['failed_requests'],
            'retries': stats['retries'],
            'elapsed_time': elapsed,
            'requests_per_second': rps,
            'error_rate': error_rate,
        }
    
    @classmethod
    def reset_stats(cls, credentials: Optional[Credentials] = None):
        """重置请求统计"""
        creds = credentials or Credentials()
        cls._stats_pool[creds] = {
            'total_requests': 0,
            'success_requests': 0,
            'failed_requests': 0,
            'retries': 0,
            'start_time': None,
        }
    
    @classmethod
    def clear_session_pool(cls):
        """清理 Session 池"""
        for session in cls._session_pool.values():
            session.close()
        cls._session_pool.clear()
        cls._bucket_pool.clear()
        cls._stats_pool.clear()
    
    def esearch(
        self,
        term: str,
        retmax: int = 0,
        usehistory: bool = True,
        **options
    ) -> Dict[str, Any]:
        """执行 ESearch 请求"""
        params = self._build_params({
            "db": "pubmed",
            "term": term,
            "retmax": str(retmax),
        })
        
        if usehistory:
            params["usehistory"] = "y"
        if "mindate" in options:
            params["mindate"] = options["mindate"]
        if "maxdate" in options:
            params["maxdate"] = options["maxdate"]
        if "sort" in options:
            params["sort"] = options["sort"]
        
        root = self._request("esearch.fcgi", params)
        if root is None:
            return {"count": 0, "webenv": "", "query_key": "", "ids": []}
        
        def text(tag: str) -> str:
            elem = root.find(tag)
            return elem.text.strip() if elem is not None and elem.text else ""
        
        id_list = root.find("IdList")
        ids = [e.text.strip() for e in id_list.findall("Id") if e.text] if id_list is not None else []
        
        return {
            "count": int(text("Count") or 0),
            "webenv": text("WebEnv"),
            "query_key": text("QueryKey"),
            "ids": ids,
        }
    
    def efetch(
        self,
        ids: Optional[List[str]] = None,
        webenv: Optional[str] = None,
        query_key: Optional[str] = None,
        retstart: int = 0,
        retmax: int = 200,
        decode: bool = True,
    ) -> Any:
        """执行 EFetch 请求"""
        params = self._build_params({
            "db": "pubmed",
            "retstart": str(retstart),
            "retmax": str(retmax),
        })
        
        if ids:
            params["id"] = ",".join(str(i) for i in ids)
        elif webenv and query_key:
            params["WebEnv"] = webenv
            params["query_key"] = query_key
        else:
            return [] if decode else None
        
        root = self._request("efetch.fcgi", params)
        if root is None:
            return [] if decode else None
        
        if not decode:
            return root
        
        from bcbi.pubmed._decode import decode_articles
        return decode_articles(root)
    
    def _build_params(self, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        params = {'retmode': 'xml'}
        if self.credentials.api_key:
            params['api_key'] = self.credentials.api_key
        if self.credentials.email:
            params['email'] = self.credentials.email
        if self.credentials.tool:
            params['tool'] = self.credentials.tool
        if extra:
            params.update(extra)
        return params
    
    def _request(self, endpoint: str, params: Dict[str, Any]) -> Optional[ET.Element]:
        """发送 HTTP 请求，自动处理限速和重试"""
        url = f"{self.BASE_URL}/{endpoint}"
        
        stats = Client._get_stats(self.credentials)
        if stats['start_time'] is None:
            stats['start_time'] = time.time()
        
        self._bucket.acquire()
        
        for attempt in range(1, 6):
            stats['total_requests'] += 1
            
            try:
                resp = self.session.request("GET", url, params=params, timeout=30)
                
                if resp.status_code == 200:
                    try:
                        result = ET.fromstring(resp.content)
                        stats['success_requests'] += 1
                        return result
                    except Exception:
                        stats['failed_requests'] += 1
                        return None
                
                if resp.status_code not in (429, 500, 502, 503, 504):
                    stats['failed_requests'] += 1
                    return None
                
                if attempt > 1:
                    stats['retries'] += 1
                
                sleep = self._backoff(attempt, resp)
                time.sleep(sleep)
                
            except Exception:
                if attempt > 1:
                    stats['retries'] += 1
                    
                if attempt >= 5:
                    stats['failed_requests'] += 1
                    return None
                time.sleep(self._backoff(attempt))
        
        stats['failed_requests'] += 1
        return None
    
    def _backoff(self, attempt: int, resp: Optional[requests.Response] = None) -> float:
        """计算退避时间（指数退避，最大 60 秒）"""
        base = min(1.0 * (2 ** (attempt - 1)), 60.0)
        
        if resp and resp.status_code == 429:
            try:
                return float(int(resp.headers.get("Retry-After", "0")))
            except Exception:
                pass
        
        return base + random.uniform(0, 0.25 * base)
