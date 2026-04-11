#!/usr/bin/env python3
"""
BCBI 完整测试脚本

测试集:
- SCLC (~12,500 篇)
- EGFR NSCLC (~14,600 篇)
- CRISPR (~66,000 篇)
- COPD (~124,000 篇)

测试项:
- 有 API Key vs 无 API Key
- 数据完整性验证
- 性能统计
- 自动生成测试报告
"""

import sys
import time
import json
from datetime import datetime
from pathlib import Path

from bcbi import pubmed
from bcbi.pubmed.client import Client, Credentials

# 加载凭据
try:
    from credentials import CREDENTIALS
    print(f"凭据加载成功: {CREDENTIALS['email']}")
except ImportError:
    print("错误: 请创建 tests/credentials.py 文件")
    print("内容示例:")
    print('CREDENTIALS = {"api_key": "your_key", "email": "your@email.com", "tool": "your_tool"}')
    sys.exit(1)

CREDS = Credentials(**CREDENTIALS)

# 测试集配置
TEST_CASES = [
    {"name": "SCLC", "term": "SCLC", "description": "小细胞肺癌"},
    {"name": "EGFR NSCLC", "term": "EGFR mutation NSCLC", "description": "EGFR非小细胞肺癌"},
    {"name": "CRISPR", "term": "CRISPR", "description": "CRISPR基因编辑技术"},
    {"name": "COPD", "term": "COPD", "description": "慢性阻塞性肺病"},
]


def run_single_test(test_case: dict, with_key: bool) -> dict:
    """运行单个测试用例"""
    name = test_case["name"]
    term = test_case["term"]
    creds = CREDS if with_key else None
    key_status = "有Key" if with_key else "无Key"
    
    print(f"\n{'='*60}")
    print(f"测试: {name} ({key_status})")
    print(f"搜索词: {term}")
    print(f"{'='*60}")
    
    Client.reset_stats(creds)
    start_time = time.time()
    
    try:
        result = pubmed.bulk_export(
            term=term,
            output_dir="test_output",
            credentials=creds,
        )
        
        elapsed = time.time() - start_time
        stats = Client.get_stats(creds)
        
        total = result.get("total", 0)
        count = result.get("count", 0)
        completeness = (count / total * 100) if total > 0 else 0
        
        test_result = {
            "name": name,
            "term": term,
            "with_key": with_key,
            "success": result.get("success", False),
            "total": total,
            "exported": count,
            "completeness": round(completeness, 2),
            "output_file": result.get("output_file", ""),
            "elapsed_seconds": round(elapsed, 2),
            "articles_per_second": round(count / elapsed, 2) if elapsed > 0 else 0,
            "stats": {
                "total_requests": stats["total_requests"],
                "success_requests": stats["success_requests"],
                "failed_requests": stats["failed_requests"],
                "retries": stats["retries"],
                "requests_per_second": round(stats["requests_per_second"], 2),
                "error_rate": round(stats["error_rate"], 2),
            },
        }
        
        print(f"\n结果:")
        print(f"  总文献: {total}")
        print(f"  导出: {count}")
        print(f"  完整性: {completeness:.2f}%")
        print(f"  耗时: {elapsed:.2f}s ({elapsed/60:.1f}分钟)")
        print(f"  速率: {count/elapsed:.2f} 篇/s")
        print(f"  请求: {stats['total_requests']}, 重试: {stats['retries']}, 错误率: {stats['error_rate']:.2f}%")
        
        if result.get("output_file"):
            test_result["file_validation"] = validate_output_file(result["output_file"])
        
    except Exception as e:
        elapsed = time.time() - start_time
        test_result = {
            "name": name,
            "term": term,
            "with_key": with_key,
            "success": False,
            "error": str(e),
            "elapsed_seconds": round(elapsed, 2),
        }
        print(f"\n❌ 测试失败: {e}")
    
    return test_result


def validate_output_file(filepath: str) -> dict:
    """验证输出文件"""
    try:
        path = Path(filepath)
        if not path.exists():
            return {"valid": False, "error": "文件不存在"}
        
        file_size = path.stat().st_size
        line_count = 0
        pmids = set()
        
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                line_count += 1
                try:
                    article = json.loads(line)
                    pmid = article.get("PMID")
                    if pmid:
                        pmids.add(pmid)
                except json.JSONDecodeError:
                    pass
        
        return {
            "valid": True,
            "file_size_mb": round(file_size / 1024 / 1024, 2),
            "line_count": line_count,
            "unique_pmids": len(pmids),
            "duplicate_count": line_count - len(pmids),
        }
    except Exception as e:
        return {"valid": False, "error": str(e)}


def generate_report(results: list, output_dir: str = "test_reports") -> str:
    """生成测试报告"""
    report_dir = Path(output_dir)
    report_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = report_dir / f"test_report_{timestamp}.md"
    json_file = report_dir / f"test_report_{timestamp}.json"
    
    lines = [
        "# BCBI 测试报告",
        "",
        f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 测试概览",
        "",
        "| 测试集 | Key状态 | 总文献 | 导出 | 完整性 | 耗时 | 速率 |",
        "|--------|---------|--------|------|--------|------|------|",
    ]
    
    for r in results:
        if r.get("success"):
            key_status = "有Key" if r["with_key"] else "无Key"
            lines.append(
                f"| {r['name']} | {key_status} | {r['total']} | {r['exported']} | "
                f"{r['completeness']}% | {r['elapsed_seconds']}s | {r['articles_per_second']} 篇/s |"
            )
        else:
            key_status = "有Key" if r["with_key"] else "无Key"
            lines.append(f"| {r['name']} | {key_status} | - | - | 失败 | - | - |")
    
    lines.extend(["", "## 详细结果", ""])
    
    for r in results:
        key_status = "有Key" if r["with_key"] else "无Key"
        lines.extend([
            f"### {r['name']} ({key_status})",
            "",
            f"- **搜索词**: `{r['term']}`",
            f"- **状态**: {'✅ 成功' if r.get('success') else '❌ 失败'}",
        ])
        
        if r.get("success"):
            lines.extend([
                "",
                "#### 数据统计",
                "",
                f"- 总文献数: {r['total']}",
                f"- 导出数量: {r['exported']}",
                f"- 数据完整性: {r['completeness']}%",
                f"- 输出文件: `{r.get('output_file', 'N/A')}`",
                "",
                "#### 性能统计",
                "",
                f"- 总耗时: {r['elapsed_seconds']} 秒 ({r['elapsed_seconds']/60:.1f}分钟)",
                f"- 处理速率: {r['articles_per_second']} 篇/秒",
                "",
                "#### 请求统计",
                "",
                f"- 总请求数: {r['stats']['total_requests']}",
                f"- 成功请求: {r['stats']['success_requests']}",
                f"- 失败请求: {r['stats']['failed_requests']}",
                f"- 重试次数: {r['stats']['retries']}",
                f"- 请求速率: {r['stats']['requests_per_second']} req/s",
                f"- 错误率: {r['stats']['error_rate']}%",
            ])
            
            if "file_validation" in r and r["file_validation"].get("valid"):
                fv = r["file_validation"]
                lines.extend([
                    "",
                    "#### 文件验证",
                    "",
                    f"- 文件大小: {fv['file_size_mb']} MB",
                    f"- 行数: {fv['line_count']}",
                    f"- 唯一PMID: {fv['unique_pmids']}",
                    f"- 重复数: {fv['duplicate_count']}",
                ])
            
            lines.append("")
        else:
            lines.extend([
                f"- **错误**: {r.get('error', '未知错误')}",
                f"- **耗时**: {r['elapsed_seconds']} 秒",
                "",
            ])
    
    successful = [r for r in results if r.get("success")]
    if successful:
        avg_completeness = sum(r['completeness'] for r in successful) / len(successful)
        avg_rate = sum(r['articles_per_second'] for r in successful) / len(successful)
        total_exported = sum(r['exported'] for r in successful)
        
        lines.extend([
            "## 汇总统计",
            "",
            f"- 测试成功: {len(successful)}/{len(results)}",
            f"- 总导出文献: {total_exported}",
            f"- 平均完整性: {avg_completeness:.2f}%",
            f"- 平均速率: {avg_rate:.2f} 篇/秒",
            "",
        ])
    
    lines.extend(["---", "", "*报告由 BCBI 自动生成*"])
    
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))
    
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\n测试报告已保存:")
    print(f"  Markdown: {report_file}")
    print(f"  JSON: {json_file}")
    
    return str(report_file)


def main():
    """运行所有测试"""
    print("=" * 60)
    print("BCBI 完整测试")
    print("=" * 60)
    
    results = []
    
    for test_case in TEST_CASES:
        print(f"\n\n{'#'*60}")
        print(f"# 测试集: {test_case['name']}")
        print(f"# {test_case['description']}")
        print(f"{'#'*60}")
        
        # 有 Key 测试
        result_with_key = run_single_test(test_case, with_key=True)
        results.append(result_with_key)
        
        # 无 Key 测试
        result_without_key = run_single_test(test_case, with_key=False)
        results.append(result_without_key)
    
    print(f"\n\n{'='*60}")
    print("生成测试报告...")
    print(f"{'='*60}")
    
    report_path = generate_report(results)
    
    print(f"\n\n{'='*60}")
    print("测试完成摘要")
    print(f"{'='*60}")
    
    for r in results:
        key_status = "有Key" if r["with_key"] else "无Key"
        if r.get("success"):
            print(f"✅ {r['name']} ({key_status}): {r['completeness']}% - {r['elapsed_seconds']}s")
        else:
            print(f"❌ {r['name']} ({key_status}): 失败")
    
    print(f"\n报告文件: {report_path}")


if __name__ == "__main__":
    main()
