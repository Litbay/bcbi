"""
XML 解码模块（私有）

将 PubMed E-utilities API 返回的 XML 数据解码为结构化的 Python 字典。

主要功能:
- decode_articles: 解码 efetch 返回的文章 XML
- decode_search_result: 解码 esearch 返回的搜索结果 XML

XML 结构说明:
- PubmedArticle: 期刊文章
- PubmedBookArticle: 书籍章节
"""

import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional


def decode_articles(root: ET.Element) -> List[Dict[str, Any]]:
    """
    将 efetch XML 解码为文章列表
    
    Args:
        root: XML 根元素，来自 efetch API 响应
        
    Returns:
        文章元数据字典列表，每个字典包含:
        - PMID: PubMed ID
        - Title: 文章标题
        - Authors: 作者列表（逗号分隔）
        - Journal: 期刊名称
        - PublicationDate: 发表日期
        - Abstract: 摘要
        - DOI: 数字对象标识符
        - PMCID: PubMed Central ID
    
    Example:
        >>> root = ET.fromstring(xml_content)
        >>> articles = decode_articles(root)
        >>> print(articles[0]['Title'])
    """
    articles = []
    
    # 解码期刊文章
    for elem in root.findall(".//PubmedArticle"):
        article = _decode_article(elem)
        if article:
            articles.append(article)
    
    # 解码书籍章节
    for elem in root.findall(".//PubmedBookArticle"):
        article = _decode_book(elem)
        if article:
            articles.append(article)
    
    return articles


def decode_search_result(root: ET.Element) -> Dict[str, Any]:
    """
    将 esearch XML 解码为结果字典
    
    Args:
        root: XML 根元素，来自 esearch API 响应
        
    Returns:
        字典包含:
        - count: 符合条件的总文献数
        - webenv: Web Environment 字符串（用于后续请求）
        - query_key: Query Key（用于后续请求）
        - ids: PMID 列表
    
    Example:
        >>> root = ET.fromstring(xml_content)
        >>> result = decode_search_result(root)
        >>> print(f"找到 {result['count']} 篇文献")
    """
    def text(tag: str) -> str:
        """安全获取元素文本"""
        elem = root.find(tag)
        return elem.text.strip() if elem is not None and elem.text else ""
    
    result = {
        "count": int(text("Count") or 0),
        "webenv": text("WebEnv"),
        "query_key": text("QueryKey"),
    }
    
    # 提取 PMID 列表
    id_list = root.find("IdList")
    result["ids"] = [e.text.strip() for e in id_list.findall("Id") if e.text] if id_list is not None else []
    
    return result


def _decode_article(elem: ET.Element) -> Optional[Dict[str, Any]]:
    """
    解码单个 PubmedArticle 元素
    
    Args:
        elem: PubmedArticle XML 元素
        
    Returns:
        文章元数据字典，解析失败返回 None
    """
    pmid_elem = elem.find(".//MedlineCitation/PMID")
    article_elem = elem.find(".//Article")
    
    # 验证必要元素存在
    if pmid_elem is None or article_elem is None:
        return None
    
    pmid = pmid_elem.text.strip() if pmid_elem.text else ""
    if not pmid:
        return None
    
    # 提取各字段
    title = _get_text(article_elem, ".//ArticleTitle", "无标题")
    abstract = _get_abstract(article_elem)
    authors = _get_authors(article_elem)
    journal = _get_text(article_elem, ".//Journal/Title", "无期刊信息")
    date = _get_date(article_elem)
    doi = _get_text(elem, ".//ArticleId[@IdType='doi']", "")
    pmcid = _get_text(elem, ".//ArticleId[@IdType='pmc']", "")
    
    return {
        "PMID": pmid,
        "Title": title,
        "Authors": authors,
        "Journal": journal,
        "PublicationDate": date,
        "Abstract": abstract,
        "DOI": doi,
        "PMCID": pmcid,
    }


def _decode_book(elem: ET.Element) -> Optional[Dict[str, Any]]:
    """
    解码单个 PubmedBookArticle 元素（书籍章节）
    
    Args:
        elem: PubmedBookArticle XML 元素
        
    Returns:
        文章元数据字典，解析失败返回 None
    """
    book_doc = elem.find("BookDocument")
    if book_doc is None:
        return None
    
    pmid = _get_text(book_doc, ".//PMID", "")
    if not pmid:
        return None
    
    # 书籍章节的标题可能在 BookTitle 或 ArticleTitle
    title_elem = book_doc.find(".//Book/BookTitle") or book_doc.find(".//ArticleTitle")
    title = title_elem.text if title_elem is not None and title_elem.text else "无标题"
    
    # 提取作者
    authors = []
    for e in book_doc.findall(".//Author"):
        name = e.find("LastName")
        if name is not None and name.text:
            authors.append(name.text)
    
    # 书籍名称作为期刊字段
    book_title = book_doc.find(".//Book/Title")
    journal = book_title.text if book_title is not None and book_title.text else "无书籍信息"
    
    # 发表日期
    pub_date = book_doc.find(".//PubDate/Year") or elem.find(".//PubDate/Year")
    date = pub_date.text if pub_date is not None and pub_date.text else "无发表日期"
    
    # 摘要（可能有多个部分）
    abstract_parts = [e.text for e in book_doc.findall(".//Abstract/AbstractText") if e.text]
    abstract = "\n".join(abstract_parts) if abstract_parts else "无摘要"
    
    # DOI 和 PMCID
    doi_elem = elem.find(".//ArticleId[@IdType='doi']")
    pmcid_elem = elem.find(".//ArticleId[@IdType='pmc']")
    
    return {
        "PMID": pmid,
        "Title": title,
        "Authors": ", ".join(authors) if authors else "无作者信息",
        "Journal": journal,
        "PublicationDate": date,
        "Abstract": abstract,
        "DOI": doi_elem.text if doi_elem is not None and doi_elem.text else "",
        "PMCID": pmcid_elem.text if pmcid_elem is not None and pmcid_elem.text else "",
    }


def _get_text(elem: ET.Element, path: str, default: str = "") -> str:
    """
    安全获取 XML 元素文本
    
    Args:
        elem: 父元素
        path: XPath 路径
        default: 默认值
        
    Returns:
        元素文本或默认值
    """
    found = elem.find(path)
    return found.text if found is not None and found.text else default


def _get_abstract(elem: ET.Element) -> str:
    """
    获取摘要文本
    
    摘要可能包含多个 AbstractText 元素，需要合并。
    
    Args:
        elem: Article 元素
        
    Returns:
        合并后的摘要文本
    """
    parts = [e.text for e in elem.findall(".//Abstract/AbstractText") if e.text]
    return "\n".join(parts) if parts else "无摘要"


def _get_authors(elem: ET.Element) -> str:
    """
    获取作者列表
    
    提取所有作者的姓氏，用逗号分隔。
    
    Args:
        elem: Article 元素
        
    Returns:
        作者列表字符串
    """
    names = [e.text for e in elem.findall(".//Author/LastName") if e.text]
    return ", ".join(names) if names else "无作者信息"


def _get_date(elem: ET.Element) -> str:
    """
    获取发表日期
    
    优先使用 Year，如果不存在则使用 MedlineDate。
    
    Args:
        elem: Article 元素
        
    Returns:
        发表年份或日期字符串
    """
    year = elem.find(".//PubDate/Year")
    if year is not None and year.text:
        return year.text
    
    medline = elem.find(".//PubDate/MedlineDate")
    return medline.text if medline is not None and medline.text else "无发表日期"
