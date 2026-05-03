#!/usr/bin/env python3
"""
買取明細（支払通知書）PDF生成スクリプト
"""

import json
import os
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Spacer, Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus.flowables import HRFlowable

# ─────────────────────────────────────────────
# 発行者情報（固定）
# ─────────────────────────────────────────────
ISSUER = {
    "name":    "株式会社AiGIVE",
    "zip":     "940-0062",
    "address": "新潟県長岡市大手通2−2−6",
    "tel":     "",          # 必要なら追加
    "invoice_no": "T5110001038461",
}

# 番号管理ファイル
COUNTER_FILE = os.path.join(os.path.dirname(__file__), ".receipt_counter.json")

def load_counter():
    if os.path.exists(COUNTER_FILE):
        with open(COUNTER_FILE, "r") as f:
            return json.load(f).get("counter", 28)
    return 28   # 次が PN-0000000029

def save_counter(n):
    with open(COUNTER_FILE, "w") as f:
        json.dump({"counter": n}, f)

def next_receipt_number():
    n = load_counter() + 1
    save_counter(n)
    return f"PN-{n:010d}"

# ─────────────────────────────────────────────
# フォント設定（Arial Unicode：日本語・英字統一）
# ─────────────────────────────────────────────
_FONT_CANDIDATES = [
    "/Library/Fonts/Arial Unicode.ttf",
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
    "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf",
]
_FONT_PATH = next((p for p in _FONT_CANDIDATES if os.path.exists(p)), _FONT_CANDIDATES[0])
pdfmetrics.registerFont(TTFont("JaFont", _FONT_PATH))

FONT   = "JaFont"
FONT_B = "JaFont"

def style(size=9, bold=False, align="LEFT", color=colors.black):
    """ParagraphStyle ショートカット"""
    alignment = {"LEFT": 0, "CENTER": 1, "RIGHT": 2}.get(align, 0)
    return ParagraphStyle(
        name="",
        fontName=FONT_B if bold else FONT,
        fontSize=size,
        leading=size * 1.5,
        textColor=color,
        alignment=alignment,
    )

def p(text, size=9, bold=False, align="LEFT", color=colors.black):
    return Paragraph(str(text), style(size, bold, align, color))

def fmt_yen(amount):
    return f"¥{amount:,.0f}"

# ─────────────────────────────────────────────
# メイン生成関数
# ─────────────────────────────────────────────
def generate_receipt(
    date: str,          # 例: "2025年3月5日"
    recipient_name: str,        # 宛名（会社名 or 氏名）
    recipient_address: str,     # 住所（〒xxx-xxxx 住所）
    subject: str,               # 件名
    items: list,                # [{"name": "...", "qty": 1, "unit_price": 1000}, ...]
    payment_date: str = "",     # 支払予定日
    payment_method: str = "銀行振込",
    note: str = "",
    output_dir: str = None,
    receipt_number: str = None,
    honorific: str = "御中",    # 敬称：法人="御中"、個人="様"
    tax_inclusive: bool = True, # True=単価が税込み（逆算）、False=単価が税抜き（加算）
):
    if output_dir is None:
        output_dir = os.path.dirname(__file__)
    os.makedirs(output_dir, exist_ok=True)

    if receipt_number is None:
        receipt_number = next_receipt_number()

    # ファイル名
    safe_name = recipient_name.replace(" ", "").replace("　", "")
    filename = f"{safe_name}_{receipt_number}.pdf"
    filepath = os.path.join(output_dir, filename)

    doc = SimpleDocTemplate(
        filepath,
        pagesize=A4,
        leftMargin=15*mm, rightMargin=15*mm,
        topMargin=15*mm, bottomMargin=15*mm,
    )

    W = A4[0] - 30*mm   # 有効幅 (mm→pt 変換済み)
    story = []

    # ══════════════════════════════════════════
    # タイトル行
    # ══════════════════════════════════════════
    story.append(p("支払通知書（買取明細書）", size=16, bold=True, align="CENTER"))
    story.append(Spacer(1, 6*mm))

    # ══════════════════════════════════════════
    # 宛名ブロック（左） ／ 発行者ブロック（右）
    # ══════════════════════════════════════════
    left_block = [
        [p(f"{recipient_name}　{honorific}", size=14, bold=True)],
        [p(recipient_address, size=9)],
    ]
    left_tbl = Table(left_block, colWidths=[W * 0.55])
    left_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))

    right_block = [
        [p("支払通知日", size=8), p(date, size=9)],
        [p("支払通知書番号", size=8), p(receipt_number, size=9)],
        [p("", size=8), p("")],
        [p("発行者", size=8), p(ISSUER["name"], size=9, bold=True)],
        [p("", size=8), p(f"〒{ISSUER['zip']}　{ISSUER['address']}", size=8)],
        [p("適格請求書番号", size=7), p(ISSUER["invoice_no"], size=8)],
    ]
    right_tbl = Table(right_block, colWidths=[W * 0.2, W * 0.25])
    right_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTNAME", (0, 0), (-1, -1), FONT),
    ]))

    header_tbl = Table([[left_tbl, right_tbl]], colWidths=[W * 0.55, W * 0.45])
    header_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(header_tbl)
    story.append(Spacer(1, 5*mm))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.black))
    story.append(Spacer(1, 3*mm))

    # ══════════════════════════════════════════
    # 件名
    # ══════════════════════════════════════════
    story.append(p(f"件名：{subject}", size=10, bold=True))
    story.append(Spacer(1, 5*mm))

    # ══════════════════════════════════════════
    # 集計（右寄せ）
    # ══════════════════════════════════════════
    total_taxinc = sum(item["qty"] * item["unit_price"] for item in items)
    if tax_inclusive:
        # 単価が税込み → 逆算で税抜きを算出（切り捨て）
        subtotal = int(total_taxinc / 1.1)
        tax   = total_taxinc - subtotal
        total = total_taxinc
    else:
        # 単価が税抜き → 従来通り加算
        subtotal = total_taxinc
        tax   = int(subtotal * 0.10)
        total = subtotal + tax

    summary_data = [
        [p("小計（税抜）", size=9, align="RIGHT"), p(fmt_yen(subtotal), size=9, align="RIGHT")],
        [p("消費税（10%）", size=9, align="RIGHT"), p(fmt_yen(tax), size=9, align="RIGHT")],
        [p("お支払金額", size=10, bold=True, align="RIGHT"), p(fmt_yen(total), size=10, bold=True, align="RIGHT")],
    ]
    col_w = W * 0.25
    summary_tbl = Table(summary_data, colWidths=[col_w, col_w])
    summary_tbl.setStyle(TableStyle([
        ("ALIGN",      (0, 0), (-1, -1), "RIGHT"),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("LINEABOVE",  (0, 2), (-1, 2), 1, colors.black),
        ("LINEBELOW",  (0, 2), (-1, 2), 2, colors.black),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
    ]))

    # 集計を右端に配置
    align_tbl = Table([[p(""), summary_tbl]], colWidths=[W * 0.5, col_w * 2])
    align_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(align_tbl)
    story.append(Spacer(1, 5*mm))

    # ══════════════════════════════════════════
    # 明細テーブル
    # ══════════════════════════════════════════
    header_row = [
        p("No",     size=9, bold=True, align="CENTER", color=colors.white),
        p("摘要",   size=9, bold=True, align="CENTER", color=colors.white),
        p("数量",   size=9, bold=True, align="CENTER", color=colors.white),
        p("単価",   size=9, bold=True, align="CENTER", color=colors.white),
        p("明細金額", size=9, bold=True, align="CENTER", color=colors.white),
    ]
    col_widths = [W * 0.06, W * 0.46, W * 0.12, W * 0.18, W * 0.18]

    detail_rows = [header_row]
    for i, item in enumerate(items, 1):
        amount = item["qty"] * item["unit_price"]
        detail_rows.append([
            p(str(i), size=9, align="CENTER"),
            p(item["name"], size=9),
            p(f'{item["qty"]:,}', size=9, align="RIGHT"),
            p(fmt_yen(item["unit_price"]), size=9, align="RIGHT"),
            p(fmt_yen(amount), size=9, align="RIGHT"),
        ])

    detail_tbl = Table(detail_rows, colWidths=col_widths, repeatRows=1)
    detail_tbl.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0), colors.HexColor("#404040")),
        ("TEXTCOLOR",    (0, 0), (-1, 0), colors.white),
        ("GRID",         (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
        ("TOPPADDING",   (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F5F5")]),
    ]))
    story.append(detail_tbl)
    story.append(Spacer(1, 6*mm))

    # ══════════════════════════════════════════
    # 支払情報 ・ 備考
    # ══════════════════════════════════════════
    info_data = [
        [p("支払予定日", size=9, bold=True), p(payment_date or "別途通知", size=9)],
        [p("支払方法", size=9, bold=True), p(payment_method, size=9)],
        [p("備考", size=9, bold=True), p(note or "　", size=9)],
    ]
    info_tbl = Table(info_data, colWidths=[W * 0.2, W * 0.5])
    info_tbl.setStyle(TableStyle([
        ("GRID",         (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
        ("TOPPADDING",   (0, 0), (-1, -1), 5),
    ]))
    story.append(info_tbl)
    story.append(Spacer(1, 4*mm))

    # ══════════════════════════════════════════
    # 内訳
    # ══════════════════════════════════════════
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
    story.append(Spacer(1, 2*mm))
    breakdown_data = [
        [
            p("【内訳】", size=8, bold=True),
            p(f"10%対象（税抜）：{fmt_yen(subtotal)}", size=8),
            p(f"10%消費税：{fmt_yen(tax)}", size=8),
        ]
    ]
    breakdown_tbl = Table(breakdown_data, colWidths=[W * 0.15, W * 0.42, W * 0.43])
    breakdown_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(breakdown_tbl)

    doc.build(story)
    print(f"生成完了: {filepath}")
    return filepath


# ─────────────────────────────────────────────
# 使用例（直接実行時）
# ─────────────────────────────────────────────
if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    generate_receipt(
        date="2025年3月5日",
        recipient_name="スズラン商店",
        recipient_address="〒000-0000　（住所）",
        subject="スズラン商店様のポケモンカード買取に関する支払通知",
        items=[
            {"name": "ポケモンカード（例）", "qty": 1, "unit_price": 10000},
        ],
        payment_date="2025年3月31日",
        payment_method="銀行振込",
        note="",
        output_dir=script_dir,
    )
