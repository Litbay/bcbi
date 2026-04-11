"""
内部工具函数模块（私有）

提供批量导出所需的辅助功能:
- 日期分块: 将大量文献按时间段分割
- 文件去重: 合并多个 JSONL 文件并去除重复
- 输出管理: 处理临时文件和最终输出路径
"""

import json
import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Set


def chunk_dates(client, query: str, threshold: int) -> List[Dict[str, str]]:
    """按日期分块以处理大量文献"""
    total = _count(client, query)
    if total == 0 or total < threshold:
        return []
    
    earliest = _find_earliest_year(client, query)
    return _split_recursive(client, query, f"{earliest}/01/01", "2099/12/31", threshold)


def dedupe_jsonl(input_files: List[str], output_file: Path) -> Tuple[int, int]:
    """合并多个 JSONL 文件并去重"""
    seen: Set[str] = set()
    unique = 0
    dup = 0
    
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as out:
        for file in input_files:
            with open(file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        article = json.loads(line)
                        pmid = str(article.get("PMID", ""))
                        
                        if pmid and pmid not in seen:
                            seen.add(pmid)
                            out.write(json.dumps(article, ensure_ascii=False) + '\n')
                            unique += 1
                        else:
                            dup += 1
                    except json.JSONDecodeError:
                        continue
    
    return unique, dup


class Output:
    """输出文件管理器"""
    
    def __init__(self, user_path: Optional[str] = None):
        self.user_path = user_path
        self._temp_dir: Optional[Path] = None
    
    @property
    def temp_dir(self) -> Path:
        if self._temp_dir is None:
            self._temp_dir = Path(tempfile.mkdtemp(prefix="bcbi_"))
        return self._temp_dir
    
    def default_path(self, ext: str = ".jsonl") -> Path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return self.temp_dir / f"{ts}_pubmed{ext}"
    
    def finalize(self) -> Dict[str, str]:
        if not self.temp_dir.exists():
            return {"temp": "", "final": ""}
        
        files = {f.name: str(f) for f in self.temp_dir.iterdir() if f.is_file()}
        result = {"temp": str(self.temp_dir), "files": files, "final": ""}
        
        if self.user_path and files:
            copied = {}
            for name, temp_path in files.items():
                dest = self._copy_to_user(Path(temp_path))
                if dest:
                    copied[name] = str(dest)
            
            if copied:
                result["final"] = list(copied.values())[0] if len(copied) == 1 else str(copied)
                result["files"] = copied
        else:
            result["final"] = str(self.temp_dir)
        
        return result
    
    def cleanup(self):
        if self._temp_dir and self._temp_dir.exists() and self.user_path:
            try:
                shutil.rmtree(self._temp_dir)
            except Exception:
                pass
    
    def _copy_to_user(self, src: Path) -> Optional[Path]:
        if not self.user_path:
            return None
        
        try:
            dest = Path(self.user_path)
            if dest.suffix == '' and (not dest.exists() or dest.is_dir()):
                dest.mkdir(parents=True, exist_ok=True)
                dest = dest / src.name
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
            
            shutil.copy2(src, dest)
            return dest
        except Exception:
            return None


def _count(client, query: str, mindate: Optional[str] = None, maxdate: Optional[str] = None) -> int:
    """获取指定时间范围内的文献数量"""
    result = client.esearch(query, retmax=0, mindate=mindate, maxdate=maxdate)
    return result['count']


def _find_earliest_year(client, query: str, min_year: int = 1800, max_year: int = 2030) -> int:
    """二分查找最早有文献的年份"""
    total = _count(client, query)
    if total == 0:
        return min_year
    
    low, high = min_year, max_year
    earliest = max_year
    
    while low < high:
        mid = (low + high) // 2
        count = _count(client, query, f"{min_year}/01/01", f"{mid}/12/31")
        
        if count > 0 and count < total:
            earliest = mid
            high = mid
        elif count == total:
            earliest = mid
            high = mid
        else:
            low = mid + 1
    
    return max(min_year, low - 1)


def _split_recursive(client, query: str, start: str, end: str, threshold: int) -> List[Dict[str, str]]:
    """递归分割日期范围"""
    count = _count(client, query, start, end)
    
    if count == 0:
        return []
    
    if count < threshold:
        return [{"start": start, "end": end}]
    
    if start == end:
        print(f"警告：单日 {start} 有 {count} 篇文献，超过阈值")
        return [{"start": start, "end": end}]
    
    start_dt = datetime.strptime(start, "%Y/%m/%d")
    end_dt = datetime.strptime(end, "%Y/%m/%d")
    mid_dt = start_dt + (end_dt - start_dt) / 2
    mid = mid_dt.strftime("%Y/%m/%d")
    
    left = _split_recursive(client, query, start, mid, threshold)
    right_start = (mid_dt + timedelta(days=1)).strftime("%Y/%m/%d")
    right = _split_recursive(client, query, right_start, end, threshold)
    
    return left + right
