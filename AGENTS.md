# AGENTS.md

## 项目概述

BCBI - 生物计算与生物信息学工具包，包含 PubMed 文献搜索等功能。

## 环境

- Python: `.venv/bin/python` 
- 依赖: `requests`
- PYTHONPATH: `src/`

## 命令

```bash
# Python API 使用示例
PYTHONPATH=src .venv/bin/python -c "from bcbi import pubmed; print(pubmed.search('CRISPR'))"

# 测试
PYTHONPATH=src .venv/bin/python tests/test_search.py
```

## 项目结构

```
src/bcbi/                  # 主包
├── __init__.py           # 包入口 (from bcbi import pubmed)
└── pubmed/               # PubMed 子包 (4 个核心文件)
    ├── __init__.py       # 导出: Credentials, search, fetch, bulk_export, Client
    ├── api.py            # 用户 API 实现 (~230 行)
    ├── client.py         # Client + Credentials (~220 行)
    ├── _decode.py        # XML 解码（私有，~140 行）
    ├── _util.py          # 工具函数（私有，~230 行）
    └── py.typed          # 类型提示标记

tests/
└── test_search.py        # 测试用例

pyproject.toml            # 打包配置
README.md                 # 项目说明
```

## 模块说明

### __init__.py (16 行)
简洁的 API 导出，用户通过 `from bcbi import pubmed` 访问所有功能。

### api.py (~230 行)
用户接口实现，包含：
- `search()` - 搜索文献
- `fetch()` - 获取文献（支持 max_workers 并发）
- `bulk_export()` - 批量导出到 JSONL

### client.py (~220 行)
底层 API 客户端，包含：
- `Credentials` - 凭据数据类（支持 hash，可作 dict key）
- `Client` - API 客户端
  - `esearch()` - esearch API，返回 dict
  - `efetch()` - efetch API，返回文章列表（支持 decode 参数）
  - 类级别 Session 池，复用连接
  - 内置重试和限速逻辑

### _decode.py (~140 行，私有)
XML 解码工具：
- `decode_articles()` - 将 XML 解码为文章列表

### _util.py (~230 行，私有)
内部工具函数：
- `chunk_dates()` - 按日期分块
- `dedupe_jsonl()` - 合并去重 JSONL
- `Output` - 输出管理类

## 核心 API

### pubmed.Credentials(api_key, email, tool)
API 凭据结构体

### pubmed.search(term, credentials, retmax, **kwargs)
搜索文献，返回 `{"count", "webenv", "query_key", "ids"}`

### pubmed.fetch(pmids, webenv, query_key, credentials, retmax, batch_size, max_workers)
获取文献元数据，支持并发（max_workers > 1）

### pubmed.bulk_export(term, output_dir, credentials, threshold, max_workers)
批量导出文献元数据到 JSONL

## 核心特性

1. **简单接口**: `from bcbi import pubmed` 即可使用
2. **返回结构化数据**: esearch/efetch 返回 dict/list，而非 XML
3. **Session 复用**: 类级别 Session 池，按 Credentials 缓存
4. **并发支持**: fetch() 支持 max_workers 参数
5. **流式处理**: 内存占用恒定，支持大数据量（10,000+ 条）
6. **自动分段**: 超过阈值自动按日期分段导出
7. **速率限制**: 遵守 PubMed API 限制，支持 API Key 加速

## 代码风格

- **语言**: 中文注释、中文输出信息
- **命名**: snake_case (类名 PascalCase)
- **类型**: 使用 type hints (Optional, List, Dict 等)
- **错误处理**: print 输出错误信息，直接返回空值
- **导入**: 标准库 → 第三方库 → 本地模块
- **文件结构**: 模块放在 src/bcbi/pubmed/ 目录
- **私有模块**: 以 _ 开头（_decode.py, _util.py）

## 开发约定

1. Client 负责底层网络请求，api.py 负责用户 API
2. 配置通过 Credentials 结构体传入（无 config 模块）
3. Client.esearch/efetch 返回结构化数据，不返回 XML
4. Session 池类级别缓存，相同 Credentials 复用连接
5. 并发通过 api 层 max_workers 参数控制
6. 私有模块（_decode.py, _util.py）以 _ 开头
7. 用户只通过 `from bcbi import pubmed` 访问 API

## 设计原则

### 模块划分
- **公开模块**: `__init__.py`, `api.py`, `client.py` - 用户可访问
- **私有模块**: `_decode.py`, `_util.py` - 内部实现细节

### 命名规范
- Client 方法: esearch/efetch（对应 PubMed API）
- 公开 API: search/fetch/bulk_export（用户友好）
- 私有函数: 以 _ 开头
- 类名: PascalCase（Client, Credentials）
- 函数名: snake_case

### 职责分离
- `client.py`: 底层 API，返回结构化数据
- `api.py`: 用户接口，参数处理，调用 Client
- `_decode.py`: 纯数据转换，XML → Dict
- `_util.py`: 业务逻辑，分块、去重、输出

### 性能优化
- Session 复用：相同 Credentials 共享 Session
- 并发获取：ThreadPoolExecutor 多线程
- 自动分批：batch_size=350 避免 URL 过长
- 限速遵守：min_interval 控制请求间隔

## 注意事项

- 使用 PubMed E-utilities API，遵守 rate limit (3 req/s 无 API key，10 req/s 有 API key)
- 并发数 max_workers 建议不超过 10
- 搜索结果默认保存为 JSONL 格式（下游友好）
- 私有模块可能会变更，用户不应直接使用

## 打包发布

```bash
# 构建
python -m build

# 上传到 PyPI
twine upload dist/*
```

## 测试

```bash
# 运行测试
PYTHONPATH=src python tests/test_search.py
```
