"""
BCBI - 生物计算与生物信息学工具包

提供文献搜索、数据分析等生物信息学常用功能。

子模块:
- pubmed: PubMed 文献搜索与获取

快速开始:
    >>> from bcbi import pubmed
    >>> 
    >>> # 搜索文献
    >>> result = pubmed.search("CRISPR")
    >>> print(f"找到 {result['count']} 篇文献")
    >>> 
    >>> # 获取文献详情
    >>> result = pubmed.search("CRISPR", retmax=10)
    >>> articles = pubmed.fetch(result['ids'])
    >>> for article in articles:
    ...     print(f"{article['PMID']}: {article['Title']}")
    >>> 
    >>> # 批量导出
    >>> result = pubmed.bulk_export("COVID-19", output_dir="./output")
    >>> print(f"导出到 {result['output_file']}")

更多文档:
- GitHub: https://github.com/yourusername/bcbi
- PubMed API: https://www.ncbi.nlm.nih.gov/books/NBK25500/
"""

from bcbi import pubmed

__version__ = "0.1.0"

__all__ = ["pubmed"]
