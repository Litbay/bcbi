# BCBI

[![PyPI version](https://img.shields.io/pypi/v/bcbi.svg)](https://pypi.org/project/bcbi/)
[![Python](https://img.shields.io/pypi/pyversions/bcbi.svg)](https://pypi.org/project/bcbi/)
[![License](https://img.shields.io/github/license/litbay/bcbi.svg)](https://github.com/litbay/bcbi/blob/main/LICENSE)

**BCBI** - 生物计算与生物信息学工具包

[GitHub](https://github.com/litbay/bcbi) | [PyPI](https://pypi.org/project/bcbi/) | [文档](docs/)

## 特性

- **100% 数据完整性** - 验证返回数量，失败自动重试最多 5 次
- **高并发** - 多线程获取，自动根据凭据调整并发数
- **自动分段** - 超过阈值自动按日期分段导出
- **简单易用** - `from bcbi import pubmed` 即可使用
- **流式处理** - 内存占用恒定，支持 100,000+ 条数据

## 安装

```bash
pip install bcbi
```

## 快速开始

```python
from bcbi import pubmed

# 搜索文献
result = pubmed.search("CRISPR")
print(f"找到 {result['count']} 篇文献")

# 批量导出（自动分段、自动并发）
result = pubmed.bulk_export("COPD", output_dir="./output")
print(f"导出 {result['count']} 篇文献")
```

## 性能

在大规模数据集上的测试结果：

| 测试集 | 文献数 | 完整性 | 耗时 | 速率 |
|--------|--------|--------|------|------|
| COPD | 123,930 | 100% | 370s | 335 篇/s |
| CRISPR | 66,179 | 100% | 229s | 289 篇/s |
| EGFR NSCLC | 14,616 | 100% | 58s | 252 篇/s |
| SCLC | 12,571 | 100% | 52s | 242 篇/s |

详细测试报告: [docs/pubmed_bulk_export_test.md](docs/pubmed_bulk_export_test.md)

## 用法

### 搜索文献

```python
from bcbi import pubmed

# 基本搜索
result = pubmed.search("CRISPR")
print(f"总数: {result['count']}")

# 获取 PMID 列表
result = pubmed.search("CRISPR", retmax=100)
print(f"PMID: {result['ids'][:5]}")

# 使用凭据（提高速率限制）
creds = pubmed.Credentials(
    api_key="your_api_key",
    email="your@email.com",
    tool="my_tool"
)
result = pubmed.search("CRISPR", credentials=creds)
```

### 获取文献元数据

```python
# 通过 WebEnv 获取
result = pubmed.search("CRISPR", retmax=100)
articles = pubmed.fetch(
    webenv=result["webenv"],
    query_key=result["query_key"],
    retmax=100
)

# 通过 PMID 列表获取
result = pubmed.search("CRISPR", retmax=100)
articles = pubmed.fetch(pmids=result["ids"])

for article in articles[:3]:
    print(f"{article['PMID']}: {article['Title'][:50]}...")
```

### 批量导出

```python
# 导出大量文献（自动分段、自动并发）
result = pubmed.bulk_export(
    "COPD",
    output_dir="./output",
    credentials=creds
)

print(f"导出: {result['count']} 篇")
print(f"文件: {result['output_file']}")
```

## API 参考

### pubmed.Credentials

```python
creds = pubmed.Credentials(
    api_key="",    # NCBI API Key（提高速率限制到 10 req/s）
    email="",      # 用户邮箱
    tool=""        # 工具名称
)
```

### pubmed.search(term, credentials, retmax, **kwargs)

搜索文献。

**返回:** `{"count": int, "webenv": str, "query_key": str, "ids": List[str]}`

### pubmed.fetch(pmids, webenv, query_key, credentials, retmax, ...)

获取文献元数据。

**特性:**
- 验证返回数量与请求一致
- 失败自动重试最多 5 次

**返回:** 文章元数据列表

### pubmed.bulk_export(term, output_dir, credentials, threshold, ...)

批量导出到 JSONL 文件。

**自动配置:**
- 有 API Key: 10 并发 × 5 段
- 无 API Key: 5 并发 × 3 段

**返回:** `{"success": bool, "total": int, "count": int, "output_file": str}`

## 文献元数据格式

```json
{
  "PMID": "12345678",
  "Title": "文章标题",
  "Authors": "作者1, 作者2",
  "Journal": "期刊名",
  "PublicationDate": "2024",
  "Abstract": "摘要内容",
  "DOI": "10.1234/example",
  "PMCID": "PMC1234567"
}
```

## API Key

获取 NCBI API Key 可提高速率限制：
- 无 API Key: 3 次/秒
- 有 API Key: 10 次/秒

申请地址: https://www.ncbi.nlm.nih.gov/account/settings/apikeys/

## 开发

```bash
git clone https://github.com/litbay/bcbi.git
cd bcbi
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 运行测试
PYTHONPATH=src python tests/test_search.py
```

## 项目结构

```
src/bcbi/
├── __init__.py
└── pubmed/
    ├── __init__.py    # 导出 API
    ├── api.py         # 用户接口
    ├── client.py      # Client + Credentials
    ├── _decode.py     # XML 解码
    └── _util.py       # 工具函数
```

## 许可证

[MIT License](LICENSE)
