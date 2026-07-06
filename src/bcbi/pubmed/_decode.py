"""
XML 解码模块（私有）

将 PubMed E-utilities API 返回的 XML 数据解码为结构化的 Python 字典。

主要功能:
- decode_articles: 解码 efetch 返回的文章 XML

XML 结构说明:
- PubmedArticle: 期刊文章
- PubmedBookArticle: 书籍章节
"""

import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional, Tuple, Set


def decode_articles(root: ET.Element) -> List[Dict[str, Any]]:
    """
    将 efetch XML 解码为文章列表

    Args:
        root: XML 根元素，来自 efetch API 响应

    Returns:
        文章元数据字典列表，每个字典包含:
        - PMID: PubMed ID
        - Title: 文章标题
        - Authors: 作者全名列表（"姓 名"），含集体作者
        - Affiliations: 作者单位列表（去重）
        - Journal: 期刊名称
        - ISSN: 纸版 ISSN
        - EISSN: 电子版 ISSN
        - Volume: 卷
        - Issue: 期
        - Pages: 起止页码
        - PublicationDate: 发表日期
        - PublicationType: 出版类型列表（如 Review、Journal Article）
        - Language: 语言（如 eng）
        - PublicationStatus: 出版状态（ppublish/epublish/aheadofprint/ecollection）
        - History: 审稿与出版历史，键为状态，值为 "YYYY/M/D" 字符串
        - MeSH: MeSH 主题词列表（PubMed 官方风格，* 表示主要主题）
        - Keywords: 作者关键词列表
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


_ARTICLE_FIELDS = [
    "PMID", "Title", "Authors", "Affiliations", "Journal", "ISSN", "EISSN",
    "Volume", "Issue", "Pages", "PublicationDate", "PublicationType",
    "Language", "PublicationStatus", "History", "MeSH", "Keywords",
    "Abstract", "DOI", "PMCID",
]


def _build_article_dict(**kwargs: Any) -> Dict[str, Any]:
    """
    构造文章元数据 dict，统一字段顺序和完整性
    
    Args:
        **kwargs: 20 个字段的值，键必须与 _ARTICLE_FIELDS 一致
        
    Returns:
        按 _ARTICLE_FIELDS 顺序排列的字段字典
    """
    return {f: kwargs[f] for f in _ARTICLE_FIELDS}


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
    
    # 提取各字段（标题用 itertext 处理 <i>基因名</i> 等行内标记）
    title = _get_text_itertext(article_elem, ".//ArticleTitle", "无标题")
    abstract = _get_abstract(article_elem)
    authors = _get_authors(article_elem)
    affiliations = _get_affiliations(article_elem)
    journal = _get_text(article_elem, ".//Journal/Title", "无期刊信息")
    issn, eissn = _get_issn(article_elem)
    volume = _get_text(article_elem, ".//JournalIssue/Volume", "")
    issue = _get_text(article_elem, ".//JournalIssue/Issue", "")
    pages = _get_text(article_elem, ".//Pagination/MedlinePgn", "")
    date = _get_date(article_elem)
    pub_types = _get_publication_types(article_elem)
    language = _get_text(article_elem, ".//Language", "")
    pub_status = _get_text(elem, ".//PubmedData/PublicationStatus", "")
    history = _get_history(elem)
    mesh = _get_mesh(elem)
    keywords = _get_keywords(elem)
    # DOI/PMCID：限定在 PubmedData/ArticleIdList 子树，避免匹配 ReferenceList 中引用文献的 ID
    pubmed_data = elem.find(".//PubmedData")
    if pubmed_data is not None:
        doi = _get_text(pubmed_data, "ArticleIdList/ArticleId[@IdType='doi']", "")
        pmcid = _get_text(pubmed_data, "ArticleIdList/ArticleId[@IdType='pmc']", "")
    else:
        doi = pmcid = ""
    
    return _build_article_dict(
        PMID=pmid, Title=title, Authors=authors, Affiliations=affiliations,
        Journal=journal, ISSN=issn, EISSN=eissn, Volume=volume, Issue=issue,
        Pages=pages, PublicationDate=date, PublicationType=pub_types,
        Language=language, PublicationStatus=pub_status, History=history,
        MeSH=mesh, Keywords=keywords, Abstract=abstract, DOI=doi, PMCID=pmcid,
    )


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
    
    # 章节标题优先 ArticleTitle，fallback 到 Book/BookTitle（书籍概览记录无 ArticleTitle）
    # 用 itertext() 处理 <i>基因名</i>、GeneReviews<sup>®</sup> 等行内标记
    # 注意：不能用 `or`，Element 的 truthiness 基于子元素数量而非 None
    title_elem = book_doc.find("ArticleTitle")
    if title_elem is None:
        title_elem = book_doc.find(".//Book/BookTitle")
    title = "".join(title_elem.itertext()).strip() if title_elem is not None else "无标题"
    title = title or "无标题"
    
    # 章节作者及单位（仅 BookDocument 直接子级 AuthorList，排除 Book/AuthorList 中的编辑者）
    authors = _get_book_authors(book_doc)
    affiliations = _get_book_affiliations(book_doc)
    
    # 书籍系列名作为期刊字段（Book/BookTitle，用 itertext 处理 <sup> 等标记）
    book_title = book_doc.find(".//Book/BookTitle")
    journal = "".join(book_title.itertext()).strip() if book_title is not None else "无书籍信息"
    journal = journal or "无书籍信息"
    
    # 书籍章节通常无 ISSN（不像期刊文章），保留调用以兼容罕见情况
    issn, eissn = _get_issn(book_doc)
    volume = _get_text(book_doc, ".//Volume", "")
    issue = ""
    pages = _get_text(book_doc, ".//Pagination/MedlinePgn", "")
    
    # 发表日期：优先章节贡献日期，fallback 到书系列出版年
    # 注意：不能用 `or`，Element 的 truthiness 基于子元素数量而非 None
    pub_date = book_doc.find(".//ContributionDate/Year")
    if pub_date is None:
        pub_date = book_doc.find(".//Book/PubDate/Year")
    date = pub_date.text.strip() if pub_date is not None and pub_date.text else "无发表日期"
    
    # 出版类型、语言、MeSH、关键词
    pub_types = _get_book_publication_types(book_doc)
    language = _get_text(book_doc, ".//Language", "")
    mesh = _get_mesh(elem)
    keywords = _get_keywords(elem)
    
    # 摘要（可能有多个部分，用 itertext 处理行内标记）
    abstract = _get_abstract(book_doc)
    
    # PubmedBookArticle 用 PubmedBookData 而非 PubmedData
    pbd = elem.find("PubmedBookData")
    pub_status = _get_text(pbd, "PublicationStatus", "") if pbd is not None else ""
    history = _get_book_history(pbd) if pbd is not None else {}
    
    # DOI/PMCID：限定在 PubmedBookData/ArticleIdList 子树，避免匹配 ReferenceList 中引用文献的 ID
    doi = _get_text(pbd, "ArticleIdList/ArticleId[@IdType='doi']", "") if pbd is not None else ""
    pmcid = _get_text(pbd, "ArticleIdList/ArticleId[@IdType='pmc']", "") if pbd is not None else ""
    
    return _build_article_dict(
        PMID=pmid, Title=title, Authors=authors, Affiliations=affiliations,
        Journal=journal, ISSN=issn, EISSN=eissn, Volume=volume, Issue=issue,
        Pages=pages, PublicationDate=date, PublicationType=pub_types,
        Language=language, PublicationStatus=pub_status, History=history,
        MeSH=mesh, Keywords=keywords, Abstract=abstract, DOI=doi, PMCID=pmcid,
    )


def _get_text(elem: ET.Element, path: str, default: str = "") -> str:
    """
    安全获取 XML 元素文本

    与 _get_text_itertext 对纯空白元素返回 default 的行为保持一致。

    Args:
        elem: 父元素
        path: XPath 路径
        default: 默认值

    Returns:
        元素文本（已 strip）或默认值
    """
    found = elem.find(path)
    if found is None or not found.text or not found.text.strip():
        return default
    return found.text.strip()


def _get_text_itertext(elem: ET.Element, path: str, default: str = "") -> str:
    """
    安全获取 XML 元素文本，用 itertext() 处理行内标记

    用于 <i>基因名</i>、GeneReviews<sup>®</sup> 等含行内标记的文本提取，
    避免直接用 .text 导致标记后内容丢失。

    Args:
        elem: 父元素
        path: XPath 路径
        default: 默认值

    Returns:
        合并所有子元素后的元素文本或默认值
    """
    found = elem.find(path)
    if found is None:
        return default
    text = "".join(found.itertext()).strip()
    return text if text else default


def _get_abstract(elem: ET.Element) -> str:
    """
    获取摘要文本

    摘要可能包含多个 AbstractText 元素，需要合并。
    用 itertext() 处理 <i>基因名</i> 等行内标记，避免文本截断。
    保留 Label 属性（如 BACKGROUND/METHODS/RESULTS），格式 "LABEL: text"，
    匹配 PubMed 官网展示风格，便于下游分段检索。

    Args:
        elem: Article 或 BookDocument 元素

    Returns:
        合并后的摘要文本，结构化摘要各段以 "LABEL: " 前缀
    """
    parts = []
    for e in elem.findall(".//Abstract/AbstractText"):
        text = "".join(e.itertext()).strip()
        if not text:
            continue
        label = e.get("Label")
        if label:
            parts.append(f"{label}: {text}")
        else:
            parts.append(text)
    return "\n".join(parts) if parts else "无摘要"


def _get_authors(elem: ET.Element) -> List[str]:
    """
    获取作者全名列表
    
    普通作者取 "姓 名"（ForeName 缺失则仅姓），
    集体作者取 CollectiveName。
    
    Args:
        elem: Article 或 BookDocument 元素
        
    Returns:
        作者全名列表
    """
    authors: List[str] = []
    for a in elem.findall(".//Author"):
        last = a.findtext("LastName")
        fore = a.findtext("ForeName")
        coll = a.findtext("CollectiveName")
        if last and fore:
            authors.append(f"{last} {fore}")
        elif coll:
            authors.append(coll)
        elif last:
            authors.append(last)
    return authors


def _get_book_authors(book_doc: ET.Element) -> List[str]:
    """
    获取书籍章节作者全名列表
    
    仅取 BookDocument 直接子级 AuthorList 中的作者，
    排除 Book/AuthorList 中的书籍编辑者。
    
    Args:
        book_doc: BookDocument 元素
        
    Returns:
        章节作者全名列表
    """
    authors: List[str] = []
    for al in book_doc.findall("AuthorList"):
        for a in al.findall("Author"):
            last = a.findtext("LastName")
            fore = a.findtext("ForeName")
            coll = a.findtext("CollectiveName")
            if last and fore:
                authors.append(f"{last} {fore}")
            elif coll:
                authors.append(coll)
            elif last:
                authors.append(last)
    return authors


def _get_book_affiliations(book_doc: ET.Element) -> List[str]:
    """
    获取书籍章节作者单位列表（去重，保持出现顺序）

    仅取 BookDocument 直接子级 AuthorList 中的作者单位，
    排除 Book/AuthorList 中的书籍编辑者单位（与 _get_book_authors 对称）。

    Args:
        book_doc: BookDocument 元素

    Returns:
        去重后的章节作者单位列表
    """
    seen: Set[str] = set()
    affs: List[str] = []
    for al in book_doc.findall("AuthorList"):
        for a in al.findall("Author"):
            for aff in a.findall("AffiliationInfo/Affiliation"):
                if aff.text:
                    t = aff.text.strip()
                    if t and t not in seen:
                        seen.add(t)
                        affs.append(t)
    return affs


def _get_affiliations(elem: ET.Element) -> List[str]:
    """
    获取作者单位列表（去重，保持出现顺序）
    
    Args:
        elem: Article 或 BookDocument 元素
        
    Returns:
        去重后的作者单位列表
    """
    seen: Set[str] = set()
    affs: List[str] = []
    for a in elem.findall(".//AffiliationInfo/Affiliation"):
        if a.text:
            t = a.text.strip()
            if t and t not in seen:
                seen.add(t)
                affs.append(t)
    return affs


def _get_issn(elem: ET.Element) -> Tuple[str, str]:
    """
    获取 ISSN（纸版）和 EISSN（电子版）
    
    Args:
        elem: Article 或 BookDocument 元素
        
    Returns:
        (ISSN, EISSN) 元组，缺失为空字符串
    """
    issn = eissn = ""
    for e in elem.findall(".//ISSN"):
        t = e.get("IssnType")
        v = e.text.strip() if e.text else ""
        if t == "Print":
            issn = v
        elif t == "Electronic":
            eissn = v
    return issn, eissn


def _get_publication_types(elem: ET.Element) -> List[str]:
    """
    获取出版类型列表
    
    Args:
        elem: Article 或 BookDocument 元素
        
    Returns:
        出版类型列表（如 ["Review", "Journal Article"]）
    """
    return [e.text.strip() for e in elem.findall(".//PublicationTypeList/PublicationType") if e.text]


def _get_book_publication_types(book_doc: ET.Element) -> List[str]:
    """
    获取书籍章节的出版类型列表
    
    PubmedBookArticle 的 PublicationType 直接挂在 BookDocument 下，
    无 PublicationTypeList 包裹（与 PubmedArticle 不同）。
    
    Args:
        book_doc: BookDocument 元素
        
    Returns:
        出版类型列表（如 ["Review"]）
    """
    return [e.text.strip() for e in book_doc.findall("PublicationType") if e.text]


def _parse_history_dates(parent: ET.Element, path: str = ".//History/PubMedPubDate") -> Dict[str, str]:
    """
    解析 History/PubMedPubDate 列表为状态 -> 日期字符串字典

    Args:
        parent: 包含 History 的父元素（PubmedArticle/PubmedData 或 PubmedBookArticle/PubmedBookData）
        path: PubMedPubDate 的 XPath，默认递归查找

    Returns:
        状态 -> 日期字符串的字典，日期格式 "YYYY/M/D"（缺月/日则省略）
        常见键: received, revised, accepted, entrez, pubmed, medline, pmc-release
    """
    history: Dict[str, str] = {}
    for d in parent.findall(path):
        status = d.get("PubStatus")
        if not status:
            continue
        year = _format_date_part(d.findtext("Year"))
        if not year:
            continue
        month = _format_date_part(d.findtext("Month"))
        day = _format_date_part(d.findtext("Day"))
        date_str = year
        if month:
            date_str += f"/{month}"
            if day:
                date_str += f"/{day}"
        history[status] = date_str
    return history


def _get_history(elem: ET.Element) -> Dict[str, str]:
    """
    获取审稿与出版历史

    Args:
        elem: PubmedArticle 元素

    Returns:
        状态 -> 日期字符串的字典
    """
    return _parse_history_dates(elem, ".//PubmedData/History/PubMedPubDate")


def _get_book_history(pubmed_book_data: ET.Element) -> Dict[str, str]:
    """
    获取书籍章节的审稿与出版历史

    Args:
        pubmed_book_data: PubmedBookData 元素

    Returns:
        状态 -> 日期字符串的字典
    """
    return _parse_history_dates(pubmed_book_data, ".//History/PubMedPubDate")


def _get_mesh(elem: ET.Element) -> List[str]:
    """
    获取 MeSH 主题词列表（PubMed 官方风格）
    
    格式:
    - 主要主题加 * 前缀
    - 子标题以 / 分隔，如 "Colitis, Ulcerative/epidemiology/therapy"
    
    Args:
        elem: PubmedArticle 或 PubmedBookArticle 元素
        
    Returns:
        MeSH 主题词列表
    """
    result: List[str] = []
    for mh in elem.findall(".//MeshHeadingList/MeshHeading"):
        desc = mh.find("DescriptorName")
        if desc is None or not desc.text:
            continue
        major = desc.get("MajorTopicYN") == "Y"
        quals = [q.text.strip() for q in mh.findall("QualifierName") if q.text]
        s = ("*" if major else "") + desc.text.strip()
        if quals:
            s += "/" + "/".join(quals)
        result.append(s)
    return result


def _get_keywords(elem: ET.Element) -> List[str]:
    """
    获取作者关键词列表
    
    Args:
        elem: PubmedArticle 或 PubmedBookArticle 元素
        
    Returns:
        关键词列表
    """
    return [e.text.strip() for e in elem.findall(".//KeywordList/Keyword") if e.text]


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
        return year.text.strip()

    medline = elem.find(".//PubDate/MedlineDate")
    return medline.text.strip() if medline is not None and medline.text else "无发表日期"


def _format_date_part(s: Optional[str]) -> str:
    """
    规范化日期片段（年/月/日）

    数字字符串去除前导零（"09" -> "9"，适配 PubMed History 中混合的 "01"~"12" 与 "1"~"9" 格式）；
    非数字字符串（历史罕见文本月份）保持原样。

    Args:
        s: 日期片段原始文本

    Returns:
        规范化后的字符串，空输入返回空字符串
    """
    if not s:
        return ""
    try:
        return str(int(s))
    except (ValueError, TypeError):
        return s.strip()
