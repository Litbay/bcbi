"""
PubMed 子模块

提供 PubMed 文献搜索与获取功能。

主要组件:
- Credentials: API 凭据配置
- Client: 底层 API 客户端
- search(): 搜索文献
- fetch(): 获取文献详情
- bulk_export(): 批量导出到文件

快速开始:
    >>> from bcbi import pubmed
    >>> 
    >>> # 搜索文献
    >>> result = pubmed.search("CRISPR", retmax=10)
    >>> print(f"找到 {result['count']} 篇")
    >>> 
    >>> # 获取文献详情
    >>> articles = pubmed.fetch(result['ids'])
    >>> print(articles[0]['Title'])
    >>> 
    >>> # 批量导出
    >>> pubmed.bulk_export("COVID-19", output_dir="./output")

API 凭据:
    提供 NCBI API Key 可将速率限制从 3 req/s 提升到 10 req/s。
    申请地址: https://www.ncbi.nlm.nih.gov/account/settings/apikeys/
    
    >>> creds = pubmed.Credentials(
    ...     api_key="your-api-key",
    ...     email="your@email.com",
    ...     tool="my-app"
    ... )
    >>> result = pubmed.search("CRISPR", credentials=creds)
"""

from .api import (
    search,
    fetch,
    bulk_export,
)
from .client import Credentials, Client

__all__ = [
    "Credentials",
    "search",
    "fetch",
    "bulk_export",
    "Client",
]
