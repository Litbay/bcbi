"""
用户 API 模块

提供简洁易用的高层接口:
- search(): 搜索文献
- fetch(): 获取文献详情（支持并发）
- bulk_export(): 批量导出到 JSONL
"""

import json
import time
import shutil
import tempfile
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from bcbi.pubmed.client import Client, Credentials
from bcbi.pubmed._util import chunk_dates, dedupe_jsonl, Output


def _get_max_workers(credentials: Optional[Credentials]) -> int:
    """根据凭据返回合适的并发数"""
    has_key = credentials and credentials.api_key and credentials.email and credentials.tool
    return 10 if has_key else 5


def _get_segment_workers(credentials: Optional[Credentials]) -> int:
    """根据凭据返回合适的段并发数"""
    has_key = credentials and credentials.api_key and credentials.email and credentials.tool
    return 5 if has_key else 3


def search(
    term: str,
    credentials: Optional[Credentials] = None,
    retmax: int = 0,
    **options
) -> Dict[str, Any]:
    """搜索 PubMed 文献"""
    client = Client(credentials)
    return client.esearch(term, retmax=retmax, **options)


def fetch(
    pmids: Optional[List[str]] = None,
    webenv: Optional[str] = None,
    query_key: Optional[str] = None,
    credentials: Optional[Credentials] = None,
    retstart: int = 0,
    retmax: int = 200,
    batch_size: int = 1000,
    max_workers: Optional[int] = None,
    _client: Optional[Client] = None,
) -> List[Dict[str, Any]]:
    """获取文献元数据（支持并发）"""
    client = _client if _client is not None else Client(credentials)
    
    if max_workers is None:
        max_workers = _get_max_workers(credentials)
    
    if webenv and query_key:
        return _fetch_by_webenv(client, webenv, query_key, retstart, retmax, batch_size, max_workers)
    
    if not pmids:
        return []
    
    return _fetch_by_pmids(client, pmids, batch_size, max_workers)


def _fetch_by_webenv(
    client: Client,
    webenv: str,
    query_key: str,
    retstart: int,
    retmax: int,
    batch_size: int,
    max_workers: int,
) -> List[Dict[str, Any]]:
    """通过 WebEnv 获取文献"""
    if max_workers <= 1:
        return client.efetch(webenv=webenv, query_key=query_key, retstart=retstart, retmax=retmax)
    
    all_articles: List[Dict[str, Any]] = []
    failed_batches: List[Tuple[int, int, int]] = []  # (start, expected_size, retry_count)
    
    batches = [
        (retstart + i * batch_size, min(batch_size, retmax - i * batch_size))
        for i in range((retmax + batch_size - 1) // batch_size)
    ]
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(client.efetch, None, webenv, query_key, start, size): (start, size)
            for start, size in batches
        }
        
        for future in as_completed(futures):
            start, expected_size = futures[future]
            try:
                articles = future.result()
                if articles is not None and len(articles) >= expected_size:
                    all_articles.extend(articles)
                else:
                    failed_batches.append((start, expected_size, 0))
            except Exception:
                failed_batches.append((start, expected_size, 0))
    
    if failed_batches:
        all_articles.extend(_retry_batches_until_complete(client, webenv, query_key, failed_batches))
    
    return all_articles


def _fetch_by_pmids(
    client: Client,
    pmids: List[str],
    batch_size: int,
    max_workers: int,
) -> List[Dict[str, Any]]:
    """通过 PMID 列表获取文献"""
    if max_workers <= 1:
        return client.efetch(ids=pmids)
    
    batches = [pmids[i:i + batch_size] for i in range(0, len(pmids), batch_size)]
    all_articles: List[Dict[str, Any]] = []
    failed_batches: List[Tuple[List[str], int]] = []  # (batch, retry_count)
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(client.efetch, batch): batch for batch in batches}
        
        for future in as_completed(futures):
            batch = futures[future]
            try:
                articles = future.result()
                if articles is not None and len(articles) >= len(batch):
                    all_articles.extend(articles)
                else:
                    failed_batches.append((batch, 0))
            except Exception:
                failed_batches.append((batch, 0))
    
    if failed_batches:
        all_articles.extend(_retry_pmids_until_complete(client, failed_batches))
    
    return all_articles


def _retry_batches_until_complete(
    client: Client,
    webenv: str,
    query_key: str,
    failed_batches: List[Tuple[int, int, int]],
    max_retries: int = 5,
) -> List[Dict[str, Any]]:
    """重试失败的批次，直到成功或达到最大重试次数"""
    if not failed_batches:
        return []
    
    print(f"    [fetch] 重试 {len(failed_batches)} 个失败批次...")
    all_articles = []
    
    for attempt in range(1, max_retries + 1):
        if not failed_batches:
            break
        
        still_failed: List[Tuple[int, int, int]] = []
        retry_success = 0
        
        for start, expected_size, retry_count in failed_batches:
            articles = client.efetch(webenv=webenv, query_key=query_key, retstart=start, retmax=expected_size)
            actual = len(articles) if articles else 0
            
            if actual >= expected_size:
                all_articles.extend(articles)
                retry_success += 1
            else:
                still_failed.append((start, expected_size, retry_count + 1))
        
        if still_failed:
            print(f"      第{attempt}次重试: 成功 {retry_success}, 仍失败 {len(still_failed)}")
            failed_batches = still_failed
            if attempt < max_retries:
                wait_time = 2 ** attempt
                time.sleep(wait_time)
        else:
            print(f"      第{attempt}次重试: 全部成功")
            failed_batches = []
            break
    
    if failed_batches:
        total_lost = sum(size for _, size, _ in failed_batches)
        print(f"    [fetch] ⚠️ 最终失败 {len(failed_batches)} 个批次，约 {total_lost} 篇文献丢失")
    
    return all_articles


def _retry_pmids_until_complete(
    client: Client,
    failed_batches: List[Tuple[List[str], int]],
    max_retries: int = 5,
) -> List[Dict[str, Any]]:
    """重试失败的 PMID 批次，直到成功或达到最大重试次数"""
    if not failed_batches:
        return []
    
    print(f"    [fetch] 重试 {len(failed_batches)} 个失败批次...")
    all_articles = []
    
    for attempt in range(1, max_retries + 1):
        if not failed_batches:
            break
        
        still_failed: List[Tuple[List[str], int]] = []
        retry_success = 0
        
        for batch, retry_count in failed_batches:
            articles = client.efetch(ids=batch)
            actual = len(articles) if articles else 0
            
            if actual >= len(batch):
                all_articles.extend(articles)
                retry_success += 1
            else:
                still_failed.append((batch, retry_count + 1))
        
        if still_failed:
            print(f"      第{attempt}次重试: 成功 {retry_success}, 仍失败 {len(still_failed)}")
            failed_batches = still_failed
            if attempt < max_retries:
                wait_time = 2 ** attempt
                time.sleep(wait_time)
        else:
            print(f"      第{attempt}次重试: 全部成功")
            failed_batches = []
            break
    
    if failed_batches:
        total_lost = sum(len(b) for b, _ in failed_batches)
        print(f"    [fetch] ⚠️ 最终失败 {len(failed_batches)} 个批次，{total_lost} 篇文献丢失")
    
    return all_articles


def bulk_export(
    term: str,
    output_dir: Optional[str] = None,
    credentials: Optional[Credentials] = None,
    threshold: int = 9500,
    max_workers: Optional[int] = None,
    batch_size: int = 1000,
) -> Dict[str, Any]:
    """批量导出文献元数据到 JSONL"""
    client = Client(credentials)
    
    if max_workers is None:
        max_workers = _get_max_workers(credentials)
    
    print(f"正在搜索: {term}")
    result = client.esearch(term, retmax=0)
    total = result['count']
    print(f"找到 {total} 篇文献")
    
    if total == 0:
        return {"success": True, "total": 0, "count": 0, "output_file": None}
    
    output = Output(user_path=output_dir)
    
    if total < threshold:
        return _export_small(client, result, total, output, batch_size, max_workers)
    
    return _export_large(client, term, total, output, credentials, threshold, batch_size, max_workers)


def _export_small(
    client: Client,
    result: Dict[str, Any],
    total: int,
    output: Output,
    batch_size: int,
    max_workers: int,
) -> Dict[str, Any]:
    """小批量导出"""
    print(f"文献数少于阈值，直接导出...")
    
    path = output.default_path(".jsonl")
    articles = fetch(
        webenv=result["webenv"],
        query_key=result["query_key"],
        _client=client,
        retmax=total,
        batch_size=batch_size,
        max_workers=max_workers
    )
    
    with open(path, 'w', encoding='utf-8') as f:
        for article in articles:
            f.write(json.dumps(article, ensure_ascii=False) + '\n')
    
    final = output.finalize()
    
    return {
        "success": True,
        "total": total,
        "count": len(articles),
        "output_file": final["final"],
    }


def _export_large(
    client: Client,
    term: str,
    total: int,
    output: Output,
    credentials: Optional[Credentials],
    threshold: int,
    batch_size: int,
    max_workers: int,
) -> Dict[str, Any]:
    """大批量导出（并行分段）"""
    print(f"文献数超过阈值，启用分段导出...")
    
    chunks = chunk_dates(client, term, threshold)
    print(f"分为 {len(chunks)} 个时间段")
    
    temp_dir = tempfile.mkdtemp(prefix="bcbi_chunks_")
    segment_workers = min(_get_segment_workers(credentials), len(chunks))
    
    print(f"\n使用 {segment_workers} 个并发段，每段 {max_workers} 个并发请求...")
    
    chunk_results = _process_chunks_parallel(
        chunks, term, credentials, temp_dir, batch_size, max_workers, segment_workers
    )
    
    chunk_files = [r['path'] for r in chunk_results if r['path']]
    total_exported = sum(r['count'] for r in chunk_results)
    
    print(f"\n所有时间段处理完成，共导出 {total_exported} 篇")
    
    for r in chunk_results:
        if r['log']:
            print(r['log'])
    
    final_path = output.default_path(".jsonl")
    unique_count, dup_count = dedupe_jsonl(chunk_files, final_path)
    
    shutil.rmtree(temp_dir)
    final = output.finalize()
    
    print(f"\n完成！去重 {dup_count} 篇，保留 {unique_count} 篇")
    print(f"输出: {final['final']}")
    
    return {
        "success": True,
        "total": total,
        "count": unique_count,
        "output_file": final["final"],
    }


def _process_chunks_parallel(
    chunks: List[Dict[str, str]],
    term: str,
    credentials: Optional[Credentials],
    temp_dir: str,
    batch_size: int,
    max_workers: int,
    segment_workers: int,
) -> List[Dict[str, Any]]:
    """并行处理所有时间段"""
    results = []
    
    def process_chunk(args: Tuple[int, Dict[str, str]]) -> Dict[str, Any]:
        return _process_single_chunk(
            args[0], args[1], len(chunks), term, credentials, temp_dir, batch_size, max_workers
        )
    
    with ThreadPoolExecutor(max_workers=segment_workers) as executor:
        futures = {executor.submit(process_chunk, (i, chunk)): (i, chunk) for i, chunk in enumerate(chunks)}
        
        for future in as_completed(futures):
            i, chunk = futures[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                print(f"警告：时间段 {chunk['start']} ~ {chunk['end']} 处理失败，重试中...")
                try:
                    result = _process_single_chunk(
                        i, chunk, len(chunks), term, credentials, temp_dir, batch_size, max_workers
                    )
                    results.append(result)
                except Exception as e2:
                    print(f"错误：时间段重试失败: {e2}")
                    results.append({'index': i, 'path': None, 'count': 0, 'log': f"  [{i+1}/{len(chunks)}] {chunk['start']} ~ {chunk['end']}: 失败"})
    
    return sorted(results, key=lambda x: x['index'])


def _process_single_chunk(
    i: int,
    chunk: Dict[str, str],
    total_chunks: int,
    term: str,
    credentials: Optional[Credentials],
    temp_dir: str,
    batch_size: int,
    max_workers: int,
) -> Dict[str, Any]:
    """处理单个时间段，返回结果而非直接打印"""
    chunk_idx = i + 1
    chunk_client = Client(credentials)
    
    result = chunk_client.esearch(term, retmax=0, usehistory=True, 
                                  mindate=chunk['start'], maxdate=chunk['end'])
    chunk_count = result['count']
    
    if chunk_count == 0:
        return {'index': i, 'path': None, 'count': 0, 'log': ''}
    
    articles = fetch(
        webenv=result["webenv"],
        query_key=result["query_key"],
        _client=chunk_client,
        retmax=chunk_count,
        batch_size=batch_size,
        max_workers=max_workers
    )
    
    path = Path(temp_dir) / f"chunk_{chunk_idx:04d}.jsonl"
    with open(path, 'w', encoding='utf-8') as f:
        for article in articles:
            f.write(json.dumps(article, ensure_ascii=False) + '\n')
    
    count = len(articles)
    log = f"  [{chunk_idx}/{total_chunks}] {chunk['start']} ~ {chunk['end']}: {count} 篇"
    
    return {'index': i, 'path': str(path), 'count': count, 'log': log}
