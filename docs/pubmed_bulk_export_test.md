# BCBI 性能测试指南

本文档提供 BCBI PubMed API 的完整测试用例和性能基准。

## 测试环境

- Python 3.x
- 依赖: `requests`
- 测试凭据: 在 `tests/pubmed/credentials.py` 中配置

## 凭据配置

在 `tests/pubmed/credentials.py` 中配置测试凭据：

```python
CREDENTIALS = {
    "api_key": "your_api_key",
    "email": "your@email.com",
    "tool": "your_tool",
}
```

> 注意：凭据文件已在 `.gitignore` 中排除，不会被提交到版本控制。

## 测试集

| 测试集 | 搜索词 | 预期文献数 | 说明 |
|--------|--------|------------|------|
| SCLC | `SCLC` | ~12,500 | 小细胞肺癌 |
| EGFR NSCLC | `EGFR mutation NSCLC` | ~14,600 | EGFR突变非小细胞肺癌 |
| CRISPR | `CRISPR` | ~66,000 | CRISPR基因编辑 |
| COPD | `COPD` | ~124,000 | 慢性阻塞性肺病 |

## 测试代码

### 基础测试

```python
#!/usr/bin/env python3
"""BCBI 基础功能测试"""

from bcbi import pubmed

def test_search():
    """测试搜索功能"""
    result = pubmed.search("CRISPR", retmax=10)
    assert result['count'] > 0
    assert len(result['ids']) == 10
    print(f"✓ 搜索到 {result['count']} 篇文献")

def test_fetch_by_pmids():
    """测试通过 PMID 获取文献"""
    result = pubmed.search("CRISPR", retmax=5)
    articles = pubmed.fetch(pmids=result['ids'])
    assert len(articles) == 5
    print(f"✓ 获取到 {len(articles)} 篇文献")

def test_fetch_by_webenv():
    """测试通过 WebEnv 获取文献"""
    result = pubmed.search("CRISPR", retmax=5)
    articles = pubmed.fetch(
        webenv=result['webenv'],
        query_key=result['query_key'],
        retmax=5
    )
    assert len(articles) == 5
    print(f"✓ 获取到 {len(articles)} 篇文献")

if __name__ == "__main__":
    test_search()
    test_fetch_by_pmids()
    test_fetch_by_webenv()
    print("✓ 所有测试通过")
```

### 性能测试

```python
#!/usr/bin/env python3
"""BCBI 性能测试"""

import time
from bcbi import pubmed
from bcbi.pubmed.client import Client, Credentials

# 测试凭据
CREDENTIALS = Credentials(
    api_key="your_api_key",
    email="your@email.com",
    tool="your_tool"
)

def run_test(term: str, with_key: bool):
    """运行单个测试"""
    creds = CREDENTIALS if with_key else None
    key_status = "有Key" if with_key else "无Key"
    
    print(f"\n{'='*60}")
    print(f"测试: {term} ({key_status})")
    print(f"{'='*60}")
    
    Client.reset_stats(creds)
    start = time.time()
    
    result = pubmed.bulk_export(
        term=term,
        output_dir="test_output",
        credentials=creds,
    )
    
    elapsed = time.time() - start
    stats = Client.get_stats(creds)
    
    print(f"\n结果:")
    print(f"  总文献: {result['total']}")
    print(f"  导出: {result['count']}")
    print(f"  完整性: {result['count']/result['total']*100:.2f}%")
    print(f"  耗时: {elapsed:.2f}s ({elapsed/60:.1f}分钟)")
    print(f"  速率: {result['count']/elapsed:.2f} 篇/s")
    print(f"  请求数: {stats['total_requests']}")
    print(f"  重试次数: {stats['retries']}")
    print(f"  错误率: {stats['error_rate']:.2f}%")

if __name__ == "__main__":
    # 测试 COPD（大数据集）
    run_test("COPD", with_key=True)
    run_test("COPD", with_key=False)
```

## 性能基准

### COPD 测试（123,930 篇文献）

| Key状态 | 导出 | 完整性 | 耗时 | 速率 | 请求数 | 重试 | 错误率 |
|---------|------|--------|------|------|--------|------|--------|
| 有Key | 123,930 | 100% | 370s | 335 篇/s | 236 | 2 | 0.00% |
| 无Key | 123,930 | 100% | 371s | 334 篇/s | 293 | 13 | 0.00% |

### CRISPR 测试（66,179 篇文献）

| Key状态 | 导出 | 完整性 | 耗时 | 速率 | 请求数 | 重试 | 错误率 |
|---------|------|--------|------|------|--------|------|--------|
| 有Key | 66,179 | 100% | 229s | 289 篇/s | - | - | 0.00% |
| 无Key | 66,179 | 100% | 248s | 267 篇/s | - | 9 | 0.00% |

### SCLC 测试（12,571 篇文献）

| Key状态 | 导出 | 完整性 | 耗时 | 速率 | 请求数 | 重试 | 错误率 |
|---------|------|--------|------|------|--------|------|--------|
| 有Key | 12,571 | 100% | 54s | 235 篇/s | 33 | 0 | 0.00% |
| 无Key | 12,571 | 100% | 49s | 258 篇/s | 51 | 4 | 0.00% |

## 并发配置

系统自动根据凭据调整并发参数：

| 凭据状态 | 请求并发 (max_workers) | 段并发 (segment_workers) | 总并发 |
|----------|------------------------|--------------------------|--------|
| 有 Key | 10 | 5 | 50 |
| 无 Key | 5 | 3 | 15 |

## 重试机制

### 重试策略

1. **数量验证**: 每个批次验证返回数量与请求数量一致
2. **最大重试次数**: 5 次
3. **指数退避**: 2s → 4s → 8s → 16s → 32s
4. **最终报告**: 最终失败会报告丢失数量

### 重试日志示例

```
[fetch] 重试 1 个失败批次...
  第1次重试: 成功 0, 仍失败 1
  第2次重试: 全部成功
```

## 数据完整性保证

1. **请求级验证**: 每次请求验证返回数量
2. **批次级重试**: 失败批次自动重试
3. **段级重试**: 整段失败会重新处理
4. **去重机制**: 合并时按 PMID 去重

## 测试报告生成

测试完成后会自动生成报告：

```python
# Markdown 报告
test_reports/test_report_YYYYMMDD_HHMMSS.md

# JSON 数据
test_reports/test_report_YYYYMMDD_HHMMSS.json
```

## 运行完整测试

```bash
# 运行基础测试
PYTHONPATH=src python tests/test_search.py

# 运行性能测试（需先配置凭据）
PYTHONPATH=src:tests/pubmed python tests/pubmed/test_pubmed_bulk_export.py
```

## 注意事项

1. **超时设置**: 大数据集测试需要设置足够长的超时时间（10W 文献不少于 6 分钟）
2. **网络稳定性**: 测试前确保网络稳定
3. **API 限制**: 遵守 PubMed API 速率限制
4. **临时文件**: 测试期间会在 `test_output/` 生成临时文件
5. **凭据安全**: 凭据文件已在 `.gitignore` 中排除
