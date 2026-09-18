"""Excel 导出器 — 三 sheet 汇总表 + 账号统计 + 关键词统计"""
from pathlib import Path
from typing import Optional

from src.models.records import AuditResult, HitRecord


class ExcelExporter:
    """将审计结果导出为带格式的 Excel"""

    @staticmethod
    def _auto_width(ws, min_width=8, max_width=55):
        """根据内容自适应列宽（中文字符按 2 个英文字符宽度计算）"""
        from openpyxl.utils import get_column_letter
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                if cell.value is None:
                    continue
                text = str(cell.value)
                # 只取第一行（表头）和有数据的行，忽略空行
                if not text.strip():
                    continue
                # 计算显示宽度：中文=2，英文=1
                width = 0
                for ch in text:
                    if ord(ch) > 127:
                        width += 2
                    else:
                        width += 1
                # 多行取最长那行
                for line in text.split("\n"):
                    lw = sum(2 if ord(c) > 127 else 1 for c in line)
                    width = max(width, lw)
                max_len = max(max_len, width)
            if max_len > 0:
                ws.column_dimensions[col_letter].width = max(min_width, min(max_len + 2, max_width))

    def export(self, result: AuditResult, out_path: str) -> str:
        from openpyxl import Workbook
        from openpyxl.styles import Font, Alignment, PatternFill
        from openpyxl.utils import get_column_letter

        wb = Workbook()

        # ========== Sheet1: 命中汇总 ==========
        ws1 = wb.active
        ws1.title = "命中汇总"

        headers = [
            "姓名", "账号", "文件夹", "UID", "日期",
            "发件人", "收件人", "抄送", "主题",
            "命中关键词", "命中同义词", "命中字段", "命中内容", "EML路径",
        ]
        ws1.append(headers)

        # 表头样式
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        for col_idx in range(1, len(headers) + 1):
            cell = ws1.cell(row=1, column=col_idx)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")

        for r in result.records:
            ws1.append([
                r.account_name,
                r.account,
                r.folder,
                r.uid,
                r.date,
                r.from_,
                r.to,
                r.cc,
                r.subject,
                "\n".join(r.hit_keywords),
                "\n".join(r.hit_synonym),
                "\n".join(r.hit_fields),
                r.hit_content,
                r.eml_path,
            ])

        # 冻结首行 + 自适应列宽
        ws1.freeze_panes = "A2"
        self._auto_width(ws1, min_width=8, max_width=55)

        # 命中关键词列自动换行
        for row in ws1.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(vertical="top", wrap_text=True)

        # ========== Sheet2: 按账号统计 ==========
        ws2 = wb.create_sheet("按账号统计")
        stat_headers = ["姓名", "账号", "命中邮件数", "命中关键词", "命中的文件夹"]
        ws2.append(stat_headers)
        for col_idx in range(1, len(stat_headers) + 1):
            cell = ws2.cell(row=1, column=col_idx)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")

        for stat in result.account_stats.values():
            ws2.append([
                stat.name,
                stat.email,
                stat.hit_count,
                "\n".join(stat.hit_keywords),
                "\n".join(stat.scanned_folders),
            ])
        ws2.freeze_panes = "A2"
        self._auto_width(ws2, min_width=10, max_width=50)
        for row in ws2.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(vertical="top", wrap_text=True)

        # 失败账号区块
        if result.failures:
            ws2.append([])
            ws2.append(["失败账号", "失败原因"])
            for cell in ws2[ws2.max_row]:
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill(start_color="C00000", end_color="C00000", fill_type="solid")
            for em, err in result.failures.items():
                ws2.append([em, err])

        # ========== Sheet3: 按关键词统计 ==========
        # 每个账号 × 每个关键词一行，命中邮件数对应该关键词的命中数
        ws3 = wb.create_sheet("按关键词统计")
        kw_headers = ["姓名", "账号", "命中邮件数", "命中关键词", "命中的文件夹"]
        ws3.append(kw_headers)
        for col_idx in range(1, len(kw_headers) + 1):
            cell = ws3.cell(row=1, column=col_idx)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")

        # 按 (账号, 关键词) 聚合：保留首次出现顺序
        kw_stats = {}          # account -> {keyword -> {"count","folders","name"}}
        account_order = []     # 账号首次出现顺序
        for r in result.records:
            if r.account not in kw_stats:
                kw_stats[r.account] = {}
                account_order.append(r.account)
            acc_map = kw_stats[r.account]
            for kw in r.hit_keywords:
                if kw not in acc_map:
                    acc_map[kw] = {"count": 0, "folders": [], "name": r.account_name}
                acc_map[kw]["count"] += 1
                if r.folder not in acc_map[kw]["folders"]:
                    acc_map[kw]["folders"].append(r.folder)
                if not acc_map[kw]["name"] and r.account_name:
                    acc_map[kw]["name"] = r.account_name

        for acc in account_order:
            for kw, st in kw_stats[acc].items():
                ws3.append([
                    st["name"],
                    acc,
                    st["count"],
                    kw,
                    "\n".join(st["folders"]),
                ])
        ws3.freeze_panes = "A2"
        self._auto_width(ws3, min_width=10, max_width=50)
        for row in ws3.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(vertical="top", wrap_text=True)

        # ========== 保存 ==========
        out_path = str(out_path)
        wb.save(out_path)
        return out_path
